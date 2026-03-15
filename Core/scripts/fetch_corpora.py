#!/usr/bin/env python3
"""
scripts/fetch_corpora.py
Fetch real document corpora for each node defined in config/nodes.yaml.

Sources:
  • Wikipedia  — article text via the wikipedia-api package
  • arXiv      — abstract + full-text PDFs via the arxiv package

Each node gets its own subdirectory under --corpus-root:
  data/corpora/<node_id>/wiki_<title>.txt
  data/corpora/<node_id>/arxiv_<id>.txt

Usage:
    python scripts/fetch_corpora.py
    python scripts/fetch_corpora.py --node-id quantum_mechanics
    python scripts/fetch_corpora.py --source wikipedia --min-docs 50
    python scripts/fetch_corpora.py --dry-run
    python scripts/fetch_corpora.py --resume   # skip nodes that already have enough docs

Requirements (install separately — not in core deps):
    pip install wikipedia-api arxiv requests
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# ---------------------------------------------------------------------------
# Optional imports with graceful fallback
# ---------------------------------------------------------------------------

try:
    import wikipediaapi
    _WIKI_AVAILABLE = True
except ImportError:
    _WIKI_AVAILABLE = False

try:
    import arxiv as arxiv_lib
    _ARXIV_AVAILABLE = True
except ImportError:
    _ARXIV_AVAILABLE = False

try:
    import requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False


# ---------------------------------------------------------------------------
# Domain → search queries mapping
# ---------------------------------------------------------------------------

DOMAIN_WIKI_QUERIES: Dict[str, List[str]] = {
    "physics": [
        "Quantum mechanics", "Wave function", "Uncertainty principle",
        "Quantum entanglement", "Schrödinger equation", "Particle physics",
        "Standard Model", "Higgs boson", "General relativity", "Special relativity",
        "Black hole", "Gravitational wave", "Thermodynamics", "Statistical mechanics",
        "Condensed matter physics", "Superconductivity", "Nuclear physics",
        "Radioactive decay", "Quantum field theory", "String theory",
    ],
    "computer_science": [
        "Machine learning", "Deep learning", "Neural network", "Transformer model",
        "Reinforcement learning", "Convolutional neural network",
        "Cryptography", "Public-key cryptography", "Zero-knowledge proof",
        "Quantum computing", "Qubit", "Quantum algorithm",
        "Algorithm", "Data structure", "Computational complexity theory",
        "Distributed computing", "Blockchain", "Byzantine fault tolerance",
    ],
    "biology": [
        "DNA", "Gene expression", "Natural selection", "Evolution",
        "Cell biology", "Mitosis", "Protein folding", "Enzyme",
        "Neuroscience", "Synapse", "Action potential", "Neurotransmitter",
        "Ecology", "Food web", "Photosynthesis", "Metabolism",
        "CRISPR", "Stem cell", "Epigenetics", "Microbiome",
    ],
    "astronomy": [
        "Cosmology", "Big Bang", "Cosmic microwave background",
        "Dark matter", "Dark energy", "Hubble constant",
        "Stellar evolution", "Main sequence", "Neutron star", "Pulsar",
        "Exoplanet", "Habitable zone", "Astrobiology",
        "Galaxy formation", "Milky Way", "Quasar",
        "Gravitational lensing", "Cosmic inflation",
    ],
    "chemistry": [
        "Chemical bond", "Covalent bond", "Ionic bond",
        "Reaction mechanism", "Catalysis", "Enzyme catalysis",
        "Thermochemistry", "Gibbs free energy", "Entropy",
        "Organic chemistry", "Polymer", "Nanomaterial",
        "Periodic table", "Electronegativity", "Oxidation state",
        "Spectroscopy", "Nuclear magnetic resonance",
    ],
    "mathematics": [
        "Probability theory", "Bayes theorem", "Central limit theorem",
        "Information theory", "Entropy (information theory)", "Shannon entropy",
        "Game theory", "Nash equilibrium", "Mechanism design",
        "Linear algebra", "Eigenvalues and eigenvectors",
        "Statistics", "Hypothesis testing", "Bayesian inference",
        "Topology", "Graph theory", "Number theory",
    ],
    "philosophy": [
        "Philosophy of mind", "Consciousness", "Qualia",
        "Hard problem of consciousness", "Functionalism (philosophy of mind)",
        "Epistemology", "Justified true belief", "Skepticism",
        "Ethics", "Consequentialism", "Deontological ethics",
        "Metaphysics", "Ontology", "Free will",
        "Logic", "Modal logic", "Gödel's incompleteness theorems",
    ],
}

DOMAIN_ARXIV_QUERIES: Dict[str, List[str]] = {
    "physics": [
        "quantum mechanics foundations", "quantum entanglement experiment",
        "general relativity tests", "black hole thermodynamics",
        "condensed matter topological", "superconductivity mechanism",
    ],
    "computer_science": [
        "large language model transformer", "reinforcement learning policy gradient",
        "zero knowledge proof blockchain", "quantum algorithm advantage",
        "federated learning privacy",
    ],
    "biology": [
        "CRISPR gene editing", "protein structure prediction",
        "neural circuit connectome", "evolutionary genomics",
        "microbiome human health",
    ],
    "astronomy": [
        "dark matter detection", "cosmological constant measurement",
        "exoplanet atmosphere spectroscopy", "gravitational wave detection",
        "cosmic inflation CMB",
    ],
    "chemistry": [
        "catalytic reaction mechanism", "nanomaterial synthesis",
        "polymer self-assembly", "quantum chemistry simulation",
        "electrochemical energy storage",
    ],
    "mathematics": [
        "Bayesian inference variational", "game theory mechanism design",
        "information theory channel capacity", "random matrix theory",
        "topological data analysis",
    ],
    "philosophy": [
        "consciousness integrated information", "philosophy mind computation",
        "epistemic logic formal", "moral uncertainty decision theory",
    ],
}


# ---------------------------------------------------------------------------
# Fetchers
# ---------------------------------------------------------------------------

def _sanitise_filename(s: str) -> str:
    return re.sub(r'[^\w\-_.]', '_', s)[:80]


def fetch_wikipedia(
    domain: str,
    node_id: str,
    out_dir: Path,
    min_docs: int,
    lang: str = "en",
    dry_run: bool = False,
) -> int:
    if not _WIKI_AVAILABLE:
        print(f"  [skip] wikipedia-api not installed (pip install wikipedia-api)")
        return 0

    wiki = wikipediaapi.Wikipedia(
        language=lang,
        user_agent="axon-graph-corpus-fetcher/0.1 (research)",
    )
    queries = DOMAIN_WIKI_QUERIES.get(domain, [])
    fetched = 0

    for title in queries:
        if fetched >= min_docs:
            break
        fname = out_dir / f"wiki_{_sanitise_filename(title)}.txt"
        if fname.exists():
            print(f"    [skip] {fname.name} already exists")
            fetched += 1
            continue

        if dry_run:
            print(f"    [dry] would fetch wikipedia: {title!r}")
            fetched += 1
            continue

        try:
            page = wiki.page(title)
            if not page.exists():
                print(f"    [miss] Wikipedia page not found: {title!r}")
                continue
            text = page.text
            if len(text) < 500:
                print(f"    [skip] page too short: {title!r}")
                continue
            fname.write_text(text, encoding="utf-8")
            print(f"    [wiki] {title!r} → {fname.name} ({len(text):,} chars)")
            fetched += 1
            time.sleep(0.3)   # polite rate limiting
        except Exception as exc:
            print(f"    [err] wikipedia {title!r}: {exc}")

    return fetched


def fetch_arxiv(
    domain: str,
    node_id: str,
    out_dir: Path,
    min_docs: int,
    max_results_per_query: int = 10,
    dry_run: bool = False,
) -> int:
    if not _ARXIV_AVAILABLE:
        print(f"  [skip] arxiv package not installed (pip install arxiv)")
        return 0

    queries = DOMAIN_ARXIV_QUERIES.get(domain, [])
    fetched = 0

    for query in queries:
        if fetched >= min_docs:
            break
        if dry_run:
            print(f"    [dry] would fetch arXiv: {query!r}")
            fetched += 2
            continue

        try:
            search = arxiv_lib.Search(
                query=query,
                max_results=max_results_per_query,
                sort_by=arxiv_lib.SortCriterion.Relevance,
            )
            for result in search.results():
                if fetched >= min_docs:
                    break
                arxiv_id = result.entry_id.split("/")[-1]
                fname = out_dir / f"arxiv_{_sanitise_filename(arxiv_id)}.txt"
                if fname.exists():
                    fetched += 1
                    continue

                # Write abstract + title as a text document
                text = (
                    f"Title: {result.title}\n\n"
                    f"Authors: {', '.join(str(a) for a in result.authors)}\n\n"
                    f"Published: {result.published}\n\n"
                    f"Abstract:\n{result.summary}\n"
                )
                fname.write_text(text, encoding="utf-8")
                print(f"    [arxiv] {result.title[:60]}... → {fname.name}")
                fetched += 1
                time.sleep(0.5)
        except Exception as exc:
            print(f"    [err] arxiv {query!r}: {exc}")

    return fetched


# ---------------------------------------------------------------------------
# Per-node orchestrator
# ---------------------------------------------------------------------------

def fetch_node_corpus(
    node_id: str,
    domain: str,
    corpus_root: Path,
    min_docs: int,
    sources: List[str],
    dry_run: bool = False,
    resume: bool = False,
) -> Tuple[int, int]:
    out_dir = corpus_root / node_id
    out_dir.mkdir(parents=True, exist_ok=True)

    existing = list(out_dir.glob("*.txt"))
    if resume and len(existing) >= min_docs:
        print(f"  [resume] {node_id}: {len(existing)} docs already present, skipping.")
        return len(existing), 0

    print(f"\n  [{node_id}] domain={domain} target={min_docs} docs existing={len(existing)}")

    wiki_fetched = arxiv_fetched = 0

    if "wikipedia" in sources:
        needed = max(0, min_docs - len(existing) - wiki_fetched)
        wiki_fetched = fetch_wikipedia(domain, node_id, out_dir, needed, dry_run=dry_run)

    if "arxiv" in sources:
        existing_now = len(list(out_dir.glob("*.txt")))
        needed = max(0, min_docs - existing_now)
        if needed > 0:
            arxiv_fetched = fetch_arxiv(domain, node_id, out_dir, needed, dry_run=dry_run)

    total = len(list(out_dir.glob("*.txt")))
    print(f"  [{node_id}] done: {total} docs total (wiki={wiki_fetched} arxiv={arxiv_fetched})")
    return total, wiki_fetched + arxiv_fetched


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch real document corpora for axon-graph nodes"
    )
    parser.add_argument("--nodes-file",   default="config/nodes.yaml")
    parser.add_argument("--corpus-root",  default="./data/corpora")
    parser.add_argument("--node-id",      default=None,
                        help="Fetch for a single node only")
    parser.add_argument("--source",       default="wikipedia,arxiv",
                        help="Comma-separated sources: wikipedia,arxiv")
    parser.add_argument("--min-docs",     type=int, default=100,
                        help="Minimum documents per node (default: 100)")
    parser.add_argument("--dry-run",      action="store_true")
    parser.add_argument("--resume",       action="store_true",
                        help="Skip nodes that already have enough docs")
    parser.add_argument("--delay",        type=float, default=1.0,
                        help="Seconds to wait between nodes (default: 1.0)")
    args = parser.parse_args()

    sources = [s.strip() for s in args.source.split(",")]
    corpus_root = Path(args.corpus_root)
    corpus_root.mkdir(parents=True, exist_ok=True)

    with open(args.nodes_file, "r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh)
    nodes = config.get("nodes", [])

    if args.node_id:
        nodes = [n for n in nodes if n["id"] == args.node_id]
        if not nodes:
            print(f"ERROR: node {args.node_id!r} not found in {args.nodes_file}")
            sys.exit(1)

    print(f"\naxon-graph fetch_corpora.py")
    print(f"  nodes      : {len(nodes)}")
    print(f"  sources    : {sources}")
    print(f"  min-docs   : {args.min_docs}")
    print(f"  corpus-root: {corpus_root}")
    print(f"  dry-run    : {args.dry_run}")
    print(f"  resume     : {args.resume}")

    total_docs = 0
    for entry in nodes:
        node_id = entry["id"]
        domain  = entry.get("domain", "")
        total, _ = fetch_node_corpus(
            node_id=node_id,
            domain=domain,
            corpus_root=corpus_root,
            min_docs=args.min_docs,
            sources=sources,
            dry_run=args.dry_run,
            resume=args.resume,
        )
        total_docs += total
        time.sleep(args.delay)

    print(f"\nDone. Total docs across all nodes: {total_docs}\n")


if __name__ == "__main__":
    main()
