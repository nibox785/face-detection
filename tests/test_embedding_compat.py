import pickle

import numpy as np

from backend.database.db import EMBEDDING_MAGIC, _deserialize_embedding, _serialize_embedding


def test_serialize_embedding_uses_binary_magic_prefix():
    embedding = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    blob = _serialize_embedding(embedding)

    assert blob.startswith(EMBEDDING_MAGIC)


def test_deserialize_embedding_supports_new_binary_format():
    embedding = np.array([0.4, 0.5, 0.6], dtype=np.float32)
    blob = _serialize_embedding(embedding)

    restored = _deserialize_embedding(blob)

    assert restored.dtype == np.float32
    assert np.allclose(restored, embedding)


def test_deserialize_embedding_supports_legacy_pickle_format():
    embedding = np.array([0.7, 0.8, 0.9], dtype=np.float32)
    legacy_blob = pickle.dumps(embedding)

    restored = _deserialize_embedding(legacy_blob)

    assert restored.dtype == np.float32
    assert np.allclose(restored, embedding)
