import json
from pathlib import Path
from app.config import ROOT, settings
from app.rag.ingest import COLLECTION, RetrievalUnavailable, client, embed, source_hashes

class Retriever:
    def __init__(self, destination=None, directory=ROOT / 'knowledge_base', embedder=None, model_name=None):
        self.path = Path(destination or settings.chroma)
        self.directory = Path(directory)
        self.embedder = embedder or embed
        self.model_name = model_name or settings.embedding_model

    def search(self, question, k=3, max_distance=0.55):
        manifest = self.path / 'manifest.json'
        if not manifest.is_file():
            raise RetrievalUnavailable('Policy index missing. Run python -m scripts.ingest_policies once.')
        metadata = json.loads(manifest.read_text(encoding='utf-8'))
        if metadata['model'] != self.model_name or metadata['sources'] != source_hashes(self.directory):
            raise RetrievalUnavailable('Policy index is stale or uses another model. Reindex explicitly.')
        try:
            collection = client(str(self.path)).get_collection(COLLECTION, embedding_function=None)
            if collection.count() != len(metadata['chunk_ids']):
                raise RetrievalUnavailable('Policy index is incomplete. Reindex explicitly.')
            result = collection.query(query_embeddings=self.embedder([question]), n_results=min(k, collection.count()), include=['documents', 'metadatas', 'distances'])
        except RetrievalUnavailable:
            raise
        except Exception as exc:
            raise RetrievalUnavailable('Local policy retrieval failed. Check the cached model and index; no online download is attempted.') from exc
        return [{'id': chunk_id, 'text': text, **meta, 'distance': float(distance), 'citation': f"[{meta['document_id']} § {meta['section']}] ({meta['source']}, v{meta['version']}; synthetic demonstration policy)"} for chunk_id, text, meta, distance in zip(result['ids'][0], result['documents'][0], result['metadatas'][0], result['distances'][0]) if distance <= max_distance]
