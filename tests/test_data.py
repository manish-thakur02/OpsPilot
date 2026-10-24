from app.config import ROOT
from app.database.inspection import hashes, load_csv, DataIntegrityError
import pytest

def test_authoritative_invariants(inspected):
    import json
    result, (events, summary, ties), _ = inspected
    assert len(events) == 141712
    assert events.number.nunique() == len(summary) == 24918
    assert summary.number.is_unique and events.source_row_id.is_unique
    assert summary.event_count.astype(int).sum() == len(events)
    assert len(ties) == 0
    assert result['sha256'] == hashes(ROOT / 'data')
    assert result['sha256'] == json.loads((ROOT / 'docs/INPUT_HASHES.json').read_text(encoding='utf-8'))

def test_malformed_csv_fails(tmp_path):
    path = tmp_path / 'bad.csv'
    path.write_text('a,b\n1,2,3\n', encoding='utf-8')
    with pytest.raises(DataIntegrityError, match='field count'):
        load_csv(path)
