import json
from app.database.ingest import ingest

if __name__ == '__main__':
    print(json.dumps(ingest(), indent=2))
