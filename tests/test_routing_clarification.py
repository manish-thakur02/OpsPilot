import pytest
from app.agents.graph import build_graph
from app.agents.router import offline_plan


AMBIGUOUS = [
    ('How many unresolved incidents?', 'state'),
    ('How many open incidents?', 'state'),
    ('How many incidents are not resolved?', 'state'),
    ('How many incidents are not yet closed?', 'state'),
    ('How many active or closed incidents?', 'state'),
    ('How many incidents in Group 1 and Group 2?', 'assignment group'),
    ('How many incidents in Group 1 or Group 2?', 'assignment group'),
    ('How many incidents in groups 1 and 2?', 'assignment group'),
    ('How many incidents in groups 1, 2, 3?', 'assignment group'),
    ('How many incidents in Group 1 & 2?', 'assignment group'),
    ('How many incidents in Group 1 to 3?', 'assignment group'),
    ('Find the escalation policy and count unresolved incidents: how many?', 'state'),
]


@pytest.mark.parametrize('question,topic', AMBIGUOUS)
@pytest.mark.parametrize('llm_enabled', [False, True])
def test_ambiguous_questions_clarify_without_tools(question, topic, llm_enabled):
    class NoTools:
        def run(self, request):
            pytest.fail('Clarification must not query incident data')
        def search(self, question):
            pytest.fail('Clarification must not retrieve policy evidence')

    class NoProvider:
        enabled = llm_enabled
        def plan(self, question):
            pytest.fail('Provider must not bypass clarification')

    plan = offline_plan(question)
    assert plan.intent == 'UNSUPPORTED' and plan.request is None
    state = build_graph(NoTools(), NoTools(), NoProvider()).invoke({'question': question})
    assert state['intent'] == 'UNSUPPORTED'
    assert state['analytics'] is None
    assert state['selected_tools'] == [] and state['sources'] == []
    assert state['errors'] == []
    assert 'Please clarify' in state['answer'] and topic in state['answer']


@pytest.mark.parametrize('question,expected', [
    ('How many incidents in Group 1?', {'assignment_group': 'Group 1'}),
    ('How many incidents in groups 1?', {'assignment_group': 'Group 1'}),
    ('How many incidents in Group 1 and Group 1?', {'assignment_group': 'Group 1'}),
    ('How many active incidents in Group 2?', {'state': 'Active', 'assignment_group': 'Group 2'}),
    ('How many resolved incidents?', {'state': 'Resolved'}),
    ('How many closed critical incidents?', {'state': 'Closed', 'priority': '1 - Critical'}),
])
def test_supported_single_filters_remain_exact(question, expected):
    plan = offline_plan(question)
    assert plan.intent == 'ANALYTICS'
    assert plan.request.tool == 'overview'
    assert plan.request.filters.model_dump(exclude_none=True) == expected


@pytest.mark.parametrize('question', [
    'How many unresolved incidents?',
    'How many incidents in Group 1 and Group 2?',
])
def test_chat_endpoint_returns_clarification_response(question):
    from app.api.routes import chat
    from app.api.schemas import ChatRequest, ChatResponse

    class NoTools:
        def run(self, request):
            pytest.fail('Clarification must not query incident data')
        def search(self, question):
            pytest.fail('Clarification must not retrieve policy evidence')

    class Offline:
        enabled = False

    graph = build_graph(NoTools(), NoTools(), Offline())
    response = chat(ChatRequest(question=question), graph=graph)
    assert isinstance(response, ChatResponse)
    assert response.route == 'UNSUPPORTED'
    assert 'Please clarify' in response.answer
    assert response.analytics is None and response.sources == []
    assert response.errors == [] and response.execution['status'] == 'ok'
