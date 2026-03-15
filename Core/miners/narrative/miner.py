"""
miners/narrative/miner.py
Narrative miner: serves NarrativeHop synapses via a Bittensor axon.

Each request asks the miner to generate one story paragraph that bridges
two adjacent knowledge-graph nodes.  Generation is handled by a local
vLLM OpenAI-compatible server (or any OpenAI-compatible endpoint).

The miner also reads/writes prior narrative from a Redis session store
so that context accumulates correctly across multi-hop sessions.
"""

from __future__ import annotations

import asyncio
import time
from typing import Optional

import bittensor as bt

try:
    from openai import AsyncOpenAI
    _OPENAI_AVAILABLE = True
except ImportError:
    _OPENAI_AVAILABLE = False
    bt.logging.warning("openai package not installed; NarrativeMiner will echo prompts.")

from config.subnet_config import SubnetConfig
from miners.narrative.prompt import build_prompt, fits_in_context
from miners.narrative.session_store import SessionStore
from subnet.protocol import NarrativeHop


class NarrativeMiner:
    """
    Narrative miner that owns no corpus of its own — it synthesises
    hop-text by calling a vLLM model, grounded on chunks supplied in
    the synapse by the orchestrator.
    """

    def __init__(
        self,
        wallet: bt.wallet,
        subtensor: bt.subtensor,
        metagraph: bt.metagraph,
        session_store: SessionStore,
        cfg: Optional[SubnetConfig] = None,
        axon: Optional[bt.axon] = None,
        vllm_base_url: str = "http://localhost:8000/v1",
        model_name: str = "mistralai/Mistral-7B-Instruct-v0.3",
    ):
        self.wallet = wallet
        self.subtensor = subtensor
        self.metagraph = metagraph
        self.session_store = session_store
        self.cfg = cfg or SubnetConfig()
        self.model_name = model_name

        self._llm: Optional[AsyncOpenAI] = None
        if _OPENAI_AVAILABLE:
            self._llm = AsyncOpenAI(
                base_url=vllm_base_url,
                api_key="EMPTY",   # vLLM doesn't require a real key
            )

        self.axon = axon or bt.axon(wallet=self.wallet, port=self.cfg.NARRATIVE_AXON_PORT)
        self.axon.attach(
            forward_fn=self._forward,
            blacklist_fn=self._blacklist,
            priority_fn=self._priority,
        )

        self._request_count: int = 0
        self._error_count: int = 0

    # ── generation ───────────────────────────────────────────────────

    async def _generate(self, synapse: NarrativeHop) -> tuple[str, str, int]:
        """
        Call vLLM and return (hop_text, finish_reason, token_count).
        Falls back to an echo stub when vLLM is unavailable.
        """
        # Fetch prior narrative from session store (may be richer than synapse field)
        stored_prior = await self.session_store.get(synapse.session_id) or synapse.prior_narrative

        system_prompt, user_prompt = build_prompt(
            from_node_id=synapse.from_node_id,
            to_node_id=synapse.to_node_id,
            path_so_far=synapse.path_so_far,
            chunks=synapse.chunks,
            prior_narrative=stored_prior,
            persona=synapse.persona,
            min_words=self.cfg.MIN_HOP_WORDS,
            max_words=self.cfg.MAX_HOP_WORDS,
        )

        if not fits_in_context(system_prompt, user_prompt, synapse.max_tokens):
            bt.logging.warning(
                f"[session={synapse.session_id}] prompt may exceed context window; "
                "truncation may occur."
            )

        if self._llm is None:
            # Stub fallback
            stub = (
                f"[stub] Transitioning from {synapse.from_node_id} "
                f"to {synapse.to_node_id}. (vLLM not available)"
            )
            return stub, "stop", len(stub.split())

        response = await self._llm.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            max_tokens=synapse.max_tokens,
            temperature=self.cfg.NARRATIVE_TEMPERATURE,
            top_p=self.cfg.NARRATIVE_TOP_P,
        )

        choice = response.choices[0]
        hop_text = choice.message.content or ""
        finish_reason = choice.finish_reason or "stop"
        token_count = response.usage.completion_tokens if response.usage else len(hop_text.split())

        return hop_text, finish_reason, token_count

    # ── session persistence ──────────────────────────────────────────

    async def _update_session(self, synapse: NarrativeHop, hop_text: str) -> None:
        prior = await self.session_store.get(synapse.session_id) or ""
        updated = (prior + "\n\n" + hop_text).strip()
        await self.session_store.set(synapse.session_id, updated)

    # ── forward handler ──────────────────────────────────────────────

    async def _forward(self, synapse: NarrativeHop) -> NarrativeHop:
        t0 = time.monotonic()
        try:
            hop_text, finish_reason, token_count = await self._generate(synapse)
            await self._update_session(synapse, hop_text)

            synapse.hop_text = hop_text
            synapse.finish_reason = finish_reason
            synapse.token_count = token_count
            synapse.miner_hotkey = self.wallet.hotkey.ss58_address
            synapse.elapsed_ms = (time.monotonic() - t0) * 1000
            self._request_count += 1

        except Exception as exc:
            bt.logging.error(f"NarrativeMiner._forward error: {exc}", exc_info=True)
            self._error_count += 1
            synapse.hop_text = ""
            synapse.finish_reason = "safety"
            synapse.token_count = 0
            synapse.elapsed_ms = (time.monotonic() - t0) * 1000

        return synapse

    # ── blacklist ────────────────────────────────────────────────────

    async def _blacklist(self, synapse: NarrativeHop) -> tuple[bool, str]:
        caller = synapse.dendrite.hotkey if synapse.dendrite else None
        if caller is None:
            return True, "missing dendrite hotkey"
        if caller not in self.metagraph.hotkeys:
            return True, f"hotkey {caller!r} not registered"
        uid = self.metagraph.hotkeys.index(caller)
        if self.metagraph.validator_permit[uid] == 0:
            if caller not in self.cfg.WHITELIST_HOTKEYS:
                return True, f"uid={uid} has no validator permit"
        return False, "ok"

    # ── priority ─────────────────────────────────────────────────────

    async def _priority(self, synapse: NarrativeHop) -> float:
        caller = synapse.dendrite.hotkey if synapse.dendrite else None
        if caller is None or caller not in self.metagraph.hotkeys:
            return 0.0
        uid = self.metagraph.hotkeys.index(caller)
        return float(self.metagraph.S[uid])

    # ── lifecycle ────────────────────────────────────────────────────

    def start(self) -> None:
        self.axon.start()
        bt.logging.success(
            f"NarrativeMiner axon started | model={self.model_name} "
            f"| port={self.cfg.NARRATIVE_AXON_PORT}"
        )

    def stop(self) -> None:
        self.axon.stop()
        bt.logging.info("NarrativeMiner axon stopped.")

    async def run_forever(self) -> None:
        self.start()
        try:
            while True:
                self.metagraph.sync(subtensor=self.subtensor)
                bt.logging.info(
                    f"NarrativeMiner heartbeat | requests={self._request_count} "
                    f"errors={self._error_count}"
                )
                await asyncio.sleep(self.cfg.MINER_SYNC_INTERVAL_S)
        except asyncio.CancelledError:
            pass
        finally:
            self.stop()
