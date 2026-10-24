import argparse
import json
from app.config import ROOT
from app.database.inspection import inspect, schema_markdown

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Validate all authoritative inputs without changing them')
    parser.add_argument('--write-schema', action='store_true', help='Write docs/DATA_SCHEMA.md only')
    args = parser.parse_args()
    result, _, _ = inspect()
    if args.write_schema:
        (ROOT / 'docs/DATA_SCHEMA.md').write_text(schema_markdown(result), encoding='utf-8')
    print(json.dumps(result, indent=2))
