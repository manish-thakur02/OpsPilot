"""Explicit policy indexing. Model downloads happen only in this CLI path."""
import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path
from app.config import ROOT, settings

COLLECTION = 'opspilot_synthetic_policies_v1'

class RetrievalUnavailable(RuntimeError):
    pass

def source_hashes(directory):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(directory).glob('*.md'))}

def load_chunks(directory=ROOT / 'knowledge_base'):
    chunks = []
    for path in sorted(Path(directory).glob('*.md')):
        text = path.read_text(encoding='utf-8')
        if 'Synthetic demonstration policy.' not in text:
            raise ValueError(f'{path.name} lacks required synthetic-policy attribution')
        doc_id_match = re.search(r'DEMO-POL-\d+', text)
        if not doc_id_match:
            raise ValueError(f'{path.name} lacks a document ID')
        doc_id = doc_id_match.group()
        title = text.splitlines()[0].lstrip('# ')
        version = re.search(r'Version ([\d.]+)', text).group(1).rstrip('.')
        parts = re.split(r'^## (.+)$', text, flags=re.MULTILINE)
        for pos in range(1, len(parts), 2):
            heading, body = parts[pos].strip(), parts[pos+1].strip()
            # Paragraph-preserving chunks with repeated title/section context.
            paragraphs = body.split('\n\n')
            blocks, current = [], ''
            for paragraph in paragraphs:
                if current and len(current) + len(paragraph) > 1600:
                    blocks.append(current); current = ''
                current += ('\n\n' if current else '') + paragraph
            if current:
                blocks.append(current)
            for i, block in enumerate(blocks):
                content = f'{title}\nSynthetic demonstration policy. Version {version}.\nSection: {heading}\n{block}'
                chunk_id = hashlib.sha256(f'{path.name}|{heading}|{i}|{content}'.encode()).hexdigest()
                chunks.append({'id': chunk_id, 'text': content, 'metadata': {'source': path.name, 'document_id': doc_id, 'title': title, 'section': heading, 'version': version, 'synthetic': True}})
    if not chunks:
        raise ValueError('No policy sections found')
    return chunks

@lru_cache(maxsize=4)
def embedding_model(model_name, cache, local_only=True):
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(model_name, cache_folder=str(cache), local_files_only=local_only, trust_remote_code=False, device='cpu')

def embed(texts, model=None):
    model = model or embedding_model(settings.embedding_model, str(settings.model_cache), True)
    return model.encode(texts, normalize_embeddings=True, show_progress_bar=False).tolist()

@lru_cache(maxsize=8)
def client(path):
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    return chromadb.PersistentClient(path=str(path), settings=ChromaSettings(anonymized_telemetry=False))

def index_policies(directory=ROOT / 'knowledge_base', destination=None, embedder=None, model_name=None):
    destination = Path(destination or settings.chroma)
    destination.mkdir(parents=True, exist_ok=True)
    chunks = load_chunks(directory)
    signature = {'model': model_name or settings.embedding_model, 'sources': source_hashes(directory), 'chunk_ids': [c['id'] for c in chunks], 'schema_version': 1}
    manifest = destination / 'manifest.json'
    collection = client(str(destination)).get_or_create_collection(COLLECTION, embedding_function=None, metadata={'hnsw:space': 'cosine'})
    if manifest.exists():
        previous = json.loads(manifest.read_text(encoding='utf-8'))
        if previous['model'] != signature['model']:
            raise ValueError('Embedding model changed. Use a new OPSPILOT_CHROMA directory and reindex.')
        if previous == signature and collection.count() == len(chunks):
            return {'status': 'unchanged', 'documents': len(signature['sources']), 'chunks': collection.count(), 'model': signature['model']}
    # Explicit indexing may download model files. Retrieval never downloads.
    if embedder is None:
        model = embedding_model(settings.embedding_model, str(settings.model_cache), False)
        embedder = lambda texts: embed(texts, model)
    vectors = embedder([c['text'] for c in chunks])
    # Invalidate readiness before changing records; a failed update cannot look ready.
    manifest.unlink(missing_ok=True)
    collection.upsert(ids=[c['id'] for c in chunks], documents=[c['text'] for c in chunks], metadatas=[c['metadata'] for c in chunks], embeddings=vectors)
    existing = set(collection.get(include=[])['ids'])
    stale = existing - set(signature['chunk_ids'])
    if stale:
        collection.delete(ids=sorted(stale))
    if collection.count() != len(chunks):
        raise RuntimeError('Policy index count verification failed')
    temporary = destination / 'manifest.json.tmp'
    temporary.write_text(json.dumps(signature, indent=2), encoding='utf-8')
    temporary.replace(manifest)
    return {'status': 'indexed', 'documents': len(signature['sources']), 'chunks': collection.count(), 'model': signature['model']}
