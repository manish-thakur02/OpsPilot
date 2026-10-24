import json
from datetime import date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.database.connection import readonly
from app.database.queries import where

class Filters(BaseModel):
    model_config = ConfigDict(extra='forbid')
    priority: Literal['1 - Critical', '2 - High', '3 - Moderate', '4 - Low'] | None = None
    state: Literal['New', 'Resolved', 'Closed', 'Active', 'Awaiting User Info', 'Awaiting Problem', 'Awaiting Vendor', 'Awaiting Evidence', 'Unknown'] | None = None
    assignment_group: str | None = Field(default=None, pattern=r'^Group \d+$', max_length=32)
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode='after')
    def ordered_dates(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError('start_date must be on or before end_date')
        return self

class ToolRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    tool: Literal['overview', 'event_count', 'priorities', 'states', 'trends', 'priority_changes', 'sla_changes', 'reopenings', 'resolution', 'assignment_groups', 'incident', 'diagnostics', 'limitations']
    filters: Filters = Field(default_factory=Filters)
    incident_id: str | None = Field(default=None, pattern=r'^INC\d{7}$')

    @model_validator(mode='after')
    def incident_required(self):
        if self.tool == 'incident' and not self.incident_id:
            raise ValueError('An incident ID such as INC0000045 is required')
        if self.tool == 'incident' and any(self.filters.model_dump().values()):
            raise ValueError('Incident lookup uses only incident_id; population filters are not supported')
        if self.tool in {'diagnostics', 'limitations'} and any(self.filters.model_dump().values()):
            raise ValueError('Diagnostics and limitations describe the complete dataset and do not accept population filters')
        return self

METRIC_NOTES = 'Incident metrics use latest observed summary records. Event metrics count recorded observations. Dates filter summary opening dates, inclusively; timezone unspecified. No as-of or SLA-breach inference.'
LIMITATIONS = 'The original UCI dataset has anonymized structured observations, no full ticket narratives, real organization policies, costs, customer identities or verified SLA targets. Source made_sla is not interpreted as breach/compliance. No timezone is established. Latest observations are snapshots, not independently verified final ground truth. Completion timestamps may leak future information. OpsPilot policy documents are synthetic demonstrations and did not establish historical compliance.'

def rows(conn, sql, params=()):
    return [dict(row) for row in conn.execute(sql, params)]

class Analytics:
    def __init__(self, db=None):
        self.db = db

    def run(self, request: ToolRequest | dict):
        request = ToolRequest.model_validate(request)
        if request.tool == 'limitations':
            return {'metric': 'limitations', 'population': 'dataset documentation', 'text': LIMITATIONS}
        clause, params = where(request.filters)
        with readonly(self.db) as conn:
            tool = request.tool
            if tool in {'overview', 'event_count', 'reopenings', 'resolution', 'sla_changes'}:
                data = rows(conn, '''SELECT COUNT(*) AS total_incidents, COALESCE(SUM(event_count),0) AS total_events,
                    COALESCE(SUM(priority_changed),0) AS priority_changed_incidents,
                    COALESCE(SUM(made_sla_changed),0) AS made_sla_changed_incidents,
                    COALESCE(AVG(event_count),0) AS average_events_per_incident,
                    COUNT(CASE WHEN resolution_hours_latest_record >= 0 THEN 1 END) AS resolution_valid_incidents,
                    AVG(CASE WHEN resolution_hours_latest_record >= 0 THEN resolution_hours_latest_record END) AS average_resolution_hours,
                    MIN(CASE WHEN resolution_hours_latest_record >= 0 THEN resolution_hours_latest_record END) AS minimum_resolution_hours,
                    MAX(CASE WHEN resolution_hours_latest_record >= 0 THEN resolution_hours_latest_record END) AS maximum_resolution_hours,
                    COALESCE(SUM(latest_selection_tied),0) AS latest_selection_tied_incidents
                    FROM incident_summary s''' + clause, params)[0]
                # Population is summary-selected; reopening is observed at ANY event.
                reopen_where = clause + (' AND ' if clause else ' WHERE ') + 'EXISTS (SELECT 1 FROM incident_events e WHERE e.number=s.number AND e.reopen_count>0)'
                data['observed_reopened_incidents'] = conn.execute('SELECT COUNT(*) FROM incident_summary s' + reopen_where, params).fetchone()[0]
                data['resolution_excluded_incidents'] = data['total_incidents'] - data['resolution_valid_incidents']
                return self.result(tool, data, request)
            if tool in {'priorities', 'states', 'trends', 'assignment_groups'}:
                expression, label = {
                    'priorities': ('s.latest_observed_priority', 'priority'),
                    'states': ('s.latest_observed_incident_state_clean', 'state'),
                    'trends': ("substr(s.opened_at,1,7)", 'month'),
                    'assignment_groups': ("COALESCE(s.assignment_group,'Unknown')", 'assignment_group')
                }[tool]
                order = 'label' if tool in {'priorities', 'trends'} else 'incident_count DESC,label'
                limit = ' LIMIT 10' if tool == 'assignment_groups' else ''
                data = rows(conn, f'SELECT {expression} AS label,COUNT(*) AS incident_count FROM incident_summary s' + clause + f' GROUP BY {expression} ORDER BY {order}' + limit, params)
                data = [{label: r['label'], 'incident_count': r['incident_count']} for r in data]
                return self.result(tool, data, request)
            if tool == 'priority_changes':
                subset = clause + (' AND ' if clause else ' WHERE ') + 's.priority_changed=1'
                count = conn.execute('SELECT COUNT(*) FROM incident_summary s' + subset, params).fetchone()[0]
                data = rows(conn, 'SELECT number,first_observed_priority,latest_observed_priority,priority_distinct_count FROM incident_summary s' + subset + ' ORDER BY number LIMIT 100', params)
                return self.result(tool, {'total_changed_incidents': count, 'incidents': data, 'returned': len(data), 'limit': 100, 'truncated': count > 100}, request)
            if tool == 'incident':
                found = rows(conn, 'SELECT * FROM incident_summary WHERE number=?', [request.incident_id])
                if not found:
                    raise LookupError(f'Incident {request.incident_id} was not found')
                history = rows(conn, 'SELECT * FROM incident_events WHERE number=? ORDER BY sys_updated_at,sys_mod_count,source_row_id', [request.incident_id])
                return self.result(tool, {'summary': found[0], 'history': history, 'event_count': len(history)}, request)
            if tool == 'diagnostics':
                metadata = dict(conn.execute('SELECT key,value FROM import_metadata'))
                data = {'quality_report': json.loads(metadata['quality_report']), 'source_sha256': json.loads(metadata['sha256']), 'imported_at_utc': metadata['imported_at_utc'], 'latest_selection_ties': rows(conn, 'SELECT * FROM latest_selection_ties')}
                return self.result(tool, data, request)
        raise ValueError('Unsupported approved tool')

    @staticmethod
    def result(tool, data, request):
        return {'metric': tool, 'population': 'incident summary records' if tool != 'incident' else 'one incident and all its event observations', 'data': data, 'filters': request.filters.model_dump(mode='json'), 'notes': METRIC_NOTES}
