"""
miners/domain/manifest.py

Builds and publishes the DomainManifest that a miner submits when
registering on subnet 42.

The manifest is a JSON document stored on IPFS. Only its CID is written
to the on-chain axon.info field. Validators fetch the full manifest from
IPFS to verify corpus integrity and domain centroid.

Manifest schema:
    {
        "spec_version":           int,
        "node_id":                str,
        "display_label":          str,
        "domain":                 str,
        "narrative_persona":      str,       # ≤ 500 chars
        "narrative_style":        str,       # ≤ 200 chars
        "adjacent_nodes":         list[str], # existing live node_ids
        "centroid_embedding_cid": str,       # IPFS CID of 768-dim .npy file
        "corpus_root_hash":       str,       # Merkle root of chunk hashes
        "chunk_count":            int,
        "min_stake_tao":          float,
        "created_at_epoch":       int,
        "miner_hotkey":           str,
    }

Usage (called by scripts/register_miner.py):
    manifest = ManifestBuilder(
        node_id="causal_inference",
        corpus_loader=loader,         # already-loaded CorpusLoader
        prover=prover,                # already-built MerkleProver
        config=node_cfg,              # from config/nodes.yaml
    ).build()

    cid = IPFSPublisher(ipfs_host="127.0.0.1", ipfs_port=5001).publish(manifest)
    print(f"Manifest CID: {cid}")
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import requests

import bittensor as bt

from config.subnet_config import SPEC_VERSION
from miners.domain.corpus import CorpusLoader, MerkleProver


# ---------------------------------------------------------------------------
# Manifest dataclass
# ---------------------------------------------------------------------------

@dataclass
class DomainManifest:
    spec_version:           int
    node_id:                str
    display_label:          str
    domain:                 str
    narrative_persona:      str
    narrative_style:        str
    adjacent_nodes:         list[str]
    centroid_embedding_cid: str        # pinned on IPFS
    corpus_root_hash:       str
    chunk_count:            int
    min_stake_tao:          float
    created_at_epoch:       int
    miner_hotkey:           str

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, raw: str) -> "DomainManifest":
        return cls(**json.loads(raw))

    def validate(self):
        """
        Lightweight self-check before publishing.
        Raises ValueError if the manifest is malformed.
        """
        if len(self.narrative_persona) > 500:
            raise ValueError("narrative_persona must be ≤ 500 chars")
        if len(self.narrative_style) > 200:
            raise ValueError("narrative_style must be ≤ 200 chars")
        if not self.adjacent_nodes:
            raise ValueError("adjacent_nodes must name at least one existing node")
        if len(self.adjacent_nodes) > 4:
            raise ValueError("adjacent_nodes must name at most 4 nodes (proposal limit)")
        if not self.corpus_root_hash:
            raise ValueError("corpus_root_hash cannot be empty")
        if self.chunk_count < 10:
            raise ValueError("corpus must have at least 10 chunks")


# ---------------------------------------------------------------------------
# ManifestBuilder
# ---------------------------------------------------------------------------

class ManifestBuilder:
    """
    Assembles a DomainManifest from a loaded CorpusLoader and a node
    configuration dict (one entry from config/nodes.yaml).

    The centroid embedding is pinned to IPFS separately (as a .npy file)
    and only its CID is stored in the manifest JSON.
    """

    def __init__(
        self,
        node_id:       str,
        corpus_loader: CorpusLoader,
        prover:        MerkleProver,
        node_cfg:      dict,           # from nodes.yaml
        wallet:        bt.wallet,
        ipfs_publisher: "IPFSPublisher",
        current_epoch: int = 0,
    ):
        self.node_id        = node_id
        self.loader         = corpus_loader
        self.prover         = prover
        self.node_cfg       = node_cfg
        self.wallet         = wallet
        self.ipfs           = ipfs_publisher
        self.current_epoch  = current_epoch

    def build(self) -> DomainManifest:
        # 1. Pin the centroid embedding to IPFS
        centroid_bytes = self.loader.centroid.astype(np.float32).tobytes()
        centroid_cid   = self.ipfs.publish_bytes(
            centroid_bytes,
            filename=f"{self.node_id}_centroid.bin",
        )

        manifest = DomainManifest(
            spec_version           = SPEC_VERSION,
            node_id                = self.node_id,
            display_label          = self.node_cfg.get("display_label", self.node_id),
            domain                 = self.node_cfg["domain"],
            narrative_persona      = self.node_cfg["narrative_persona"],
            narrative_style        = self.node_cfg.get("narrative_style", ""),
            adjacent_nodes         = self.node_cfg["adjacent_nodes"],
            centroid_embedding_cid = centroid_cid,
            corpus_root_hash       = self.prover.root_hash,
            chunk_count            = self.prover.n_chunks,
            min_stake_tao          = self.node_cfg.get("min_stake_tao", 100.0),
            created_at_epoch       = self.current_epoch,
            miner_hotkey           = self.wallet.hotkey.ss58_address,
        )
        manifest.validate()
        return manifest


# ---------------------------------------------------------------------------
# IPFSPublisher
# ---------------------------------------------------------------------------

class IPFSPublisher:
    """
    Thin wrapper around the IPFS HTTP API (go-ipfs / kubo).
    Used by ManifestBuilder to pin the centroid embedding and the
    manifest JSON itself.

    Expects a running IPFS daemon accessible at ipfs_host:ipfs_port.
    For local dev, start with: docker-compose up ipfs

    All pinned content uses --pin=true so the local node retains it.
    In production, also pin to a remote pinning service (Pinata, Web3.Storage)
    for redundancy.
    """

    def __init__(self, ipfs_host: str = "127.0.0.1", ipfs_port: int = 5001):
        self.base_url = f"http://{ipfs_host}:{ipfs_port}/api/v0"
        self._check_connectivity()

    def _check_connectivity(self):
        try:
            resp = requests.post(f"{self.base_url}/id", timeout=5)
            resp.raise_for_status()
        except Exception as exc:
            raise ConnectionError(
                f"Cannot reach IPFS daemon at {self.base_url}. "
                f"Is 'docker-compose up ipfs' running? Error: {exc}"
            )

    def publish(self, manifest: DomainManifest) -> str:
        """Pin a DomainManifest JSON and return its CID."""
        return self.publish_bytes(
            manifest.to_json().encode("utf-8"),
            filename="manifest.json",
        )

    def publish_bytes(self, data: bytes, filename: str = "data") -> str:
        """
        Pin arbitrary bytes to IPFS. Returns the CID string.
        Uses the /add endpoint with pin=true and only-hash=false.
        """
        resp = requests.post(
            f"{self.base_url}/add",
            params={"pin": "true", "only-hash": "false"},
            files={"file": (filename, data, "application/octet-stream")},
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
        return result["Hash"]

    def fetch_manifest(self, cid: str) -> DomainManifest:
        """
        Fetch and deserialise a manifest from IPFS by CID.
        Used by validators to retrieve and cache miner manifests.
        """
        resp = requests.post(
            f"{self.base_url}/cat",
            params={"arg": cid},
            timeout=15,
        )
        resp.raise_for_status()
        return DomainManifest.from_json(resp.text)

    def fetch_centroid(self, cid: str) -> np.ndarray:
        """
        Fetch a centroid embedding from IPFS by CID.
        Returns a (EMBEDDING_DIM,) float32 numpy array.
        """
        from config.subnet_config import EMBEDDING_DIM
        resp = requests.post(
            f"{self.base_url}/cat",
            params={"arg": cid},
            timeout=15,
        )
        resp.raise_for_status()
        arr = np.frombuffer(resp.content, dtype=np.float32)
        if arr.shape != (EMBEDDING_DIM,):
            raise ValueError(
                f"Centroid shape mismatch: expected ({EMBEDDING_DIM},), got {arr.shape}"
            )
        return arr
