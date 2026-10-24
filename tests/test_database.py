import sqlite3
from app.database.ingest import ingest
from app.database.connection import readonly, DatabaseUnavailable
from app.database.inspection import hashes
from app.config import ROOT
import pytest

def test_full_import_and_idempotence(full_db):
    original = hashes()
    assert ingest(destination=full_db)['status'] == 'unchanged'
    with readonly(full_db) as conn:
        assert conn.execute('SELECT COUNT(*),COUNT(DISTINCT number) FROM incident_events').fetchone()[:] == (141712, 24918)
        assert conn.execute('SELECT COUNT(*) FROM incident_summary').fetchone()[0] == 24918
        assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert not conn.execute('PRAGMA foreign_key_check').fetchall()
        indexes = {r[1] for r in conn.execute('PRAGMA index_list(incident_summary)')}
        assert {'idx_summary_priority', 'idx_summary_state', 'idx_summary_opened'} <= indexes
        assert conn.execute('SELECT COUNT(*) FROM incident_events WHERE cmdb_ci IS NULL').fetchone()[0] == 141267
        assert conn.execute('SELECT DISTINCT active FROM incident_events').fetchall()
    assert original == hashes(ROOT / 'data')

def test_read_only_and_missing_database(full_db, tmp_path):
    with pytest.raises(DatabaseUnavailable):
        with readonly(tmp_path / 'missing.db'):
            pass
    with pytest.raises(DatabaseUnavailable):
        with readonly(full_db) as conn:
            conn.execute('DELETE FROM incident_events')
