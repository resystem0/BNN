#!/usr/bin/env python3
"""
scripts/seed_graph.py
Populate the GraphStore with initial nodes and edges from config/nodes.yaml.

Usage:
    python scripts/seed_graph.py [--db-path ./data/kuzu] [--nodes-file config/nodes.yaml]
    python scripts/seed_graph.py --dry-run      # print what would be inserted
    python scripts/seed_graph.py --reset        # wipe and re-seed

This is idempotent: re-running it will not duplicate nodes or edges.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import yaml

# Allow running from repo root without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from subnet.graph_store import GraphStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_nodes_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def print_summary(graph: GraphStore) -> None:
    stats = graph.stats()
    print(f"\n  Graph summary:")
    print(f"    nodes : {stats['node_count']}")
    print(f"    edges : {stats['edge_count']}")
    print(f"    avg edge weight : {stats['avg_edge_weight']}")


# ---------------------------------------------------------------------------
# Main seeding logic
# ---------------------------------------------------------------------------

def seed(
    db_path: str,
    nodes_file: str,
    dry_run: bool = False,
    reset: bool = False,
    initial_weight: float = 1.0,
    verbose: bool = True,
) -> GraphStore:
    nodes_config = load_nodes_yaml(nodes_file)
    node_entries = nodes_config.get("nodes", [])

    if not node_entries:
        print("ERROR: no nodes found in nodes.yaml")
        sys.exit(1)

    if dry_run:
        print(f"\n[dry-run] Would seed {len(node_entries)} nodes from {nodes_file}:")
        for entry in node_entries:
            adj = entry.get("adjacency", [])
            print(f"  node: {entry['id']!r:30s} domain={entry['domain']!r:20s} edges→{adj}")
        return None  # type: ignore

    if reset:
        kuzu_path = Path(db_path)
        if kuzu_path.exists():
            shutil.rmtree(kuzu_path)
            print(f"  Wiped existing KùzuDB at {db_path}")

    graph = GraphStore(db_path=db_path)

    # ── Insert nodes ──────────────────────────────────────────────────
    inserted_nodes = 0
    for entry in node_entries:
        node_id  = entry["id"]
        domain   = entry.get("domain", "")
        persona  = entry.get("persona", "neutral")
        uid      = entry.get("miner", {}).get("uid")  # None until registered

        graph.add_node(node_id, domain=domain, persona=persona, uid=uid)
        inserted_nodes += 1
        if verbose:
            print(f"  [node] {node_id:35s} domain={domain:20s} persona={persona}")

    # ── Insert edges ──────────────────────────────────────────────────
    inserted_edges = 0
    known_ids = {e["id"] for e in node_entries}

    for entry in node_entries:
        src = entry["id"]
        for dst in entry.get("adjacency", []):
            if dst not in known_ids:
                print(f"  [warn] edge {src!r} → {dst!r}: destination not in nodes.yaml, skipping")
                continue
            graph.add_edge(src, dst, weight=initial_weight)
            inserted_edges += 1
            if verbose:
                print(f"  [edge] {src:35s} → {dst}")

    print(f"\n  Seeded {inserted_nodes} nodes and {inserted_edges} edges.")
    print_summary(graph)
    return graph


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the axon-graph GraphStore from nodes.yaml")
    parser.add_argument(
        "--db-path",
        default="./data/kuzu",
        help="Path to KùzuDB directory (default: ./data/kuzu)",
    )
    parser.add_argument(
        "--nodes-file",
        default="config/nodes.yaml",
        help="Path to nodes.yaml (default: config/nodes.yaml)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be inserted without writing",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Wipe the existing graph before seeding",
    )
    parser.add_argument(
        "--initial-weight",
        type=float,
        default=1.0,
        help="Starting weight for all seeded edges (default: 1.0)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-node/edge output",
    )
    parser.add_argument(
        "--dump-json",
        action="store_true",
        help="After seeding, dump graph as JSON to stdout",
    )
    args = parser.parse_args()

    print(f"\naxon-graph seed_graph.py")
    print(f"  db-path    : {args.db_path}")
    print(f"  nodes-file : {args.nodes_file}")
    print(f"  dry-run    : {args.dry_run}")
    print(f"  reset      : {args.reset}")

    graph = seed(
        db_path=args.db_path,
        nodes_file=args.nodes_file,
        dry_run=args.dry_run,
        reset=args.reset,
        initial_weight=args.initial_weight,
        verbose=not args.quiet,
    )

    if graph and args.dump_json:
        all_nodes = graph.all_node_ids()
        data = {
            "nodes": [
                {
                    "id": nid,
                    "node": vars(graph.get_node(nid)) if graph.get_node(nid) else {},
                    "neighbours": graph.neighbours(nid),
                    "topology_score": graph.topology_score(nid),
                }
                for nid in all_nodes
            ]
        }
        print("\n--- graph JSON ---")
        print(json.dumps(data, indent=2, default=str))

    print("\nDone.\n")


if __name__ == "__main__":
    main()
