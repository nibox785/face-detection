"""
Unit tests for FAISS embedding index integration.
"""

import sys
import pytest
import numpy as np

sys.path.insert(0, '/d/face-detection')

from backend.services.faiss_search import FAISSEmbeddingIndex


class TestFAISSEmbeddingIndex:
    """Test suite for FAISSEmbeddingIndex"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.dim = 512
        self.index = FAISSEmbeddingIndex(dim=self.dim)
        
        # Create sample embeddings (normalized)
        self.embeddings = []
        for i in range(10):
            emb = np.random.randn(self.dim).astype(np.float32)
            emb = emb / np.linalg.norm(emb)
            self.embeddings.append((i, emb))
    
    def test_initialization(self):
        """Test FAISS index initialization"""
        assert self.index.dim == self.dim
        assert self.index.is_built is False
        assert len(self.index.student_ids) == 0
    
    def test_build_index(self):
        """Test building index from embeddings"""
        self.index.build(self.embeddings)
        
        assert self.index.is_built is True
        assert len(self.index.student_ids) == 10
        assert self.index.index.ntotal == 10
    
    def test_search_single(self):
        """Test searching for single embedding"""
        self.index.build(self.embeddings)
        
        # Query with the first embedding (should match itself with high score)
        query = self.embeddings[0][1]
        student_id, score = self.index.search(query, top_k=1, threshold=0.5)
        
        assert student_id == 0
        assert score > 0.9  # High similarity with itself
    
    def test_search_threshold(self):
        """Test threshold filtering"""
        self.index.build(self.embeddings)
        
        # Query with a random embedding (should not match)
        random_emb = np.random.randn(self.dim).astype(np.float32)
        random_emb = random_emb / np.linalg.norm(random_emb)
        
        student_id, score = self.index.search(random_emb, top_k=1, threshold=0.9)
        
        # Should return None because similarity below threshold
        assert student_id is None
        assert score < 0.9
    
    def test_batch_search(self):
        """Test batch search"""
        self.index.build(self.embeddings)
        
        queries = [self.embeddings[i][1] for i in range(3)]
        results = self.index.batch_search(queries, top_k=1, threshold=0.5)
        
        assert len(results) == 3
        assert all(isinstance(r, tuple) for r in results)
        assert results[0][0] == self.embeddings[0][0]
        assert results[1][0] == self.embeddings[1][0]
        assert results[2][0] == self.embeddings[2][0]
    
    def test_empty_embeddings(self):
        """Test with empty embeddings"""
        self.index.build([])
        
        assert self.index.is_built is False
        
        random_emb = np.random.randn(self.dim).astype(np.float32)
        student_id, score = self.index.search(random_emb)
        
        assert student_id is None
        assert score == 0.0
    
    def test_index_info(self):
        """Test getting index information"""
        self.index.build(self.embeddings)
        
        info = self.index.get_index_info()
        
        assert info["is_built"] is True
        assert info["dimension"] == self.dim
        assert info["num_embeddings"] == 10
        assert info["index_size"] == 10
    
    def test_reshape_query(self):
        """Test automatic reshaping of 1D query"""
        self.index.build(self.embeddings)
        
        # 1D query should be reshaped to (1, dim)
        query = self.embeddings[0][1]  # Shape (512,)
        student_id, score = self.index.search(query, top_k=1, threshold=0.5)
        
        assert student_id == 0
        assert score > 0.9


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
