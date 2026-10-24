"""Read-only validation of authoritative files; never repairs or writes them."""
import csv
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path
import pandas as pd
from app.config import ROOT

FILES = ('incident_events_clean.csv', 'incident_summary.csv', 'latest_selection_ties.csv', 'data_quality_report.json')
INTS = {'source_row_id', 'reassignment_count', 'reopen_count', 'sys_mod_count', 'event_count', 'matching_rows_at_latest_selection_key', 'priority_distinct_count', 'made_sla_distinct_count'}
BOOLS = {'active', 'made_sla', 'knowledge', 'u_priority_confirmation', 'incident_state_unknown', 'latest_observed_made_sla_raw', 'latest_selection_tied', 'first_observed_made_sla_raw', 'priority_changed', 'made_sla_changed', 'resolution_before_open_flag'}
DATES = {'opened_at', 'sys_created_at', 'sys_updated_at', 'resolved_at', 'closed_at', 'first_observed_update_at', 'last_observed_update_at'}
RENAMES = {'latest_observed_priority': 'priority', 'latest_observed_incident_state_raw': 'incident_state', 'latest_observed_incident_state_clean': 'incident_state_clean', 'latest_observed_made_sla_raw': 'made_sla'}

class DataIntegrityError(ValueError):
    pass

def require(condition, message):
    if not condition:
        raise DataIntegrityError(message)

def hashes(directory=ROOT / 'data'):
    return {name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in FILES}

def column_type(column):
    return 'INTEGER' if column in INTS | BOOLS else 'REAL' if column == 'resolution_hours_latest_record' else 'TEXT'

def load_csv(path):
    # Strict decoding, width checks and explicit strings prevent pandas coercion.
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.reader(stream, strict=True)
        header = next(reader)
        require(len(header) == len(set(header)), f'{path.name}: duplicate columns')
        for line, row in enumerate(reader, 2):
            require(len(row) == len(header), f'{path.name}:{line}: incorrect field count')
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, encoding='utf-8-sig')
    for column in frame:
        populated = frame.loc[frame[column] != '', column]
        if column in INTS:
            require(populated.str.fullmatch(r'\d+').all(), f'{path.name}: invalid integer {column}')
        elif column in BOOLS:
            require(populated.isin(['True', 'False']).all(), f'{path.name}: invalid Boolean {column}')
        elif column in DATES:
            parsed = pd.to_datetime(populated, format='%Y-%m-%d %H:%M:%S', errors='coerce')
            require(parsed.notna().all() and populated.str.fullmatch(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}').all(), f'{path.name}: invalid timestamp {column}')
        elif column == 'resolution_hours_latest_record':
            require(all(math.isfinite(float(x)) for x in populated), f'{path.name}: invalid duration')
    return frame

def inspect(directory=ROOT / 'data', expected=True):
    directory = Path(directory)
    require(all((directory / f).is_file() for f in FILES), 'One or more of the four authoritative inputs are missing')
    before = hashes(directory)
    events, summary, ties = [load_csv(directory / name) for name in FILES[:3]]
    report = json.loads((directory / FILES[3]).read_text(encoding='utf-8-sig'))
    require(events.source_row_id.is_unique, 'Duplicate event source_row_id')
    require(summary.number.is_unique, 'Duplicate summary incident identifier')
    require(events.number.ne('').all() and summary.number.ne('').all(), 'Missing incident identifier')
    require(events.number.str.fullmatch(r'INC\d{7}').all(), 'Invalid incident identifier format')
    require(set(events.number) == set(summary.number), 'Event/summary incident sets differ')
    require(events.source_row_id.ne('').all(), 'Missing source_row_id')
    require(int(summary.event_count.astype(int).sum()) == len(events), 'Summary event_count total differs from event rows')
    actual_counts = events.groupby('number').size()
    require(all(int(r.event_count) == actual_counts[r.number] for r in summary.itertuples()), 'Per-incident event_count mismatch')
    ordered = events.assign(_mod=events.sys_mod_count.astype(int), _id=events.source_row_id.astype(int)).sort_values(['sys_updated_at', '_mod', '_id'])
    latest = ordered.groupby('number', sort=False).tail(1).set_index('number').sort_index()
    indexed = summary.set_index('number').sort_index()
    for column in summary.columns:
        source = RENAMES.get(column, column)
        if source in events.columns and column != 'number':
            require(indexed[column].equals(latest[source].rename(column)), f'Summary selected-event field mismatch: {column}')
    key_counts = events.groupby(['number', 'sys_updated_at', 'sys_mod_count']).size()
    matches = [int(key_counts[(r.number, r.sys_updated_at, r.sys_mod_count)]) for r in summary.itertuples()]
    require(summary.matching_rows_at_latest_selection_key.astype(int).tolist() == matches, 'Tie key counts mismatch')
    tied = {r.number for r, count in zip(summary.itertuples(), matches) if count > 1}
    require(tied == set(summary.loc[summary.latest_selection_tied == 'True', 'number']), 'Tie flags mismatch')
    require(tied == set(ties.number), 'Tie audit identifiers mismatch')
    if len(ties):
        audited = ties.merge(events, on=['number', 'source_row_id', 'sys_updated_at', 'sys_mod_count'], how='left', indicator=True)
        require(audited['_merge'].eq('both').all(), 'Tie audit references missing events')
    for field, change in [('priority', 'priority_changed'), ('made_sla', 'made_sla_changed')]:
        counts = events.groupby('number')[field].nunique()
        require(all(int(getattr(r, field + '_distinct_count')) == counts[r.number] and (getattr(r, change) == 'True') == (counts[r.number] > 1) for r in summary.itertuples()), f'{field} change aggregation mismatch')
    first = ordered.groupby('number', sort=False).head(1).set_index('number').sort_index()
    for derived, original in [('first_observed_update_at', 'sys_updated_at'), ('first_observed_priority', 'priority'), ('first_observed_made_sla_raw', 'made_sla')]:
        require(indexed[derived].equals(first[original].rename(derived)), f'First-observation aggregate mismatch: {derived}')
    require(indexed.last_observed_update_at.equals(latest.sys_updated_at.rename('last_observed_update_at')), 'Last-observation aggregate mismatch')
    for row in summary.itertuples():
        if row.resolved_at:
            hours = (datetime.fromisoformat(row.resolved_at) - datetime.fromisoformat(row.opened_at)).total_seconds() / 3600
            require(bool(row.resolution_hours_latest_record) and math.isclose(float(row.resolution_hours_latest_record), hours, abs_tol=1e-8), f'{row.number}: resolution duration mismatch')
            require((row.resolution_before_open_flag == 'True') == (hours < 0), f'{row.number}: resolution flag mismatch')
        else:
            require(row.resolution_hours_latest_record == '', f'{row.number}: duration exists without resolution timestamp')
    unknown = events.loc[events.incident_state_unknown == 'True', 'incident_state'].value_counts().to_dict()
    require(unknown == report['unexpected_state_values'], 'Unknown-state diagnostics mismatch')
    missing = {c: int(events[c].eq('').sum()) for c in events}
    require(missing == report['missing_values_after_cleaning'], 'JSON missing-value counts differ from CSV')
    counts = {'source_event_rows': len(events), 'clean_event_rows': len(events), 'source_unique_incidents': events.number.nunique(), 'summary_rows': len(summary), 'incidents_with_latest_selection_ties': len(tied), 'incidents_with_priority_changes': int(summary.priority_changed.eq('True').sum()), 'incidents_with_made_sla_changes': int(summary.made_sla_changed.eq('True').sum()), 'incidents_with_resolution_before_open': int(summary.resolution_before_open_flag.eq('True').sum())}
    for key, value in counts.items():
        require(report[key] == value, f'JSON count mismatch: {key}')
    if expected:
        require(len(events) == 141712, f'Expected 141712 events, found {len(events)}')
        require(len(summary) == events.number.nunique() == 24918, 'Expected 24918 unique incidents and summary rows')
    require(before == hashes(directory), 'Input files changed during inspection')
    result = {'counts': counts, 'sha256': before, 'encoding': 'UTF-8 (UTF-8-SIG reader accepts optional BOM)', 'nulls': 'empty CSV cells', 'timestamps': 'YYYY-MM-DD HH:MM:SS; timezone unspecified', 'priorities': sorted(events.priority.unique().tolist()), 'states': sorted(events.incident_state_clean.unique().tolist()), 'schemas': {name: {c: column_type(c) for c in frame} for name, frame in zip(FILES[:3], (events, summary, ties))}}
    return result, (events, summary, ties), report

def schema_markdown(result):
    text = '# Authoritative data schema\n\nGenerated from the actual UTF-8 inputs by `python -m scripts.inspect_data --write-schema`. The command without that flag is read-only.\n\n'
    text += 'Validated population: 141,712 observations and 24,918 unique incidents. Empty cells are unknown information and become SQL NULL; no imputation. Boolean strings True/False become INTEGER 1/0. Date fields remain ISO TEXT with no assumed timezone. Durations are REAL hours.\n\n'
    for name, schema in result['schemas'].items():
        text += f'## {name}\n\n| Exact column | SQLite type |\n|---|---|\n'
        text += ''.join(f'| `{c}` | {t} |\n' for c, t in schema.items()) + '\n'
    text += '## Files, keys and relationships\n\n`incident_events_clean.csv`: one row per source observation; primary key source_row_id. number references incident_summary.number (many observations to one incident).\n\n`incident_summary.csv`: primary key number; source_row_id references the selected event of the same incident. Latest selection orders sys_updated_at, numeric sys_mod_count, then numeric source_row_id. It is an observed snapshot, not independently verified final ground truth.\n\n`latest_selection_ties.csv`: audit rows for incidents with multiple latest timestamp/update-count matches. Currently header-only (zero ties), retained as an empty table.\n\n`data_quality_report.json`: provenance, missing-value statistics, row counts, unknown-state diagnostics, semantic limitations, and output manifest. Its original source_file is provenance from another machine, not an input dependency.\n\n'
    text += '## Actual categories\n\nPriorities: ' + ', '.join(result['priorities']) + '.\n\nNormalized states: ' + ', '.join(result['states']) + '.\n\n'
    text += '## Metric definitions and limitations\n\nIncident counts, priority/state distributions, assignment groups and opening trends use the summary table. Trend periods are calendar months of summary opened_at; date filters are inclusive opening dates. Event counts count all observations, including repeated observations. Observed priority/SLA-field changes count distinct values per incident. Observed reopenings count incidents whose maximum recorded reopen_count exceeds zero. Average events divides observations by incidents in the selected population. Resolution duration uses only nonmissing, nonnegative latest-summary durations; report the denominator and exclusions. No duration is a forecast or an as-of measure.\n\nmade_sla remains a source Boolean: neither value is labelled breach/compliance. The five raw -100 states are flagged Unknown. Missing data is intentional; 1,556 summaries lack resolution durations. resolved_at and closed_at may contain future completion information even in early observations; no historical/as-of metrics are implemented. No timezone is established. The dataset contains anonymized structured fields, not real narratives or organizational policy. Synthetic demonstration policy does not establish historical compliance.\n\n## Input SHA-256\n\n'
    text += ''.join(f'- `{k}`: `{v}`\n' for k, v in result['sha256'].items())
    return text
