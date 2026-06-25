#!/usr/bin/env python3
"""
Ablation runner: compare retrieval presets side-by-side.

Runs the Thai eval set against a list of named presets and prints a
formatted table showing Recall@k, nDCG, MRR, and avg query latency.

Usage:
  python3 src/eval/run_ablation.py [options]

Options:
  --config FILE          Preset config file (YAML or JSON). Default: ablation_presets.json
                         in the same directory as this script.
  --output FILE          Write results to FILE (JSON or CSV).
  --search-url URL       Search endpoint (default: http://localhost:7070/search).
  --k N                  Top-k for retrieval metrics (default: 10).
  --dataset FILE         Path to the eval dataset JSON (default: thai_eval_set.json).
  --embedding-model MODEL  Override the embedding model for this run (e.g.
                           multilingual-e5-base, multilingual-e5-large, BAAI/bge-m3).
                           Recorded in the output file for longitudinal comparison.
                           Does NOT restart the server — set EMBEDDING_MODEL in the
                           server's environment and re-embed before comparing models.

Config format (JSON):
  {
    "presets": [
      {"name": "dense-only", "hybridEnabled": "false", "rerankEnabled": "false"},
      {"name": "hybrid",     "hybridEnabled": "true",  "rerankEnabled": "false"}
    ]
  }

Config format (YAML, requires pyyaml):
  presets:
    - name: dense-only
      hybridEnabled: "false"
      rerankEnabled: "false"
    - name: hybrid
      hybridEnabled: "true"
      rerankEnabled: "false"
"""

import argparse
import csv
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_CONFIG = os.path.join(_DIR, "ablation_presets.json")
_DEFAULT_DATASET = os.path.join(_DIR, "thai_eval_set.json")
_DEFAULT_SEARCH_URL = "http://localhost:7070/search"
_DEFAULT_K = 10


# ---------------------------------------------------------------------------
# Metric helpers (shared with run_eval.py logic)
# ---------------------------------------------------------------------------


def compute_ndcg(results: list, expected: set, k: int) -> float:
    gains = [1.0 if r in expected else 0.0 for r in results[:k]]
    dcg = sum(g / math.log2(i + 2) for i, g in enumerate(gains))
    ideal = sorted(gains, reverse=True)
    idcg = sum(g / math.log2(i + 2) for i, g in enumerate(ideal))
    return dcg / idcg if idcg > 0 else 0.0


def compute_rr(results: list, expected: set, k: int) -> float:
    for i, r in enumerate(results[:k]):
        if r in expected:
            return 1.0 / (i + 1)
    return 0.0


# ---------------------------------------------------------------------------
# Search helper
# ---------------------------------------------------------------------------


def _query_search(search_url: str, query: str, k: int, preset_params: dict):
    """Hit the search endpoint with query and preset params. Returns (ids, latency_ms, error)."""
    params = {"q": query, "k": k}
    params.update(preset_params)
    url = f"{search_url}?{urllib.parse.urlencode(params)}"
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        latency_ms = (time.perf_counter() - t0) * 1000
        ids = [r["id"] for r in data.get("results", []) if r.get("id")]
        return ids, latency_ms, None
    except Exception as exc:
        latency_ms = (time.perf_counter() - t0) * 1000
        return [], latency_ms, str(exc)


# ---------------------------------------------------------------------------
# Per-preset evaluation
# ---------------------------------------------------------------------------


def run_preset(preset: dict, entries: list, k: int, search_url: str) -> dict:
    """Evaluate one preset against the full eval set. Returns metrics dict."""
    name = preset["name"]
    params = {key: val for key, val in preset.items() if key != "name"}

    recalls, ndcgs, rrs, latencies, errors = [], [], [], [], []

    for entry in entries:
        query = entry["query"]
        expected = set(entry["expected"])
        ids, latency_ms, err = _query_search(search_url, query, k, params)
        if err:
            errors.append(f"query={query!r}: {err}")
        hit = bool(expected & set(ids[:k]))
        recalls.append(hit)
        ndcgs.append(compute_ndcg(ids, expected, k))
        rrs.append(compute_rr(ids, expected, k))
        latencies.append(latency_ms)

    n = len(entries)
    return {
        "name": name,
        "recall": sum(recalls) / n if n else 0.0,
        "ndcg": sum(ndcgs) / n if n else 0.0,
        "mrr": sum(rrs) / n if n else 0.0,
        "latency_ms": sum(latencies) / n if n else 0.0,
        "n_queries": n,
        "n_errors": len(errors),
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------


def load_config(path: str) -> list:
    """Load preset list from a YAML or JSON config file."""
    with open(path, encoding="utf-8") as f:
        content = f.read()

    if path.lower().endswith((".yaml", ".yml")):
        try:
            import yaml  # type: ignore
            data = yaml.safe_load(content)
        except ImportError:
            print(
                "ERROR: YAML config requires pyyaml. Install it with:\n"
                "  pip install pyyaml\n"
                "Or use a JSON config file instead.",
                file=sys.stderr,
            )
            sys.exit(1)
    else:
        data = json.loads(content)

    return data.get("presets", [])


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------


def _col_width(values: list, header: str) -> int:
    return max(len(header), max((len(str(v)) for v in values), default=0))


def print_table(results: list, k: int) -> None:
    if not results:
        print("(no results)")
        return

    headers = ["Preset", f"Recall@{k}", "nDCG", "MRR", "Latency(ms)"]
    rows = [
        [
            r["name"],
            f"{r['recall']:.4f}",
            f"{r['ndcg']:.4f}",
            f"{r['mrr']:.4f}",
            f"{r['latency_ms']:.1f}",
        ]
        for r in results
    ]

    widths = [
        max(len(headers[i]), max(len(row[i]) for row in rows))
        for i in range(len(headers))
    ]

    sep = "+-" + "-+-".join("-" * w for w in widths) + "-+"
    fmt = "| " + " | ".join(f"{{:<{w}}}" for w in widths) + " |"

    print(sep)
    print(fmt.format(*headers))
    print(sep)
    for row in rows:
        print(fmt.format(*row))
    print(sep)


def save_output(results: list, k: int, output_path: str, timestamp: str, embedding_model=None) -> None:
    if output_path.lower().endswith(".csv"):
        _save_csv(results, k, output_path, timestamp, embedding_model=embedding_model)
    else:
        _save_json(results, k, output_path, timestamp, embedding_model=embedding_model)


def _save_json(results: list, k: int, path: str, timestamp: str, embedding_model=None) -> None:
    presets_out = [
        {
            "name": r["name"],
            f"recall_at_{k}": r["recall"],
            "ndcg": r["ndcg"],
            "mrr": r["mrr"],
            "latency_ms": r["latency_ms"],
            "n_queries": r["n_queries"],
            "n_errors": r["n_errors"],
        }
        for r in results
    ]
    data = {
        "timestamp": timestamp,
        "k": k,
        "presets": presets_out,
    }
    if embedding_model:
        data["embedding_model"] = embedding_model
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _save_csv(results: list, k: int, path: str, timestamp: str, embedding_model=None) -> None:
    fieldnames = ["timestamp", "embedding_model", "preset", f"recall_at_{k}", "ndcg", "mrr", "latency_ms", "n_queries", "n_errors"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow({
                "timestamp": timestamp,
                "embedding_model": embedding_model or "",
                "preset": r["name"],
                f"recall_at_{k}": f"{r['recall']:.4f}",
                "ndcg": f"{r['ndcg']:.4f}",
                "mrr": f"{r['mrr']:.4f}",
                "latency_ms": f"{r['latency_ms']:.1f}",
                "n_queries": r["n_queries"],
                "n_errors": r["n_errors"],
            })


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ablation runner: compare retrieval presets on the Thai eval set."
    )
    parser.add_argument(
        "--config",
        default=_DEFAULT_CONFIG,
        help=f"Preset config file (YAML or JSON). Default: {_DEFAULT_CONFIG}",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Write results to this file (JSON or CSV based on extension).",
    )
    parser.add_argument(
        "--search-url",
        default=_DEFAULT_SEARCH_URL,
        dest="search_url",
        help=f"Search endpoint URL. Default: {_DEFAULT_SEARCH_URL}",
    )
    parser.add_argument(
        "--k",
        type=int,
        default=_DEFAULT_K,
        help=f"Top-k for retrieval metrics. Default: {_DEFAULT_K}",
    )
    parser.add_argument(
        "--dataset",
        default=_DEFAULT_DATASET,
        help=f"Eval dataset JSON file. Default: {_DEFAULT_DATASET}",
    )
    parser.add_argument(
        "--embedding-model",
        default=None,
        dest="embedding_model",
        help=(
            "Embedding model used by the search server being evaluated "
            "(e.g. multilingual-e5-base, multilingual-e5-large, BAAI/bge-m3). "
            "Recorded in the output file for longitudinal model comparison. "
            "Does not restart the server — set EMBEDDING_MODEL server-side and "
            "run re-embed before switching."
        ),
    )
    args = parser.parse_args()

    # Load presets
    if not os.path.isfile(args.config):
        print(f"ERROR: Config file not found: {args.config}", file=sys.stderr)
        sys.exit(1)
    presets = load_config(args.config)
    if not presets:
        print("ERROR: No presets found in config file.", file=sys.stderr)
        sys.exit(1)

    # Load eval dataset
    if not os.path.isfile(args.dataset):
        print(f"ERROR: Eval dataset not found: {args.dataset}", file=sys.stderr)
        sys.exit(1)
    with open(args.dataset, encoding="utf-8") as f:
        entries = json.load(f)

    timestamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    k = args.k
    embedding_model = args.embedding_model

    model_label = f" [model: {embedding_model}]" if embedding_model else ""
    print(f"Running ablation with {len(presets)} preset(s) against {len(entries)} queries (k={k}){model_label}…")
    print()

    results = []
    for preset in presets:
        name = preset.get("name", "<unnamed>")
        print(f"  [{name}] running…", end="", flush=True)
        try:
            metrics = run_preset(preset, entries, k, args.search_url)
            results.append(metrics)
            status = f" done  (recall={metrics['recall']:.3f}, latency={metrics['latency_ms']:.0f}ms"
            if metrics["n_errors"]:
                status += f", {metrics['n_errors']} query error(s)"
            status += ")"
            print(status)
            if metrics["errors"]:
                for err in metrics["errors"][:5]:
                    print(f"    WARN: {err}")
                if len(metrics["errors"]) > 5:
                    print(f"    … and {len(metrics['errors']) - 5} more query error(s)")
        except Exception as exc:
            print(f" ERROR: {exc}")
            results.append({
                "name": name,
                "recall": None,
                "ndcg": None,
                "mrr": None,
                "latency_ms": None,
                "n_queries": len(entries),
                "n_errors": len(entries),
                "errors": [str(exc)],
                "_failed": True,
            })

    print()

    # Print table (only successful presets)
    good = [r for r in results if not r.get("_failed")]
    failed = [r for r in results if r.get("_failed")]

    if good:
        print(f"Results (k={k}):")
        print_table(good, k)
    else:
        print("No presets completed successfully.")

    if failed:
        print()
        for r in failed:
            err_msg = r["errors"][0] if r["errors"] else "unknown error"
            print(f"  ERROR [{r['name']}]: {err_msg}")

    # Save output file
    if args.output:
        all_for_output = [r for r in results if not r.get("_failed")]
        save_output(all_for_output, k, args.output, timestamp, embedding_model=embedding_model)
        print(f"\nResults written to: {args.output}")

    if failed and not good:
        sys.exit(1)


if __name__ == "__main__":
    main()
