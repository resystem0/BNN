"""
miners/domain/miner.py
Domain miner: serves KnowledgeQuery synapses via a Bittensor axon.

Responsibilities:
  • Register a forward handler for KnowledgeQuery
  • Retrieve top-k chunks from CorpusStore (ChromaDB-backed)
  • Attach Merkle root to every response for corpus-integrity challenges
  • Blacklist / priority hooks
  • Graceful startup / shutdown
"""

from __future__ import annotations

import asyncio
import time
from typing import Optional

import bittensor as bt

from config.subnet_config import SubnetConfig
from miners.domain.corpus import CorpusStore
from orchestrator.embedder import Embedder
from subnet.protocol import KnowledgeQuery


class DomainMiner:
    """
    A domain miner that owns one knowledge-graph node and answers
    KnowledgeQuery requests by retrieving chunks from its local corpus.
    """

    def __init__(
        self,
        wallet: bt.wallet,
        subtensor: bt.subtensor,
        metagraph: bt.metagraph,
        corpus: CorpusStore,
        embedder: Embedder,
        cfg: Optional[SubnetConfig] = None,
        axon: Optional[bt.axon] = None,
    ):
        self.wallet = wallet
        self.subtensor = subtensor
        self.metagraph = metagraph
        self.corpus = corpus
        self.embedder = embedder
        self.cfg = cfg or SubnetConfig()

        self.axon = axon or bt.axon(wallet=self.wallet, port=self.cfg.MINER_AXON_PORT)
        self.axon.attach(
            forward_fn=self._forward,
            blacklist_fn=self._blacklist,
            priority_fn=self._priority,
        )

        self._request_count: int = 0
        self._error_count: int = 0

    # ── forward handler ──────────────────────────────────────────────

    async def _forward(self, synapse: KnowledgeQuery) -> KnowledgeQuery:
        t0 = time.monotonic()

        try:
            # Use the pre-computed embedding if provided; otherwise embed query_text
            if synapse.query_embedding:
                query_emb = synapse.query_embedding
            else:
                query_emb = self.embedder.embed([synapse.query_text])[0]

            texts, chunk_ids, scores = self.corpus.query(
                query_embedding=query_emb,
                top_k=synapse.top_k,
            )

            synapse.chunks = texts
            synapse.chunk_ids = chunk_ids
            synapse.scores = scores
            synapse.merkle_root = self.corpus.get_merkle_root()
            synapse.miner_hotkey = self.wallet.hotkey.ss58_address
            synapse.elapsed_ms = (time.monotonic() - t0) * 1000
            self._request_count += 1

        except Exception as exc:
            bt.logging.error(f"DomainMiner._forward error: {exc}", exc_info=True)
            self._error_count += 1
            synapse.chunks = []
            synapse.chunk_ids = []
            synapse.scores = []
            synapse.merkle_root = None
            synapse.elapsed_ms = (time.monotonic() - t0) * 1000

        return synapse

    # ── blacklist ────────────────────────────────────────────────────

    async def _blacklist(self, synapse: KnowledgeQuery) -> tuple[bool, str]:
        """
        Reject requests from:
          - hotkeys not registered on the subnet
          - hotkeys with zero validator permit (non-validators sending queries)
        """
        caller = synapse.dendrite.hotkey if synapse.dendrite else None
        if caller is None:
            return True, "missing dendrite hotkey"

        if caller not in self.metagraph.hotkeys:
            return True, f"hotkey {caller!r} not registered on netuid={self.cfg.NETUID}"

        uid = self.metagraph.hotkeys.index(caller)
        if self.metagraph.validator_permit[uid] == 0:
            # Only validators and whitelisted callers may query
            if caller not in self.cfg.WHITELIST_HOTKEYS:
                return True, f"uid={uid} has no validator permit"

        return False, "ok"

    # ── priority ─────────────────────────────────────────────────────

    async def _priority(self, synapse: KnowledgeQuery) -> float:
        """
        Higher stake → higher priority in the axon request queue.
        """
        caller = synapse.dendrite.hotkey if synapse.dendrite else None
        if caller is None or caller not in self.metagraph.hotkeys:
            return 0.0
        uid = self.metagraph.hotkeys.index(caller)
        return float(self.metagraph.S[uid])

    # ── lifecycle ────────────────────────────────────────────────────

    def start(self) -> None:
        self.axon.start()
        bt.logging.success(
            f"DomainMiner axon started | node={self.corpus.node_id} "
            f"| port={self.cfg.MINER_AXON_PORT}"
        )

    def stop(self) -> None:
        self.axon.stop()
        bt.logging.info("DomainMiner axon stopped.")

    async def run_forever(self) -> None:
        self.start()
        try:
            while True:
                self.metagraph.sync(subtensor=self.subtensor)
                bt.logging.info(
                    f"DomainMiner heartbeat | requests={self._request_count} "
                    f"errors={self._error_count} "
                    f"corpus={self.corpus.stats()}"
                )
                await asyncio.sleep(self.cfg.MINER_SYNC_INTERVAL_S)
        except asyncio.CancelledError:
            pass
        finally:
            self.stop()
