"""Command-line utility to run regression-style RAG evaluations.

Usage:
    python tools/rag_eval.py --db my_database --cases eval_cases.json

The cases file may be JSON or YAML and should be a list of objects with the
following fields (all optional except `query`):
    {
        "query": "How do I reset the router?",
        "expected_keywords": ["reset", "router"],
        "expected_doc": "network_manual.pdf",
        "filters": {"doc_id": "..."},
        "top_k": 5,
        "notes": "Smoke test for network section"
    }

The script reports hit rates, latency stats, and saves per-case results when
--report or --details is provided.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - optional dependency already in project
    yaml = None

# Ensure project root is on sys.path so we can import DatabaseManager
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db_tools import DatabaseManager  # noqa: E402


def load_cases(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Cases file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        content = f.read()

    if path.suffix.lower() in {".yaml", ".yml"}:
        if yaml is None:
            raise RuntimeError("PyYAML is required to read YAML case files.")
        payload = yaml.safe_load(content)
    else:
        payload = json.loads(content)

    if not isinstance(payload, list):
        raise ValueError("Cases file must contain a list of scenarios.")

    normalized: List[Dict[str, Any]] = []
    for entry in payload:
        if not isinstance(entry, dict) or "query" not in entry:
            raise ValueError("Each case must be an object containing at least 'query'.")
        normalized.append(entry)
    return normalized


def evaluate_case(
    manager: DatabaseManager,
    db_name: str,
    case: Dict[str, Any],
    default_top_k: int,
) -> Dict[str, Any]:
    query: str = case["query"]
    top_k = int(case.get("top_k") or default_top_k)
    filters = case.get("filters") or None

    start = time.perf_counter()
    results = manager.search(db_name, query, top_k=top_k, filters=filters, collect_metrics=False)
    latency_ms = (time.perf_counter() - start) * 1000

    expected_doc = case.get("expected_doc")
    expected_keywords = [kw.lower() for kw in case.get("expected_keywords", [])]

    keyword_hit = False
    doc_hit = False
    best_similarity: Optional[float] = None
    matches: List[str] = []

    for rank, res in enumerate(results, start=1):
        similarity = float(res.get("similarity", 0.0))
        if best_similarity is None or similarity > best_similarity:
            best_similarity = similarity

        doc_meta = res.get("document", {}) or {}
        doc_name = doc_meta.get("source") or res.get("source")
        content = (res.get("content") or "").lower()

        if expected_doc:
            if expected_doc == doc_name or expected_doc == doc_meta.get("doc_id"):
                doc_hit = True
                matches.append(f"doc@rank{rank}")

        if expected_keywords and all(keyword in content for keyword in expected_keywords):
            keyword_hit = True
            matches.append(f"keywords@rank{rank}")

    return {
        "query": query,
        "notes": case.get("notes"),
        "top_k": top_k,
        "filters": filters,
        "result_count": len(results),
        "latency_ms": latency_ms,
        "best_similarity": best_similarity,
        "keyword_hit": keyword_hit if expected_keywords else None,
        "doc_hit": doc_hit if expected_doc else None,
        "matches": matches,
    }


def summarize(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    latencies = [r["latency_ms"] for r in results]
    best_sims = [r["best_similarity"] for r in results if r.get("best_similarity") is not None]

    keyword_hits = [r["keyword_hit"] for r in results if r.get("keyword_hit") is not None]
    doc_hits = [r["doc_hit"] for r in results if r.get("doc_hit") is not None]

    def rate(values: List[Optional[bool]]) -> Optional[float]:
        if not values:
            return None
        positives = sum(1 for v in values if v)
        return positives / len(values)

    summary: Dict[str, Any] = {
        "cases": len(results),
        "latency_ms_avg": statistics.mean(latencies) if latencies else None,
        "latency_ms_p95": statistics.quantiles(latencies, n=20)[-1] if len(latencies) >= 20 else max(latencies or [0]),
        "best_similarity_avg": statistics.mean(best_sims) if best_sims else None,
        "keyword_hit_rate": rate(keyword_hits),
        "doc_hit_rate": rate(doc_hits),
        "non_empty_results": sum(1 for r in results if r.get("result_count")) / len(results) if results else None,
    }
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate RAG retrieval quality.")
    parser.add_argument("--db", required=True, help="Database name to query.")
    parser.add_argument("--cases", required=True, help="Path to JSON/YAML evaluation cases.")
    parser.add_argument("--top-k", type=int, default=5, help="Default top_k if a case does not override it.")
    parser.add_argument("--report", help="Optional path to write aggregated summary JSON.")
    parser.add_argument("--details", help="Optional path to write per-case results JSON.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cases_path = Path(args.cases)
    cases = load_cases(cases_path)
    manager = DatabaseManager()

    results: List[Dict[str, Any]] = []
    for case in cases:
        try:
            result = evaluate_case(manager, args.db, case, args.top_k)
            results.append(result)
        except Exception as exc:
            results.append({
                "query": case["query"],
                "error": str(exc),
                "latency_ms": None,
                "result_count": 0,
            })

    summary = summarize(results)

    print("RAG Evaluation Summary")
    print("=======================")
    print(json.dumps(summary, indent=2))

    if args.report:
        Path(args.report).write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"Summary written to {args.report}")

    if args.details:
        Path(args.details).write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"Per-case details written to {args.details}")


if __name__ == "__main__":
    main()
