"""Exercise Streamlit against a RUNNING real FastAPI backend."""
import json
import sqlite3
from streamlit.testing.v1 import AppTest
from app.config import ROOT, settings

def run():
    application = AppTest.from_file(str(ROOT / 'frontend/streamlit_app.py')).run(timeout=180)
    assert not application.exception, application.exception
    assert not application.error, [e.value for e in application.error]
    metrics = {m.label: m.value for m in application.metric}
    assert metrics['Unique incidents'] == '24,918' and metrics['Event observations'] == '141,712'
    application.chat_input[0].set_value('How many unique incidents are present in the dataset?').run(timeout=180)
    assert not application.exception and not application.error
    assert any('24,918 unique incidents' in text.value for text in application.markdown)
    next(button for button in application.button if button.label == 'Load complete recorded history').click().run(timeout=180)
    assert not application.exception and not application.error
    assert len(application.dataframe) >= 2
    application.selectbox[0].select('1 - Critical').run(timeout=180)
    with sqlite3.connect(settings.db) as conn:
        expected = conn.execute("SELECT COUNT(*) FROM incident_summary WHERE latest_observed_priority='1 - Critical'").fetchone()[0]
    assert next(m.value for m in application.metric if m.label == 'Unique incidents') == f'{expected:,}'
    assert not application.exception and not application.error
    results = {'initial_metrics':metrics, 'chat':'passed', 'incident_explorer':'passed', 'priority_filter':'passed', 'streamlit_exceptions':0}
    (ROOT / 'runtime/frontend_results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    return results

if __name__ == '__main__':
    print(json.dumps(run(), indent=2))
