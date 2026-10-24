"""Validated, atomic full ingestion. No input files are modified."""
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import sqlite3
import tempfile
from app.config import ROOT, settings
from app.database.inspection import inspect, column_type, BOOLS, INTS, require, hashes

TABLES = ('incident_events', 'incident_summary', 'latest_selection_ties')
SCHEMA_VERSION = '1'

def ingest(directory=ROOT / 'data', destination=None):
    destination = Path(destination or settings.db)
    result, frames, report = inspect(directory)
    destination.parent.mkdir(parents=True, exist_ok=True)
    # A valid import with the same hashes can be reused. Invalid existing DBs fail loudly.
    if destination.exists():
        with sqlite3.connect(destination) as conn:
            meta = dict(conn.execute('SELECT key,value FROM import_metadata'))
            if meta.get('sha256') == json.dumps(result['sha256'], sort_keys=True) and meta.get('schema_version') == SCHEMA_VERSION:
                require(conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok', 'Existing SQLite database failed integrity check')
                require(not conn.execute('PRAGMA foreign_key_check').fetchall(), 'Existing database has foreign-key violations')
                for table, frame in zip(TABLES, frames):
                    require(conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == len(frame), f'Existing {table} count mismatch')
                return {'status': 'unchanged', 'counts': result['counts'], 'sha256': result['sha256']}
    handle, filename = tempfile.mkstemp(prefix='opspilot-', suffix='.db', dir=destination.parent)
    os.close(handle)
    staging = Path(filename)
    try:
        conn = sqlite3.connect(staging)
        try:
            conn.execute('PRAGMA foreign_keys=ON')
            with conn:
                # Summary is inserted first; its selected event relationship is verified after insertion.
                for idx in (1, 0, 2):
                    table, frame = TABLES[idx], frames[idx]
                    definitions = []
                    for column in frame:
                        suffix = ' PRIMARY KEY NOT NULL' if (table == 'incident_events' and column == 'source_row_id') or (table == 'incident_summary' and column == 'number') else ''
                        if column in BOOLS:
                            suffix += f' CHECK("{column}" IN (0,1) OR "{column}" IS NULL)'
                        definitions.append(f'"{column}" {column_type(column)}{suffix}')
                    if table != 'incident_summary':
                        definitions.append('FOREIGN KEY(number) REFERENCES incident_summary(number)')
                    if table == 'latest_selection_ties':
                        definitions.append('FOREIGN KEY(source_row_id) REFERENCES incident_events(source_row_id)')
                    conn.execute(f'CREATE TABLE {table} (' + ','.join(definitions) + ')')
                    converted = frame.copy()
                    for column in frame:
                        if column in BOOLS:
                            converted[column] = frame[column].map({'True': 1, 'False': 0, '': None})
                        elif column in INTS:
                            converted[column] = frame[column].map(lambda v: int(v) if v else None)
                        elif column == 'resolution_hours_latest_record':
                            converted[column] = frame[column].map(lambda v: float(v) if v else None)
                        else:
                            converted[column] = frame[column].map(lambda v: v if v != '' else None)
                    sql = f'INSERT INTO {table} VALUES (' + ','.join('?' for _ in frame) + ')'
                    records = converted.astype(object).where(converted.notna(), None)
                    for start in range(0, len(records), 5000):
                        conn.executemany(sql, records.iloc[start:start+5000].itertuples(index=False, name=None))
                for name, table, columns in [
                    ('idx_events_number_time', 'incident_events', 'number,sys_updated_at,sys_mod_count,source_row_id'),
                    ('idx_summary_priority', 'incident_summary', 'latest_observed_priority'),
                    ('idx_summary_state', 'incident_summary', 'latest_observed_incident_state_clean'),
                    ('idx_summary_opened', 'incident_summary', 'opened_at'),
                    ('idx_summary_group', 'incident_summary', 'assignment_group'),
                    ('idx_summary_selected', 'incident_summary', 'source_row_id')]:
                    conn.execute(f'CREATE INDEX {name} ON {table}({columns})')
                conn.execute('CREATE TABLE import_metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
                metadata = {'schema_version': SCHEMA_VERSION, 'sha256': json.dumps(result['sha256'], sort_keys=True), 'imported_at_utc': datetime.now(timezone.utc).isoformat(), 'counts': json.dumps(result['counts']), 'quality_report': json.dumps(report)}
                conn.executemany('INSERT INTO import_metadata VALUES (?,?)', metadata.items())
                for table, frame in zip(TABLES, frames):
                    require(conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == len(frame), f'{table}: inserted count mismatch')
                require(conn.execute('SELECT COUNT(*) FROM incident_summary s LEFT JOIN incident_events e ON s.number=e.number AND s.source_row_id=e.source_row_id WHERE e.source_row_id IS NULL').fetchone()[0] == 0, 'Invalid summary selected-event references')
                require(not conn.execute('PRAGMA foreign_key_check').fetchall(), 'Foreign-key check failed')
                require(conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok', 'Integrity check failed')
                require(hashes(Path(directory)) == result['sha256'], 'Source files changed during import')
        finally:
            conn.close()
        os.replace(staging, destination)
    finally:
        staging.unlink(missing_ok=True)
    return {'status': 'imported', 'counts': result['counts'], 'sha256': result['sha256']}
