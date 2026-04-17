"""
Benchmark script để so sánh FAISS vs Loop Cosine search performance.
Used to validate Phase 2.1 FAISS integration.
"""

import time
import numpy as np
import sys
sys.path.insert(0, '/d/face-detection')

from backend.services.faiss_search import FAISSEmbeddingIndex


def benchmark_faiss_vs_loop(num_embeddings: int = 100, num_queries: int = 1000):
    """Compare performance of FAISS search vs loop cosine similarity."""
    
    print(f"\n{'='*70}")
    print(f"Benchmark: FAISS vs Loop Cosine | embeddings={num_embeddings}, queries={num_queries}")
    print(f"{'='*70}\n")
    
    # Generate random embeddings (normalized to unit vectors)
    dim = 512
    db_embeddings = []
    for i in range(num_embeddings):
        emb = np.random.randn(dim).astype(np.float32)
        emb = emb / np.linalg.norm(emb)  # Normalize
        db_embeddings.append((i, emb))
    
    query_embeddings = []
    for i in range(num_queries):
        emb = np.random.randn(dim).astype(np.float32)
        emb = emb / np.linalg.norm(emb)  # Normalize
        query_embeddings.append(emb)
    
    # ==================== FAISS Search ====================
    print("🔍 Testing FAISS search...")
    try:
        faiss_index = FAISSEmbeddingIndex(dim=512)
        faiss_index.build(db_embeddings)
        
        start_time = time.time()
        faiss_results = []
        for query_emb in query_embeddings:
            result = faiss_index.search(query_emb, top_k=1, threshold=0.68)
            faiss_results.append(result)
        faiss_time = time.time() - start_time
        
        avg_faiss = (faiss_time / num_queries) * 1000  # Convert to ms
        print(f"✅ FAISS: {faiss_time:.4f}s | Avg per query: {avg_faiss:.4f}ms")
        
    except Exception as e:
        print(f"❌ FAISS failed: {str(e)}")
        avg_faiss = None
        faiss_results = None
    
    # ==================== Loop Cosine Search ====================
    print(f"🔍 Testing Loop cosine search...")
    
    def cosine_similarity(emb1, emb2):
        return float(np.dot(emb1, emb2))
    
    start_time = time.time()
    loop_results = []
    for query_emb in query_embeddings:
        best_score = -1.0
        best_match = None
        for student_id, db_emb in db_embeddings:
            score = cosine_similarity(query_emb, db_emb)
            if score > best_score:
                best_score = score
                best_match = student_id
        
        if best_score >= 0.68:
            loop_results.append((best_match, best_score))
        else:
            loop_results.append((None, best_score))
    
    loop_time = time.time() - start_time
    avg_loop = (loop_time / num_queries) * 1000  # Convert to ms
    print(f"✅ Loop cosine: {loop_time:.4f}s | Avg per query: {avg_loop:.4f}ms")
    
    # ==================== Results Comparison ====================
    print(f"\n{'='*70}")
    print("📊 Results Comparison:")
    print(f"{'='*70}")
    print(f"Loop cosine:  {loop_time:.4f}s ({avg_loop:.4f}ms per query)")
    
    if avg_faiss:
        print(f"FAISS:        {faiss_time:.4f}s ({avg_faiss:.4f}ms per query)")
        speedup = avg_loop / avg_faiss
        print(f"\n⚡ Speedup: {speedup:.1f}x faster with FAISS")
    
    print(f"{'='*70}\n")


if __name__ == "__main__":
    # Test with different scales
    print("\n🧪 Phase 2.1 FAISS Integration Benchmark\n")
    
    benchmark_faiss_vs_loop(num_embeddings=10, num_queries=100)
    benchmark_faiss_vs_loop(num_embeddings=100, num_queries=1000)
    benchmark_faiss_vs_loop(num_embeddings=1000, num_queries=500)
    
    print("✅ Benchmark completed!")
