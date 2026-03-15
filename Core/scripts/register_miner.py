#!/usr/bin/env python3
"""
scripts/register_miner.py
One-shot script: build corpus manifest → pin to IPFS → register miner UID on subnet.

Usage:
    python scripts/register_miner.py \
        --node-id quantum_mechanics \
        --corpus-dir ./data/corpora/quantum_mechanics \
        --wallet-name miner_alice \
        --wallet-hotkey default \
        --subtensor-endpoint ws://localhost:9944 \
        --netuid 1

Steps performed:
    1. Load node metadata from config/nodes.yaml
    2. Build a corpus manifest (chunk count, Merkle root, IPFS CIDs per file)
    3. Pin the manifest JSON to the local IPFS node
    4. Register the wallet on the subnet via btcli / subtensor.serve_axon
    5. Update nodes.yaml with the assigned UID and hotkey (optional --no-update)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bittensor as bt
from miners.domain.corpus import merkle_root
from orchestrator.embedder import Embedder


# ---------------------------------------------------------------------------
# IPFS helpers
# ---------------------------------------------------------------------------

IPFS_API = "http://127.0.0.1:5001"


def ipfs_add_json(data: dict) -> str:
    """Pin a JSON object to the local IPFS node. Returns the CID."""
    payload = json.dumps(data, indent=2).encode()
    resp = httpx.post(
        f"{IPFS_API}/api/v0/add",
        files={"file": ("manifest.json", payload, "application/json")},
        timeout=30,
    )
    resp.raise_for_status()
    cid = resp.json()["Hash"]
    return cid


def ipfs_pin(cid: str) -> None:
    resp = httpx.post(f"{IPFS_API}/api/v0/pin/add?arg={cid}", timeout=30)
    resp.raise_for_status()


def ipfs_available() -> bool:
    try:
        r = httpx.get(f"{IPFS_API}/api/v0/id", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Manifest builder
# ---------------------------------------------------------------------------

def build_manifest(
    node_id: str,
    domain: str,
    persona: str,
    corpus_dir: Optional[str],
    hotkey: str,
    axon_ip: str,
    axon_port: int,
) -> Dict[str, Any]:
    """
    Build the corpus manifest dict.
    If corpus_dir is provided, scan for .txt / .md files and compute per-file hashes.
    """
    manifest: Dict[str, Any] = {
        "schema_version": "1.0",
        "node_id": node_id,
        "domain": domain,
        "persona": persona,
        "miner_hotkey": hotkey,
        "axon_ip": axon_ip,
        "axon_port": axon_port,
        "created_at": time.time(),
        "files": [],
        "total_chunks": 0,
        "corpus_merkle_root": "",
    }

    if corpus_dir:
        corpus_path = Path(corpus_dir)
        if not corpus_path.exists():
            print(f"  [warn] corpus dir {corpus_dir!r} does not exist; manifest will be empty.")
            return manifest

        all_chunk_ids: List[str] = []
        for fpath in sorted(corpus_path.rglob("*.txt")) + sorted(corpus_path.rglob("*.md")):
            text = fpath.read_text(encoding="utf-8", errors="replace")
            # Simple chunk IDs — same logic as CorpusStore
            chunks = [text[i:i+512] for i in range(0, len(text), 448)]  # 512 size, 64 overlap
            file_chunk_ids = [
                hashlib.sha256(f"{node_id}:{fpath}:{i}:{c}".encode()).hexdigest()
                for i, c in enumerate(chunks)
            ]
            file_hash = hashlib.sha256(text.encode()).hexdigest()
            manifest["files"].append({
                "path": str(fpath.relative_to(corpus_path)),
                "sha256": file_hash,
                "chunk_count": len(chunks),
                "chunk_ids": file_chunk_ids,
            })
            all_chunk_ids.extend(file_chunk_ids)

        manifest["total_chunks"] = len(all_chunk_ids)
        manifest["corpus_merkle_root"] = merkle_root(all_chunk_ids) if all_chunk_ids else ""

    return manifest


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register(
    node_id: str,
    wallet: bt.wallet,
    subtensor: bt.subtensor,
    metagraph: bt.metagraph,
    netuid: int,
    axon_ip: str,
    axon_port: int,
    manifest_cid: str,
    wait: bool = True,
) -> Optional[int]:
    """
    Serve the miner axon on-chain. Returns the assigned UID or None on failure.
    """
    print(f"\n  Registering axon on netuid={netuid} ...")
    print(f"    hotkey : {wallet.hotkey.ss58_address}")
    print(f"    axon   : {axon_ip}:{axon_port}")
    print(f"    CID    : {manifest_cid}")

    # Check if already registered
    if wallet.hotkey.ss58_address in metagraph.hotkeys:
        uid = metagraph.hotkeys.index(wallet.hotkey.ss58_address)
        print(f"  Already registered as uid={uid}")
    else:
        print("  Not yet registered — running btcli register ...")
        success = subtensor.register(
            wallet=wallet,
            netuid=netuid,
            wait_for_inclusion=wait,
            wait_for_finalization=wait,
        )
        if not success:
            print("  ERROR: registration failed.")
            return None
        metagraph.sync(subtensor=subtensor)
        if wallet.hotkey.ss58_address not in metagraph.hotkeys:
            print("  ERROR: hotkey not found in metagraph after registration.")
            return None
        uid = metagraph.hotkeys.index(wallet.hotkey.ss58_address)
        print(f"  Registered as uid={uid}")

    # Serve axon (advertise IP:port on-chain)
    axon = bt.axon(wallet=wallet, ip=axon_ip, port=axon_port)
    success = subtensor.serve_axon(netuid=netuid, axon=axon)
    if success:
        print(f"  Axon served successfully at {axon_ip}:{axon_port}")
    else:
        print("  [warn] serve_axon returned False — check subtensor logs")

    # Commit manifest CID as on-chain metadata
    try:
        subtensor.commit(
            wallet=wallet,
            netuid=netuid,
            data=json.dumps({"node_id": node_id, "manifest_cid": manifest_cid}),
        )
        print(f"  Committed manifest CID to chain: {manifest_cid}")
    except Exception as exc:
        print(f"  [warn] commit failed: {exc}")

    return uid


def update_nodes_yaml(nodes_file: str, node_id: str, uid: int, hotkey: str) -> None:
    """Write the assigned UID and hotkey back into nodes.yaml."""
    with open(nodes_file, "r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh)

    for entry in config.get("nodes", []):
        if entry["id"] == node_id:
            entry.setdefault("miner", {})
            entry["miner"]["uid"] = uid
            entry["miner"]["hotkey"] = hotkey
            break

    with open(nodes_file, "w", encoding="utf-8") as fh:
        yaml.dump(config, fh, default_flow_style=False, allow_unicode=True, sort_keys=False)

    print(f"  Updated {nodes_file}: node {node_id!r} uid={uid} hotkey={hotkey}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Register a domain miner for an axon-graph node")
    parser.add_argument("--node-id",            required=True,  help="Node ID from nodes.yaml")
    parser.add_argument("--corpus-dir",         default=None,   help="Directory of .txt/.md corpus files")
    parser.add_argument("--wallet-name",        default="miner", help="Bittensor wallet name")
    parser.add_argument("--wallet-hotkey",      default="default", help="Wallet hotkey name")
    parser.add_argument("--wallet-path",        default="~/.bittensor/wallets")
    parser.add_argument("--subtensor-endpoint", default="ws://localhost:9944")
    parser.add_argument("--netuid",             type=int, default=1)
    parser.add_argument("--axon-ip",            default="0.0.0.0")
    parser.add_argument("--axon-port",          type=int, default=8091)
    parser.add_argument("--nodes-file",         default="config/nodes.yaml")
    parser.add_argument("--ipfs-api",           default="http://127.0.0.1:5001")
    parser.add_argument("--no-ipfs",            action="store_true", help="Skip IPFS pinning")
    parser.add_argument("--no-update",          action="store_true", help="Don't update nodes.yaml")
    parser.add_argument("--dry-run",            action="store_true", help="Build manifest only, no on-chain ops")
    args = parser.parse_args()

    global IPFS_API
    IPFS_API = args.ipfs_api

    # ── Load node metadata ────────────────────────────────────────────
    print(f"\naxon-graph register_miner.py")
    print(f"  node-id : {args.node_id}")

    nodes_config = load_nodes_yaml(args.nodes_file)
    node_entry = next((n for n in nodes_config.get("nodes", []) if n["id"] == args.node_id), None)
    if node_entry is None:
        print(f"ERROR: node {args.node_id!r} not found in {args.nodes_file}")
        sys.exit(1)

    domain  = node_entry.get("domain", "")
    persona = node_entry.get("persona", "neutral")
    axon_port = node_entry.get("miner", {}).get("axon_port", args.axon_port)

    # ── Init wallet / subtensor ───────────────────────────────────────
    if not args.dry_run:
        wallet = bt.wallet(
            name=args.wallet_name,
            hotkey=args.wallet_hotkey,
            path=args.wallet_path,
        )
        subtensor = bt.subtensor(network=args.subtensor_endpoint)
        metagraph = bt.metagraph(netuid=args.netuid, network=args.subtensor_endpoint)
        hotkey = wallet.hotkey.ss58_address
    else:
        hotkey = "dry-run-hotkey"

    # ── Build manifest ────────────────────────────────────────────────
    print(f"\n  Building corpus manifest ...")
    manifest = build_manifest(
        node_id=args.node_id,
        domain=domain,
        persona=persona,
        corpus_dir=args.corpus_dir,
        hotkey=hotkey,
        axon_ip=args.axon_ip,
        axon_port=axon_port,
    )
    print(f"    files        : {len(manifest['files'])}")
    print(f"    total chunks : {manifest['total_chunks']}")
    print(f"    merkle root  : {manifest['corpus_merkle_root'][:16]}..." if manifest['corpus_merkle_root'] else "    merkle root  : (empty)")

    if args.dry_run:
        print("\n[dry-run] Manifest:")
        print(json.dumps(manifest, indent=2))
        print("\n[dry-run] No on-chain operations performed.")
        return

    # ── Pin to IPFS ───────────────────────────────────────────────────
    manifest_cid = ""
    if not args.no_ipfs:
        if ipfs_available():
            print(f"\n  Pinning manifest to IPFS ...")
            manifest_cid = ipfs_add_json(manifest)
            ipfs_pin(manifest_cid)
            print(f"    CID: {manifest_cid}")
        else:
            print("  [warn] IPFS node not reachable at {args.ipfs_api}; skipping pin.")
    else:
        print("  [skip] IPFS pinning disabled via --no-ipfs")

    # ── Register on-chain ─────────────────────────────────────────────
    uid = register(
        node_id=args.node_id,
        wallet=wallet,
        subtensor=subtensor,
        metagraph=metagraph,
        netuid=args.netuid,
        axon_ip=args.axon_ip,
        axon_port=axon_port,
        manifest_cid=manifest_cid,
    )

    if uid is None:
        print("\nERROR: registration failed.")
        sys.exit(1)

    # ── Update nodes.yaml ─────────────────────────────────────────────
    if not args.no_update:
        update_nodes_yaml(args.nodes_file, args.node_id, uid, hotkey)

    print(f"\nDone. Miner for {args.node_id!r} registered as uid={uid}.\n")


def load_nodes_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


if __name__ == "__main__":
    main()
