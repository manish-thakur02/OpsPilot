import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, model_validator
from app.services.analytics import ToolRequest, Filters

class Plan(BaseModel):
    model_config = ConfigDict(extra='forbid')
    intent: Literal['POLICY', 'ANALYTICS', 'HYBRID', 'UNSUPPORTED']
    request: ToolRequest | None = None
    reason: str = ''

    @model_validator(mode='after')
    def request_matches_route(self):
        if self.intent in {'ANALYTICS', 'HYBRID'} and not self.request:
            raise ValueError('An approved tool is required for this route')
        if self.intent in {'POLICY', 'UNSUPPORTED'} and self.request:
            raise ValueError('This route cannot execute analytics')
        return self


# One state/group can be represented by the approved filter schema. Reject
# ambiguous alternatives before selecting a tool rather than dropping a condition.
STATES = ('Awaiting User Info', 'Awaiting Problem', 'Awaiting Vendor',
          'Awaiting Evidence', 'Closed', 'Resolved', 'Active', 'New', 'Unknown')


def normalized_question(question):
    q = re.sub(r'\s+', ' ', question.lower().strip())
    return re.sub(r'\bawaiting user information\b', 'awaiting user info', q)


def constraint_clarification(question):
    q = normalized_question(question)
    if re.search(r'\burgent\b', q):
        return ('Do you mean a priority count or an escalation procedure? '
                'Urgency and priority are different fields, so I cannot assume urgent means Critical. '
                'Try "How many critical tickets are there?" or '
                '"What is the procedure for escalating a critical incident?"')
    if re.search(r'\b(unresolved|unclosed|open|pending)\b|\bnot\s+(?:yet\s+)?(?:resolved|closed)\b', q):
        return ('Please clarify which latest observed state you mean. '
                'Terms such as unresolved or open do not map to one supported state. '
                'Ask for one explicit state, such as Active or New, or request the state distribution.')
    states = {state for state in STATES if re.search(r'\b' + re.escape(state.lower()) + r'\b', q)}
    if len(states) > 1:
        return ('Please clarify by choosing one latest observed state per question. '
                'Multiple state filters are not supported; request the state distribution to compare states.')
    group_lists = re.findall(
        r'\bgroups?\s+(\d+(?:\s*(?:,|/|&|\band\b|\bor\b)\s*(?:groups?\s+)?\d+)*)', q)
    groups = {int(number) for group_list in group_lists for number in re.findall(r'\d+', group_list)}
    if len(groups) > 1 or re.search(r'\bgroups?\s+\d+\s*(?:-|\bto\b|\bthrough\b)\s*\d+', q):
        return ('Please clarify by choosing one assignment group per question, for example Group 1. '
                'Multiple assignment groups and group ranges are not supported; ask separately for each group.')
    return None


def offline_plan(question):
    q = normalized_question(question)
    blocked = ('drop table', 'delete from', 'insert into', 'update incident_', 'ignore previous', 'ignore all', 'api key', 'password', 'execute sql', 'select *', 'as of', 'as-of', 'predict', 'forecast', 'sla breach', 'breached', 'compliance rate', 'median', 'percentile', 'cost')
    if any(term in q for term in blocked):
        return Plan(intent='UNSUPPORTED', reason='This request is outside the approved read-only metrics and evidence tools.')
    if any(term in q for term in ('unavailable', 'limitations', 'missing information', 'not available in', 'not include')):
        return Plan(intent='ANALYTICS', request=ToolRequest(tool='limitations'))
    if re.search(r'\b(within|before|after|excluding|except|without|yesterday|today|tomorrow)\b|less than|more than|at least|root cause|assigned to|caller|last (week|month|year)', q):
        return Plan(intent='UNSUPPORTED', reason='This constraint is not supported by offline routing. Use the documented priority, state, group or inclusive opening-date filters, or the approved analytics API.')
    if 'first observed priority' in q or ('event' in q and any(term in q for term in ('distribution', 'by priority', 'by state', 'monthly'))):
        return Plan(intent='UNSUPPORTED', reason='This aggregation is not in the approved registry. Priority/state distributions and opening trends count latest-summary incidents; event counts and individual histories are available.')
    policy = any(term in q for term in ('policy', 'procedure', 'escalat', 'illustrative', 'demonstration target', 'how should', 'knowledge article'))
    analytical = any(term in q for term in ('how many', 'number of', 'distribution', 'dataset', 'recorded priority changes', 'latest observed', 'event records', 'event observations', 'monthly', 'trend', 'average', 'top assignment', 'reopenings', 'diagnostic'))
    if policy and not analytical:
        return Plan(intent='POLICY', reason='Retrieve synthetic demonstration policy evidence')
    clarification = constraint_clarification(question)
    if clarification:
        return Plan(intent='UNSUPPORTED', reason=clarification)
    incident = re.search(r'\bINC\d{7}\b', question, re.I)
    if incident:
        return Plan(intent='ANALYTICS', request=ToolRequest(tool='incident', incident_id=incident.group().upper()))
    filters = {}
    # Explicitly support a small documented offline grammar; refuse unparsed filters.
    priorities = [('1 - Critical', r'\bp1\b|\bcritical\b|highest.priority'), ('2 - High', r'\bp2\b|\bhigh\b'), ('3 - Moderate', r'\bp3\b|\bmoderate\b'), ('4 - Low', r'\bp4\b|\blow\b')]
    hits = [label for label, pattern in priorities if re.search(pattern, q)]
    if len(hits) > 1:
        return Plan(intent='UNSUPPORTED', reason='Offline mode accepts one priority filter at a time. Use the priority distribution for comparison.')
    if hits:
        filters['priority'] = hits[0]
    if policy and analytical and 'escalat' in q and not hits:
        filters['priority'] = '1 - Critical'
    dates = re.findall(r'\b\d{4}-\d{2}-\d{2}\b', q)
    if dates:
        if len(dates) != 2 or not re.search(r'from\s+\d{4}-\d{2}-\d{2}\s+to\s+\d{4}-\d{2}-\d{2}', q):
            return Plan(intent='UNSUPPORTED', reason='Use an inclusive opening-date filter: from YYYY-MM-DD to YYYY-MM-DD.')
        filters.update(start_date=dates[0], end_date=dates[1])
    elif re.search(r'\b20\d{2}\b|\blast (month|year|week)\b|\b(january|february|march|april|may|june|july|august|september|october|november|december)\b', q):
        return Plan(intent='UNSUPPORTED', reason='Use explicit opening dates: from YYYY-MM-DD to YYYY-MM-DD.')
    group = re.search(r'\bgroups?\s+(\d+)\b', q)
    if group:
        filters['assignment_group'] = f'Group {group.group(1)}'
    for state in STATES:
        if re.search(r'\b' + re.escape(state.lower()) + r'\b', q):
            filters['state'] = state
            break
    if 'priority change' in q:
        tool = 'priority_changes'
    elif ('sla' in q or 'made_sla' in q) and 'change' in q:
        tool = 'sla_changes'
    elif 'priorit' in q and any(t in q for t in ('distribution', 'each', 'by latest', 'by priority')):
        tool = 'priorities'
    elif 'state' in q and any(t in q for t in ('distribution', 'most common', 'each', 'by')):
        tool = 'states'
    elif 'trend' in q or 'monthly' in q:
        tool = 'trends'
    elif 'resolution' in q and any(t in q for t in ('average', 'duration', 'statistic')):
        tool = 'resolution'
    elif 'reopen' in q and analytical:
        tool = 'reopenings'
    elif 'assignment group' in q and ('top' in q or 'distribution' in q):
        tool = 'assignment_groups'
    elif 'diagnostic' in q or 'data quality' in q or 'selection tie' in q:
        tool = 'diagnostics'
    elif 'event' in q and any(t in q for t in ('how many', 'records', 'observations', 'available')):
        tool = 'event_count'
    elif re.search(r'\b(?:incidents?|tickets?)\b', q) and any(t in q for t in ('how many', 'number of', 'total', 'count', 'average events')):
        tool = 'overview'
    elif q.rstrip(' .?!') in {state.lower() for state in STATES}:
        tool = 'overview'
    else:
        return Plan(intent='UNSUPPORTED', reason='I could not identify a supported action from that phrase. '
                    'This offline assistant searches historical incident data and synthetic policies; it cannot create or update tickets. '
                    'Try "How many critical tickets are there?", "Show the state distribution", '
                    '"What is the escalation procedure?", or an incident ID such as INC0000045. '
                    'For a state count, you can also enter "Awaiting User Information". '
                    'All latest incident snapshots in this dataset are Closed; other states appear in recorded histories.')
    return Plan(intent='HYBRID' if policy else 'ANALYTICS', request=ToolRequest(tool=tool, filters=Filters(**filters)), reason='P1/1 - Critical is the illustrative category selected for critical or unspecified escalation counts.' if policy else 'Deterministic offline selection of an approved SQL tool')
