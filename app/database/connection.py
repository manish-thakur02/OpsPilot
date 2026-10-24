from contextlib import contextmanager
from pathlib import Path
import sqlite3
from app.config import settings

class DatabaseUnavailable(RuntimeError):
    pass

@contextmanager
def readonly(path=None):
    path = Path(path or settings.db)
    if not path.is_file():
        raise DatabaseUnavailable('Database not initialized. Run python -m scripts.init_db.')
    connection = None
    try:
        connection = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA query_only=ON')
        connection.execute('PRAGMA foreign_keys=ON')
        yield connection
    except sqlite3.Error as exc:
        raise DatabaseUnavailable('SQLite query failed; check database initialization and integrity.') from exc
    finally:
        if connection:
            connection.close()
