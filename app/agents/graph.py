"""A real compiled, bounded LangGraph; no arbitrary SQL or conversation loop."""
import json
import logging
import time
from typing import TypedDict, Any
from langgraph.graph import StateGraph, START, END
from app.agents.router import offline_plan, constraint_clarification
from app.rag.retriever import Retriever
from app.services.analytics import Analytics
from app.services.llm import LLM

logger = logging.getLogger(__name__)

class CopilotState(TypedDict, total=False):
    question: str
    intent: str
    tool_request: dict
    selected_tools: list[str]
    documents: list[dict]
    analytics: dict | None
    sources: list[dict]
    errors: list[str]
    trace: list[str]
    answer: str
    mode: str
    reason: str
    started: float
    elapsed_ms: float

def analytics_text(result):
    data, tool = result.get('data'), result['metric']
    if tool == 'limitations':
        return result['text']
    if tool == 'event_count':
        return f"{data['total_events']:,} event observations across {data['total_incidents']:,} unique incidents in the selected population."
    if tool == 'overview':
        return f"{data['total_incidents']:,} unique incidents; {data['total_events']:,} event observations. Average {data['average_events_per_incident']:.3f} observations per incident."
    if tool == 'reopenings':
        return f"{data['observed_reopened_incidents']:,} incidents have at least one recorded reopen_count greater than zero."
    if tool == 'sla_changes':
        return f"{data['made_sla_changed_incidents']:,} incidents have observed changes in the source made_sla Boolean. This is not an SLA-breach measure."
    if tool == 'resolution':
        avg = data['average_resolution_hours']
        description = f'{avg:.2f} hours' if avg is not None else 'unavailable'
        return f"Average descriptive resolution duration: {description}, from {data['resolution_valid_incidents']:,} valid nonnegative latest-summary durations; {data['resolution_excluded_incidents']:,} incidents excluded."
    if tool == 'priority_changes':
        return f"{data['total_changed_incidents']:,} incidents have recorded priority changes. Showing {data['returned']} identifiers (limit {data['limit']}; truncated: {data['truncated']}).\n" + '\n'.join(f"- {r['number']}: {r['first_observed_priority']} → {r['latest_observed_priority']} ({r['priority_distinct_count']} distinct priorities)" for r in data['incidents'])
    if tool == 'incident':
        return f"{data['summary']['number']}: {data['event_count']} recorded event observations. Latest observed state: {data['summary']['latest_observed_incident_state_clean']}; latest observed priority: {data['summary']['latest_observed_priority']}. Complete history is included in structured results."
    if isinstance(data, list):
        return '\n'.join('- ' + ', '.join(f'{k}: {v}' for k, v in row.items()) for row in data) or 'No matching incident records.'
    return json.dumps(data, indent=2)

def build_graph(analytics=None, retriever=None, llm=None):
    analytics = analytics or Analytics()
    retriever = retriever or Retriever()
    llm = llm or LLM()

    def parse(state):
        question = state.get('question', '').strip()
        if not 1 <= len(question) <= 2000:
            raise ValueError('Question must contain 1–2000 characters')
        return {'question': question, 'trace': ['parse: question validated'], 'errors': [], 'documents': [], 'sources': [], 'analytics': None, 'selected_tools': [], 'started': time.perf_counter(), 'mode': 'llm' if llm.enabled else 'offline_demo'}

    def classify(state):
        errors = []
        try:
            # Deterministic safety guard also applies before provider planning.
            guard = offline_plan(state['question'])
            needs_clarification = guard.intent == 'UNSUPPORTED' and constraint_clarification(state['question']) is not None
            if llm.enabled and not needs_clarification and not (guard.intent == 'UNSUPPORTED' and guard.reason.startswith('This request')):
                plan = llm.plan(state['question'])
            else:
                plan = guard
        except Exception:
            logger.exception('Intent planning failed')
            errors.append('Provider planning or parameter validation failed; using documented offline routing.')
            try:
                plan = offline_plan(state['question'])
            except ValueError:
                from app.agents.router import Plan
                plan = Plan(intent='UNSUPPORTED', reason='Invalid filter parameters. Please use the documented query format.')
        return {'intent': plan.intent, 'tool_request': plan.request.model_dump(mode='json') if plan.request else {}, 'reason': plan.reason, 'errors': errors, 'mode': 'offline_demo' if errors else state['mode'], 'trace': state['trace'] + [f'classify: {plan.intent}', plan.reason]}

    def execute(state):
        documents, result, errors, tools = [], None, list(state['errors']), []
        if state['intent'] in {'POLICY', 'HYBRID'}:
            tools.append('retrieve_synthetic_policy')
            try:
                documents = retriever.search(state['question'])
            except Exception:
                logger.exception('Policy retrieval failed')
                errors.append('Local policy evidence unavailable. Run python -m scripts.ingest_policies and check the model cache.')
        if state['intent'] in {'ANALYTICS', 'HYBRID'}:
            tools.append(state['tool_request']['tool'])
            try:
                result = analytics.run(state['tool_request'])
            except LookupError as exc:
                errors.append(str(exc))
            except Exception:
                logger.exception('Analytics tool failed')
                errors.append('Analytics tool unavailable. Check database initialization and validated parameters.')
        return {'documents': documents, 'analytics': result, 'errors': errors, 'selected_tools': tools, 'trace': state['trace'] + [f'execute: {", ".join(tools) or "no tools"}']}

    def validate(state):
        errors = list(state['errors'])
        documents = [d for d in state['documents'] if d.get('synthetic') is True and d.get('citation') and d.get('text')]
        result = state['analytics']
        if result and result.get('metric') != state['tool_request'].get('tool'):
            errors.append('Analytics evidence did not match the selected tool.')
            result = None
        return {'documents': documents, 'analytics': result, 'errors': errors, 'trace': state['trace'] + ['validate: result tool and source metadata checked']}

    def compose(state):
        parts, errors, documents = [], list(state['errors']), state['documents']
        if state['intent'] == 'UNSUPPORTED':
            parts.append(state['reason'])
        if state['intent'] in {'POLICY', 'HYBRID'}:
            label = 'Retrieval-only policy evidence (offline demonstration; no LLM-generated answer)'
            if llm.enabled and state['mode'] == 'llm' and documents:
                try:
                    documents = llm.select_evidence(state['question'], documents)
                    label = 'LLM-selected, extractive policy answer (exact cited passages)'
                except Exception:
                    logger.exception('Evidence selection failed')
                    errors.append('Provider composition unavailable; showing retrieval-only passages.')
            parts.append('Synthetic demonstration policy — ' + label)
            if not documents:
                parts.append('I could not establish an answer from the available knowledge base.')
            else:
                for document in documents:
                    parts.append(document['citation'] + '\n\n' + document['text'])
        if state['analytics']:
            parts.append('Real historical dataset — verified SQLite results\n\n' + analytics_text(state['analytics']))
            filters = state['tool_request'].get('filters', {})
            active = {k: v for k, v in filters.items() if v is not None}
            if active:
                parts.append('Applied incident population filters: ' + json.dumps(active))
        if state['intent'] == 'HYBRID':
            parts.append(state['reason'] + ' Synthetic policy does not establish that these historical incidents followed it.')
        if errors:
            parts.append('Errors / fallback notices: ' + ' '.join(errors))
        sources = [{'type': 'synthetic_policy', 'document_id': d['document_id'], 'source': d['source'], 'section': d['section'], 'citation': d['citation'], 'chunk_id': d['id']} for d in documents]
        if state['analytics']:
            if state['analytics']['metric'] == 'limitations':
                sources.append({'type': 'documentation', 'source': 'docs/DATA_SCHEMA.md', 'tool': 'limitations'})
            else:
                sources.append({'type': 'sqlite', 'source': 'incident_summary / incident_events', 'tool': state['analytics']['metric']})
        return {'answer': '\n\n'.join(parts), 'sources': sources, 'errors': errors, 'trace': state['trace'] + ['compose: exact database results and cited policy evidence'], 'elapsed_ms': round((time.perf_counter() - state['started']) * 1000, 2)}

    graph = StateGraph(CopilotState)
    graph.add_node('parse', parse)
    graph.add_node('classify', classify)
    for route in ('POLICY', 'ANALYTICS', 'HYBRID', 'UNSUPPORTED'):
        graph.add_node(route, execute)
        graph.add_edge(route, 'validate')
    graph.add_node('validate', validate)
    graph.add_node('compose', compose)
    graph.add_edge(START, 'parse')
    graph.add_edge('parse', 'classify')
    graph.add_conditional_edges('classify', lambda s: s['intent'], {r: r for r in ('POLICY', 'ANALYTICS', 'HYBRID', 'UNSUPPORTED')})
    graph.add_edge('validate', 'compose')
    graph.add_edge('compose', END)
    return graph.compile()
