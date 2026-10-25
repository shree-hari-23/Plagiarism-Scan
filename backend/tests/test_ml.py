import pytest
from unittest.mock import MagicMock, patch
from app.core.ml import Chunker, EmbeddingModel
from app.core.fingerprint import LexicalFingerprint

def test_chunker():
    chunker = Chunker(chunk_size=10, overlap=2)
    text = "Hello World This Is A Test"
    chunks = chunker.chunk_text(text)
    assert len(chunks) > 0
    assert "Hello" in chunks[0]

def test_fingerprint():
    fp = LexicalFingerprint(num_perm=16)
    text1 = "The quick brown fox jumps over the lazy dog"
    text2 = "The quick brown fox jumps over the lazy dog"
    text3 = "Different text entirely"
    
    sig1 = fp.generate_fingerprint(text1)
    sig2 = fp.generate_fingerprint(text2)
    sig3 = fp.generate_fingerprint(text3)
    
    assert sig1 == sig2
    assert sig1 != sig3

@patch("fastembed.TextEmbedding")
def test_embedding_model(mock_te):
    import numpy as np
    mock_model = MagicMock()
    mock_arr1 = np.array([0.1, 0.2])
    mock_arr2 = np.array([0.3, 0.4])
    mock_model.embed.return_value = [mock_arr1, mock_arr2]
    mock_te.return_value = mock_model
    
    model = EmbeddingModel.get_instance()
    model._model = mock_model
    embeddings = model.encode(["test chunk"])
    
    assert len(embeddings) == 2
    assert embeddings[0] == [0.1, 0.2]

@patch("qdrant_client.QdrantClient")
def test_vector_db(mock_client_cls):
    from app.db.vector import VectorDB
    
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    
    vdb = VectorDB()
    vdb.client = mock_client
    vdb.upsert_chunks(1, ["chunk1"], [[0.1, 0.2]])
    
    mock_client.upsert.assert_called_once()
