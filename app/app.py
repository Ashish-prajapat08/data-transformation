"""Streamlit V0 migration dashboard; all business operations go through FastAPI."""
import json
import os
import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv('FASTAPI_URL', 'http://127.0.0.1:8000').rstrip('/')
st.set_page_config(page_title='Data Migration Agent', layout='wide')
st.title('AI Data Migration & Transformation Agent')
st.caption('Upload business data, review the plan, resolve uncertainties, and export target-ready CSV.')

# A shared password gate for the hosted demo. Local usage is unchanged when unset.
_demo_password = os.getenv('APP_PASSWORD', '')
if _demo_password:
    import hashlib
    import hmac
    _fingerprint = hashlib.sha256(_demo_password.encode()).hexdigest()
    if st.session_state.get('demo_access') != _fingerprint:
        with st.form('demo_login'):
            _entered = st.text_input('Demo password', type='password')
            _submitted = st.form_submit_button('Open demo')
        if _submitted:
            if hmac.compare_digest(_entered.encode(), _demo_password.encode()):
                st.session_state['demo_access'] = _fingerprint
                st.rerun()
            else:
                st.error('Incorrect demo password.')
        st.stop()



def api(method, path, **kwargs):
    try:
        response = requests.request(method, BASE_URL + path, timeout=120, **kwargs)
        if not response.ok:
            try:
                detail = response.json().get('detail', 'Request failed')
            except ValueError:
                detail = 'Request failed'
            st.error(str(detail))
            return None
        return response
    except requests.RequestException:
        st.error('Backend unavailable or request timed out. Refresh the run before retrying an action.')
        return None


with st.sidebar:
    st.header('Migration history')
    if st.button('Refresh history'):
        st.rerun()
    response = api('GET', '/migrations')
    history = response.json() if response is not None else []
    selected = st.selectbox('Open a run', ['New run'] + [run['run_id'] for run in history])
    if selected != 'New run':
        st.session_state.run_id = selected
    if st.button('Start another migration'):
        st.session_state.pop('run_id', None)
        st.rerun()

migration_tab, evaluation_tab = st.tabs(['Migration', 'Evaluation'])
with migration_tab:
    with st.expander('Upload and configure', expanded='run_id' not in st.session_state):
        uploaded = st.file_uploader('Source data', type=['csv', 'xlsx'])
        response = api('GET', '/targets')
        target = response.json()[0] if response is not None else {'name': 'Generic', 'fields': [{'name': 'name'}]}
        target_mode = st.radio('Target schema', ['CRM contacts demo', 'Generic JSON schema'], horizontal=True)
        if target_mode == 'Generic JSON schema':
            schema_text = st.text_area('Target schema JSON', value=json.dumps(target, indent=2), height=250,
                help='Fields support name, kind, required, unique, aliases, allowed, default, category_map and date_order.')
        else:
            schema_text = json.dumps(target)
            st.json(target, expanded=False)
        instructions = st.text_area('Migration instructions', max_chars=4000,
            help='LLM mode interprets these instructions. Offline rules mode uses only the declared schema and aliases.')
        st.caption('File and working records are retained locally for review/resume. Delete the run to remove retained data.')
        if st.button('Profile and create migration plan', disabled=uploaded is None):
            try:
                json.loads(schema_text)
            except ValueError:
                st.error('Enter valid target schema JSON.')
            else:
                with st.spinner('Profiling source and planning migration…'):
                    response = api('POST', '/migrations', files={'file': (uploaded.name, uploaded.getvalue())},
                                   data={'target_schema': schema_text, 'instructions': instructions})
                if response is not None:
                    st.session_state.run_id = response.json()['run_id']
                    st.rerun()

    @st.fragment(run_every='2s')
    def render_run():
        if 'run_id' in st.session_state:
            run_id = st.session_state.run_id
            response = api('GET', f'/migrations/{run_id}')
            if response is not None:
                state = response.json()
                st.subheader(f"Run {run_id[:8]} · {state['status'].replace('_', ' ')}")
                profile = state['dataset_profile']
                columns = st.columns(3)
                columns[0].metric('Source rows', profile.get('row_count', 0))
                columns[1].metric('Retries', state['retry_count'])
                validation = state['validation_results']
                columns[2].metric('Migration readiness', f"{validation['readiness'] if validation else 0}%")
                st.caption('Readiness measures valid target cells. Export also requires validation and all reviews to pass.')
                with st.expander('Data profile'):
                    st.json(profile)
                plan = state['migration_plan']
                if plan:
                    st.subheader('Migration plan')
                    st.info(f"Planner: {plan['planner']} · {plan['explanation']}")
                    st.dataframe(pd.DataFrame(plan['mappings']), hide_index=True, use_container_width=True)
                    st.dataframe(pd.DataFrame(plan['tools']), hide_index=True, use_container_width=True)
                    st.caption('Approval permits listed transformations and removal of identical source rows when selected. Schema-declared defaults are applied only by the listed missing-value tool.')
                preview = api('GET', f'/migrations/{run_id}/preview', params={'limit': 200})
                preview_rows = preview.json()['rows'] if preview is not None else []
                with st.expander('Working data preview (first 200 rows)'):
                    st.dataframe(pd.DataFrame([{'row_id': row['row_id'], **row['values']} for row in preview_rows]),
                                 hide_index=True, use_container_width=True)
                pending = [item for item in state['review_items'] if item['decision'] is None]
                if pending:
                    st.subheader('Human review')
                    for item in pending:
                        with st.expander(f"{item['kind']}: {item['column']} · confidence {item['confidence']:.2f}", expanded=True):
                            st.write(item['reason'])
                            st.caption(item['recommendation'])
                            st.write('Affected row IDs:', item['rows'])
                            if item['kind'] == 'entity':
                                evidence = api('GET', f'/migrations/{run_id}/reviews/{item["id"]}/preview')
                                if evidence is not None:
                                    st.dataframe(pd.DataFrame([{'row_id': row['row_id'], **row['values']}
                                                               for row in evidence.json()]), hide_index=True)
                                st.caption('Merge is destructive: it keeps the first row and removes the second entire row. Inspect all fields first. Keep separate preserves both records.')
                            with st.form('review:' + run_id + ':' + item['id']):
                                decision = {'item_id': item['id']}
                                if item['kind'] == 'mapping':
                                    source = st.selectbox('Map from source column', ['Unmapped'] + list(state['source_schema']))
                                    decision.update(action='map', source=None if source == 'Unmapped' else source)
                                elif item['kind'] == 'entity':
                                    action = st.radio('Decision', ['keep', 'merge'], format_func=lambda x: 'Keep separate' if x == 'keep' else 'Merge: keep first row')
                                    decision['action'] = action
                                else:
                                    values = st.text_area('Verified corrections as JSON: {"row_id": "new value"}', value='{}')
                                    decision['action'] = 'correct'
                                submitted = st.form_submit_button('Submit review decision')
                            if submitted:
                                try:
                                    if item['kind'] == 'validation':
                                        decision['values'] = json.loads(values)
                                    response = api('POST', f'/migrations/{run_id}/reviews', json={'decisions': [decision]})
                                    if response is not None:
                                        st.rerun()
                                except ValueError:
                                    st.error('Enter valid corrections JSON.')
                if state['status'] == 'awaiting_plan':
                    left, right = st.columns(2)
                    if left.button('Approve plan and execute', disabled=bool(pending)):
                        with st.spinner('Executing tools, validating and replanning…'):
                            response = api('POST', f'/migrations/{run_id}/approval', json={'approved': True})
                        if response is not None:
                            st.rerun()
                    if right.button('Reject plan'):
                        if api('POST', f'/migrations/{run_id}/approval', json={'approved': False}) is not None:
                            st.rerun()
                if validation:
                    st.subheader('Validation')
                    if validation['passed']:
                        st.success('Target schema validation passed.')
                    else:
                        st.warning('Validation failed. Correct unresolved issues before export.')
                        st.dataframe(pd.DataFrame(validation['issues']), hide_index=True)
                if state['errors']:
                    st.error(' · '.join(state['errors']))
                st.subheader('Execution trace')
                for event in state['trace']:
                    st.write(f"{event['sequence']}. {event['action'].replace('_', ' ')}")
                    st.caption(json.dumps(event['metadata']))
                st.download_button('Download audit trail', json.dumps(state, indent=2),
                                   file_name=f'{run_id}-audit.json', mime='application/json')
                if state['status'] in ('approved', 'executing'):
                    st.info('Agent execution is in progress. Trace updates automatically every two seconds.')
                if state['status'] == 'ready' and st.button('Generate target-ready CSV'):
                    response = api('GET', f'/migrations/{run_id}/export')
                    if response is not None:
                        st.session_state['export:' + run_id] = response.content
                if state['status'] == 'ready' and 'export:' + run_id in st.session_state:
                    st.download_button('Download migration-ready CSV', st.session_state['export:' + run_id],
                                       file_name='migration-ready.csv', mime='text/csv')
                if st.button('Refresh run'):
                    st.rerun()
                if st.checkbox('I want to delete this run and its retained working data'):
                    if st.button('Delete run'):
                        response = api('DELETE', f'/migrations/{run_id}')
                        if response is not None:
                            st.session_state.pop('run_id', None)
                            st.rerun()

    render_run()

with evaluation_tab:
    st.subheader('Repeatable agent evaluation')
    st.write('Runs clean and injected datasets through the configured planner, tools, validation and export. The simulated review policy keeps entity candidates separate and supplies no oracle repairs.')
    if st.button('Run evaluation suite'):
        with st.spinner('Evaluating scenarios…'):
            response = api('POST', '/evaluations')
        if response is not None:
            st.session_state.evaluation = response.json()
    if 'evaluation' in st.session_state:
        result = st.session_state.evaluation
        st.caption(f"{result['planner']} · {result['fixture_count']} fixtures · {result['elapsed_seconds']} seconds")
        st.json(result['metrics'])
        st.dataframe(pd.DataFrame(result['scenarios']), hide_index=True)
        st.download_button('Download measured evaluation', json.dumps(result, indent=2),
                           file_name='evaluation.json', mime='application/json')
