import json
from app.rag.ingest import index_policies

if __name__ == '__main__':
    print(json.dumps(index_policies(), indent=2))
