import sqlite3
import pytest
from pydantic import ValidationError
from app.services.analytics import Analytics, ToolRequest, Filters

@pytest.fixture
def analytics(tmp_path):
    db = tmp_path / 'fixture.db'
    with sqlite3.connect(db) as conn:
        conn.executescript('''
        CREATE TABLE incident_summary(number TEXT PRIMARY KEY,source_row_id INTEGER,event_count INTEGER,latest_observed_priority TEXT,latest_observed_incident_state_clean TEXT,opened_at TEXT,assignment_group TEXT,priority_changed INTEGER,made_sla_changed INTEGER,resolution_hours_latest_record REAL,latest_selection_tied INTEGER,first_observed_priority TEXT,priority_distinct_count INTEGER);
        CREATE TABLE incident_events(source_row_id INTEGER PRIMARY KEY,number TEXT,sys_updated_at TEXT,sys_mod_count INTEGER,reopen_count INTEGER);
        INSERT INTO incident_summary VALUES ('INC0000001',3,3,'1 - Critical','Closed','2016-01-01 12:00:00','Group 1',1,1,2,0,'3 - Moderate',2),('INC0000002',4,1,'3 - Moderate','New','2016-02-01 00:00:00',NULL,0,0,NULL,0,'3 - Moderate',1),('INC0000003',5,1,'4 - Low','Active','2016-02-29 23:59:59','Group 1',0,0,-1,0,'4 - Low',1);
        INSERT INTO incident_events VALUES (1,'INC0000001','2016-01-01 12:00:00',0,0),(2,'INC0000001','2016-01-01 12:00:00',0,1),(3,'INC0000001','2016-01-02 12:00:00',1,0),(4,'INC0000002','2016-02-01 00:00:00',0,0),(5,'INC0000003','2016-02-29 23:59:59',0,0);
        ''')
    return Analytics(db)

def test_population_and_valid_durations(analytics):
    result = analytics.run({'tool': 'overview'})['data']
    assert (result['total_incidents'], result['total_events']) == (3, 5)
    assert result['average_events_per_incident'] == 5/3
    assert result['priority_changed_incidents'] == 1
    assert result['observed_reopened_incidents'] == 1  # any observation, not just the latest
    assert result['average_resolution_hours'] == 2
    assert result['resolution_valid_incidents'] == 1
    assert result['resolution_excluded_incidents'] == 2

def test_filters_trends_and_history(analytics):
    assert analytics.run({'tool': 'overview', 'filters': {'priority': '1 - Critical'}})['data']['total_events'] == 3
    trend = analytics.run({'tool': 'trends', 'filters': {'start_date': '2016-02-01', 'end_date': '2016-02-29'}})['data']
    assert trend == [{'month': '2016-02', 'incident_count': 2}]
    assert len(analytics.run({'tool': 'incident', 'incident_id': 'INC0000001'})['data']['history']) == 3
    assert analytics.run({'tool': 'priority_changes'})['data']['total_changed_incidents'] == 1
    assert sum(r['incident_count'] for r in analytics.run({'tool': 'states'})['data']) == 3
    assert analytics.run({'tool': 'assignment_groups'})['data'][0]['incident_count'] == 2
    with pytest.raises(LookupError):
        analytics.run({'tool': 'incident', 'incident_id': 'INC9999999'})

@pytest.mark.parametrize('payload', [
    {'tool':'DROP TABLE incident_events'}, {'tool':'overview','sql':'DELETE FROM incident_events'},
    {'tool':'overview','filters':{'priority':"1'; DROP TABLE incident_events;--"}},
    {'tool':'overview','filters':{'assignment_group':"' OR 1=1--"}},
    {'tool':'incident','incident_id':'INC0000001 OR 1=1'},
    {'tool':'overview','filters':{'start_date':'2016-03-01','end_date':'2016-01-01'}},
    {'tool':'incident'}, {'tool':'diagnostics','filters':{'priority':'1 - Critical'}}
])
def test_reject_unsafe_or_unsupported_parameters(payload):
    with pytest.raises(ValidationError):
        ToolRequest.model_validate(payload)
