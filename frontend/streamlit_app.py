"""API-only dashboard: no database or analytics imports."""
import os
from pathlib import Path
import httpx
import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / '.env', override=False)
API_URL = os.getenv('OPSPILOT_API_URL', 'http://127.0.0.1:8000').rstrip('/')
st.set_page_config(page_title='OpsPilot — Agentic Knowledge & Analytics Copilot', page_icon='◈', layout='wide')
st.markdown('''<style>
.block-container {padding-top:2rem;max-width:1450px}
[data-testid="stMetric"] {border:1px solid #dce3ef;border-radius:12px;padding:16px;background:rgba(100,130,170,.06)}
.eyebrow {color:#6080a8;font-size:.8rem;letter-spacing:.18rem;font-weight:700}
</style>''', unsafe_allow_html=True)

def api(path, body=None, params=None):
    try:
        with httpx.Client(timeout=120) as client:
            response = client.post(API_URL + path, json=body) if body is not None else client.get(API_URL + path, params=params)
        if response.status_code >= 400:
            try:
                payload = response.json()
                detail = payload.get('detail') or payload.get('answer') or payload
            except ValueError:
                detail = response.text[:300]
            st.error(f'API {response.status_code}: {detail}')
            return None
        return response.json()
    except httpx.HTTPError:
        st.error('Backend unavailable. Start the FastAPI server at ' + API_URL)
        return None

def show_chat(result):
    st.caption(f"Route: {result['route']} · Mode: {result['execution']['mode']} · {result['execution']['elapsed_ms']:.0f} ms")
    # Text from retrieved files or providers is never rendered as unsafe HTML.
    st.markdown(result['answer'])
    if result.get('analytics'):
        with st.expander('Verified structured analytics'):
            data = result['analytics'].get('data')
            if isinstance(data, list) and data:
                st.dataframe(pd.DataFrame(data), width='stretch')
            else:
                st.json(result['analytics'])
    with st.expander('Sources and execution trace'):
        st.json(result['sources'])
        st.json(result['execution'])

st.markdown('<div class="eyebrow">OPERATIONS INTELLIGENCE / LOCAL DEMONSTRATION</div>', unsafe_allow_html=True)
st.title('OpsPilot — Agentic Knowledge & Analytics Copilot')
st.caption('Real incident observations. Traceable answers. Explicitly synthetic policy evidence.')
health = api('/health')
with st.sidebar:
    st.title('◈ OpsPilot')
    st.caption('Incident intelligence and knowledge analytics')
    if health:
        st.success('Backend connected')
        st.info('Offline demonstration mode — real SQL and local retrieval' if health['mode'] == 'offline_demo' else 'LLM configured — approved tools and cited extracts')
        if not health['policy_index_ready']:
            st.warning('Run python -m scripts.ingest_policies to prepare policy retrieval.')
    st.markdown('**Data boundaries**')
    st.caption('UCI historical records are real and anonymized. All policy documents are synthetic examples created for this demonstration.')
    st.caption('Latest observed snapshots; no SLA-breach or historical as-of claims. Source timestamps have no established timezone.')
    if st.button('Refresh dashboard'):
        st.rerun()

copilot, dashboard, explorer = st.tabs(['AI Copilot', 'Incident Analytics', 'Incident Explorer'], key='workspace_tabs')
with copilot:
    st.subheader('Ask with evidence')
    if health and health['mode'] == 'offline_demo':
        st.info('Offline assistant: supports incident counts, distributions, histories and policy lookup. '
                'Try the examples below or enter a state such as Awaiting User Information. '
                'It cannot create or update tickets. All latest snapshots are Closed; other states occur in histories.')
    examples = [
        'How many unique incidents are present in the dataset?',
        'Show the distribution of incidents by latest observed priority.',
        'What is the illustrative procedure for escalating a critical incident?',
        'What does the demonstration policy say about reopening incidents?',
        'Find the escalation policy and show the number of incidents in the corresponding priority category.'
    ]
    st.session_state.setdefault('messages', [])
    pending = None
    with st.expander('Try a demonstration question', expanded=not st.session_state.messages):
        for i, example in enumerate(examples):
            if st.button(example, key=f'example_{i}', width='stretch'):
                pending = example
    for message in st.session_state.messages:
        with st.chat_message(message['role']):
            if message['role'] == 'user':
                st.write(message['text'])
            else:
                show_chat(message['result'])
    typed = st.chat_input('Ask about incident metrics or demonstration procedures', max_chars=2000)
    question = typed or pending
    if question:
        st.session_state.messages.append({'role': 'user', 'text': question})
        with st.chat_message('user'):
            st.write(question)
        with st.chat_message('assistant'):
            with st.spinner('Selecting tools and checking evidence…'):
                result = api('/chat', {'question': question})
            if result:
                st.session_state.messages.append({'role': 'assistant', 'result': result})
                show_chat(result)

with dashboard:
    st.subheader('Historical incident population')
    a, b, c = st.columns(3)
    priority = a.selectbox('Latest observed priority', ['All', '1 - Critical', '2 - High', '3 - Moderate', '4 - Low'])
    state = b.selectbox('Latest observed state', ['All', 'Active', 'Awaiting Evidence', 'Awaiting Problem', 'Awaiting User Info', 'Awaiting Vendor', 'Closed', 'New', 'Resolved', 'Unknown'])
    date_filter = c.checkbox('Filter by incident opening date')
    params = {}
    if priority != 'All': params['priority'] = priority
    if state != 'All': params['state'] = state
    if date_filter:
        from datetime import date
        d1, d2 = st.columns(2)
        start = d1.date_input('Opened from (inclusive)', value=date(2016,2,29))
        end = d2.date_input('Opened through (inclusive)', value=date(2017,2,18))
        params.update(start_date=start.isoformat(), end_date=end.isoformat())
    if params.get('start_date', '') > params.get('end_date', '9999'):
        st.warning('Opening-date range is reversed.')
        overview = None
    else:
        overview = api('/data/summary', params=params)
    if overview:
        data = overview['data']
        cols = st.columns(4)
        for col, label, value in zip(cols, ['Unique incidents', 'Event observations', 'Priority changes · incidents', 'Observed reopenings · incidents'], [data['total_incidents'], data['total_events'], data['priority_changed_incidents'], data['observed_reopened_incidents']]):
            col.metric(label, f'{value:,}')
        cols = st.columns(3)
        cols[0].metric('Average observations / incident', f"{data['average_events_per_incident']:.2f}")
        avg = data['average_resolution_hours']
        cols[1].metric('Latest-summary resolution · hours', f'{avg:.2f}' if avg is not None else 'Unavailable')
        cols[2].metric('Source made_sla changes · incidents', f"{data['made_sla_changed_incidents']:,}")
        st.caption(f"Resolution: {data['resolution_valid_incidents']:,} nonmissing, nonnegative latest-summary durations; {data['resolution_excluded_incidents']:,} excluded. Descriptive only. Reopenings use any recorded event counter > 0.")
        charts = st.columns(2)
        for target, endpoint, x, title in [(charts[0], '/analytics/priorities', 'priority', 'Incidents by latest observed priority'), (charts[1], '/analytics/states', 'state', 'Incidents by latest observed state')]:
            response = api(endpoint, params=params)
            if response and response['data']:
                frame = pd.DataFrame(response['data'])
                figure = px.bar(frame, x=x, y='incident_count', title=title, color_discrete_sequence=['#3778c2'], labels={'incident_count':'Unique incidents', x:x.replace('_',' ').title()})
                target.plotly_chart(figure, width='stretch')
        trend = api('/analytics/trends', params=params)
        if trend and trend['data']:
            figure = px.line(pd.DataFrame(trend['data']), x='month', y='incident_count', markers=True, title='Incident openings by calendar month', labels={'month':'Opening month (timezone unspecified)', 'incident_count':'Unique incidents'})
            st.plotly_chart(figure, width='stretch')
        with st.expander('Data quality and selection audit'):
            diagnostics = api('/analytics/query', {'tool':'diagnostics'})
            if diagnostics: st.json(diagnostics['data'])

with explorer:
    st.subheader('Inspect an actual incident')
    with st.form('incident_lookup'):
        incident_id = st.text_input('Incident identifier', value='INC0000045').strip().upper()
        lookup = st.form_submit_button('Load complete recorded history')
    if lookup:
        result = api('/incidents/' + incident_id)
        if result:
            data, summary = result['data'], result['data']['summary']
            if summary['latest_selection_tied']:
                st.warning('Latest observed selection has tied candidates. Review the tie audit.')
            st.markdown('**Latest observed summary**')
            st.json(summary, expanded=False)
            st.caption('Summary is the selected observation, not independent final ground truth.')
            frame = pd.DataFrame(data['history'])
            frame['observed_priority_change'] = frame.priority.ne(frame.priority.shift()) & frame.index.to_series().ne(0)
            frame['observed_state_change'] = frame.incident_state_clean.ne(frame.incident_state_clean.shift()) & frame.index.to_series().ne(0)
            st.markdown(f"**Complete recorded event history · {data['event_count']} observations**")
            st.dataframe(frame, width='stretch', hide_index=True)
            timeline = frame[['source_row_id','sys_updated_at','incident_state_clean','priority','observed_priority_change','observed_state_change']]
            st.markdown('**Observed state and priority changes**')
            st.dataframe(timeline, width='stretch', hide_index=True)
