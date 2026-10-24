"""Real SQL + real local retrieval acceptance checks, with optional live HTTP."""
import argparse
import json
import sqlite3
from pathlib import Path
import httpx
from app.config import ROOT, settings
from app.database.inspection import hashes

QUESTIONS = [
    'How many unique incidents are present in the dataset?',
    'How many event records are available?',
    'Show the distribution of incidents by latest observed priority.',
    'Which latest observed incident states are most common?',
    'Which incidents have recorded priority changes?',
    'What is the illustrative procedure for escalating a critical incident?',
    'What does the demonstration policy say about reopening incidents?',
    'Find the escalation policy and show the number of incidents in the corresponding priority category.',
    'Show the recorded history of {incident_id}.',
    'What information is unavailable in the original UCI dataset?'
]

def run(url=None):
    if url:
        client = httpx.Client(base_url=url, timeout=180)
    else:
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
    initial = hashes()
    with sqlite3.connect(settings.db) as conn:
        oracle = {
            'incidents': conn.execute('SELECT COUNT(DISTINCT number) FROM incident_events').fetchone()[0],
            'events': conn.execute('SELECT COUNT(*) FROM incident_events').fetchone()[0],
            'priorities': dict(conn.execute('SELECT latest_observed_priority,COUNT(*) FROM incident_summary GROUP BY latest_observed_priority')),
            'states': dict(conn.execute('SELECT latest_observed_incident_state_clean,COUNT(*) FROM incident_summary GROUP BY latest_observed_incident_state_clean')),
            'priority_changes': conn.execute('SELECT COUNT(*) FROM incident_summary WHERE priority_changed=1').fetchone()[0],
        }
        incident_id = conn.execute('SELECT number FROM incident_summary ORDER BY number LIMIT 1').fetchone()[0]
        history_count = conn.execute('SELECT COUNT(*) FROM incident_events WHERE number=?', [incident_id]).fetchone()[0]
    outcomes = []
    with client:
        assert client.get('/health').status_code == 200
        for index, question in enumerate(QUESTIONS):
            question = question.format(incident_id=incident_id)
            response = client.post('/chat', json={'question':question})
            assert response.status_code == 200, (question, response.text)
            result = response.json()
            assert not result['errors'], result['errors']
            data = (result['analytics'] or {}).get('data')
            if index == 0: assert data['total_incidents'] == oracle['incidents'] == 24918
            if index == 1: assert data['total_events'] == oracle['events'] == 141712
            if index == 2: assert {r['priority']:r['incident_count'] for r in data} == oracle['priorities']
            if index == 3: assert {r['state']:r['incident_count'] for r in data} == oracle['states']
            if index == 4: assert data['total_changed_incidents'] == oracle['priority_changes']
            if index in (5, 6, 7):
                expected = 'DEMO-POL-08' if index == 6 else 'DEMO-POL-03'
                assert any(s.get('document_id') == expected for s in result['sources']), (question, result['sources'])
                assert 'Synthetic demonstration policy' in result['answer']
            if index == 7:
                assert result['route'] == 'HYBRID'
                assert data['total_incidents'] == oracle['priorities']['1 - Critical']
                assert 'Real historical dataset' in result['answer']
            if index == 8: assert len(data['history']) == history_count
            outcomes.append({'question':question, 'route':result['route'], 'tools':result['execution']['tools'], 'sources':result['sources'], 'elapsed_ms':result['execution']['elapsed_ms'], 'status':'passed'})
        assert client.get('/incidents/' + incident_id).status_code == 200
        assert client.post('/analytics/query', json={'tool':'execute_sql'}).status_code == 422
        unrelated = client.post('/chat', json={'question':'What does the demonstration policy say about quantum entanglement photon experiments?'})
        assert unrelated.status_code == 200
        assert 'could not establish an answer' in unrelated.json()['answer']
        assert not unrelated.json()['sources'], 'Unrelated question returned irrelevant policy citations'
    assert initial == hashes(), 'Authoritative input files were modified'
    baseline = json.loads((ROOT / 'docs/INPUT_HASHES.json').read_text(encoding='utf-8'))
    assert initial == baseline, 'Inputs differ from the recorded original baseline'
    report = {'acceptance_questions_passed':len(outcomes), 'unrelated_policy_no_evidence':'passed', 'oracle':oracle, 'questions':outcomes, 'source_files_unchanged':True}
    (ROOT / 'runtime').mkdir(exist_ok=True)
    (ROOT / 'runtime/smoke_results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', help='Optional live FastAPI base URL; otherwise use TestClient')
    args = parser.parse_args()
    print(json.dumps(run(args.url), indent=2))
