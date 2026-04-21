import argparse
import json
import time
from pathlib import Path
from typing import Dict

import numpy as np

from backend.services.faiss_search import FAISSEmbeddingIndex


def _normalize(vec: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vec)
    if norm == 0:
        return vec
    return vec / norm


def _build_random_embeddings(num_embeddings: int, dim: int) -> list:
    rows = []
    for i in range(num_embeddings):
        emb = _normalize(np.random.randn(dim).astype(np.float32))
        rows.append((i, emb))
    return rows


def _build_random_queries(num_queries: int, dim: int) -> list:
    return [_normalize(np.random.randn(dim).astype(np.float32)) for _ in range(num_queries)]


def _loop_search(query: np.ndarray, db_embeddings: list, threshold: float):
    best_score = -1.0
    best_match = None
    for student_id, db_emb in db_embeddings:
        score = float(np.dot(query, db_emb))
        if score > best_score:
            best_score = score
            best_match = student_id
    if best_score >= threshold:
        return best_match, best_score
    return None, best_score


def run_benchmark(num_embeddings: int, num_queries: int, dim: int, threshold: float) -> Dict:
    db_embeddings = _build_random_embeddings(num_embeddings, dim)
    queries = _build_random_queries(num_queries, dim)

    # Loop baseline
    t0 = time.perf_counter()
    loop_results = [_loop_search(q, db_embeddings, threshold) for q in queries]
    loop_elapsed = time.perf_counter() - t0

    # FAISS single-query mode
    faiss_index = FAISSEmbeddingIndex(dim=dim)
    faiss_index.build(db_embeddings)

    t1 = time.perf_counter()
    faiss_single_results = [faiss_index.search(q, top_k=1, threshold=threshold) for q in queries]
    faiss_single_elapsed = time.perf_counter() - t1

    # FAISS batch-query mode
    t2 = time.perf_counter()
    faiss_batch_results = faiss_index.search_batch(queries, top_k=1, threshold=threshold)
    faiss_batch_elapsed = time.perf_counter() - t2

    # Quick consistency checks to catch accidental regressions.
    assert len(loop_results) == len(faiss_single_results) == len(faiss_batch_results)

    loop_ms = (loop_elapsed / num_queries) * 1000
    faiss_single_ms = (faiss_single_elapsed / num_queries) * 1000
    faiss_batch_ms = (faiss_batch_elapsed / num_queries) * 1000

    return {
        "num_embeddings": num_embeddings,
        "num_queries": num_queries,
        "dimension": dim,
        "threshold": threshold,
        "loop_total_s": round(loop_elapsed, 6),
        "faiss_single_total_s": round(faiss_single_elapsed, 6),
        "faiss_batch_total_s": round(faiss_batch_elapsed, 6),
        "loop_per_query_ms": round(loop_ms, 6),
        "faiss_single_per_query_ms": round(faiss_single_ms, 6),
        "faiss_batch_per_query_ms": round(faiss_batch_ms, 6),
        "speedup_single_vs_loop": round(loop_ms / faiss_single_ms, 3) if faiss_single_ms > 0 else None,
        "speedup_batch_vs_loop": round(loop_ms / faiss_batch_ms, 3) if faiss_batch_ms > 0 else None,
        "speedup_batch_vs_single": round(faiss_single_ms / faiss_batch_ms, 3) if faiss_batch_ms > 0 else None,
    }


def main():
    parser = argparse.ArgumentParser(description="Benchmark recognize latency: Loop vs FAISS single vs FAISS batch")
    parser.add_argument("--embeddings", type=int, default=1000, help="Number of embeddings in database")
    parser.add_argument("--queries", type=int, default=1000, help="Number of query embeddings")
    parser.add_argument("--dim", type=int, default=512, help="Embedding dimension")
    parser.add_argument("--threshold", type=float, default=0.68, help="Acceptance threshold")
    parser.add_argument("--output", default="benchmarks/p2_latency.json", help="Path to write JSON report")
    args = parser.parse_args()

    result = run_benchmark(
        num_embeddings=args.embeddings,
        num_queries=args.queries,
        dim=args.dim,
        threshold=args.threshold,
    )

    print("\n=== P2 LATENCY BENCHMARK ===")
    print(f"Embeddings : {result['num_embeddings']}")
    print(f"Queries    : {result['num_queries']}")
    print(f"Loop       : {result['loop_per_query_ms']:.6f} ms/query")
    print(f"FAISS one  : {result['faiss_single_per_query_ms']:.6f} ms/query")
    print(f"FAISS batch: {result['faiss_batch_per_query_ms']:.6f} ms/query")
    print(f"Speedup single vs loop: {result['speedup_single_vs_loop']}x")
    print(f"Speedup batch vs loop : {result['speedup_batch_vs_loop']}x")
    print(f"Speedup batch vs one  : {result['speedup_batch_vs_single']}x")

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Saved report: {out_path}")


if __name__ == "__main__":
    main()
