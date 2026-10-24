import pytest
from app.config import ROOT
from app.database.inspection import inspect

@pytest.fixture(scope='session')
def inspected():
    return inspect(ROOT / 'data')

@pytest.fixture(scope='session')
def full_db(tmp_path_factory):
    from app.database.ingest import ingest
    db = tmp_path_factory.mktemp('full') / 'incidents.db'
    assert ingest(destination=db)['status'] == 'imported'
    return db
