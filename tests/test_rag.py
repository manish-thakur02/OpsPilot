import hashlib
import math
import re
import pytest
from app.config import ROOT
from app.rag.ingest import load_chunks, index_policies, RetrievalUnavailable
from app.rag.retriever import Retriever

def fake_embeddings(texts):
    # Isolated deterministic test vectors, never used in production.
    vectors = []
    for text in texts:
        vector = [0.0] * 64
        for token in re.findall(r'[a-z]+', text.lower()):
            vector[int(hashlib.sha256(token.encode()).hexdigest()[:8], 16) % 64] += 1
        norm = math.sqrt(sum(x*x for x in vector)) or 1
        vectors.append([x / norm for x in vector])
    return vectors

def test_chunk_metadata_and_required_attribution(tmp_path):
    chunks = load_chunks()
    assert len({c['metadata']['document_id'] for c in chunks}) == 8
    assert len({c['id'] for c in chunks}) == len(chunks)
    assert all(c['metadata']['synthetic'] and c['metadata']['section'] and c['metadata']['version'] for c in chunks)
    assert chunks == load_chunks()
    (tmp_path / 'unsafe.md').write_text('# Missing attribution\n## Rules\ntext', encoding='utf-8')
    with pytest.raises(ValueError, match='synthetic-policy'):
        load_chunks(tmp_path)

def test_persistence_citations_repeatability_and_no_match(tmp_path):
    path = tmp_path / 'vectors'
    first = index_policies(destination=path, embedder=fake_embeddings, model_name='test-hash-v1')
    def must_not_embed(_):
        raise AssertionError('Idempotent indexing regenerated embeddings')
    second = index_policies(destination=path, embedder=must_not_embed, model_name='test-hash-v1')
    assert first['chunks'] == second['chunks'] and second['status'] == 'unchanged'
    retriever = Retriever(destination=path, embedder=fake_embeddings, model_name='test-hash-v1')
    passages = retriever.search('critical incident escalation', max_distance=2)
    assert passages and all(p['citation'] and p['source'] and p['synthetic'] for p in passages)
    assert retriever.search('no possible match', max_distance=-1) == []
    with pytest.raises(ValueError, match='model changed'):
        index_policies(destination=path, embedder=fake_embeddings, model_name='different-model')

def test_missing_and_stale_index(tmp_path):
    with pytest.raises(RetrievalUnavailable, match='missing'):
        Retriever(destination=tmp_path).search('escalation')
    kb = tmp_path / 'kb'; kb.mkdir()
    text = (ROOT / 'knowledge_base/03_escalation.md').read_text(encoding='utf-8')
    (kb / 'policy.md').write_text(text, encoding='utf-8')
    index_policies(directory=kb, destination=tmp_path/'vectors', embedder=fake_embeddings, model_name='test')
    (kb / 'policy.md').write_text(text + '\nChanged policy.', encoding='utf-8')
    with pytest.raises(RetrievalUnavailable, match='stale'):
        Retriever(destination=tmp_path/'vectors', directory=kb, embedder=fake_embeddings, model_name='test').search('escalation')

def test_default_threshold_rejects_weak_matches(tmp_path):
    # Cosine distance 0.6 must not pass, even when generic policy words overlap.
    index_policies(destination=tmp_path, embedder=lambda texts: [[1.0,0.0] for _ in texts], model_name='threshold-test')
    weak = Retriever(destination=tmp_path, embedder=lambda texts: [[0.4,0.916515] for _ in texts], model_name='threshold-test')
    assert weak.search('generic demonstration policy words') == []
    strong = Retriever(destination=tmp_path, embedder=lambda texts: [[0.8,0.6] for _ in texts], model_name='threshold-test')
    assert strong.search('supported policy topic')
