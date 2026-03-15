"""
subnet/metagraph_watcher.py
Polls subtensor periodically, maintains a fresh UID→axon map, and fires
callbacks when new miners register or existing ones deregister.

Used by:
  • validator  — to keep the scoring loop working with current axons
  • orchestrator session — to resolve node_id → axon at query time
  • evolution/integration.py — to detect when a proposed miner comes online
"""

from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set

import bittensor as bt

from config.subnet_config import SubnetConfig


# ---------------------------------------------------------------------------
# Registration event
# ---------------------------------------------------------------------------

@dataclass
class RegistrationEvent:
    uid: int
    hotkey: str
    axon: bt.AxonInfo
    kind: str           # "registered" | "deregistered" | "axon_changed"
    detected_at: float = field(default_factory=time.time)


RegistrationCallback = Callable[[RegistrationEvent], None]


# ---------------------------------------------------------------------------
# AxonCache
# ---------------------------------------------------------------------------

class AxonCache:
    """
    Thread-safe snapshot of the current metagraph state.
    Updated atomically on each sync so readers never see a partial state.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._uid_to_axon: Dict[int, bt.AxonInfo]  = {}
        self._uid_to_hotkey: Dict[int, str]        = {}
        self._hotkey_to_uid: Dict[str, int]        = {}
        self._active_uids: Set[int]                = set()
        self._last_sync: float                     = 0.0
        self._sync_count: int                      = 0

    def update(self, metagraph: bt.metagraph) -> List[RegistrationEvent]:
        """
        Atomically refresh the cache from a freshly-synced metagraph.
        Returns a list of RegistrationEvents for any changes detected.
        """
        new_uid_to_axon    = {}
        new_uid_to_hotkey  = {}
        new_hotkey_to_uid  = {}

        uids = metagraph.uids.tolist()
        for uid in uids:
            try:
                axon   = metagraph.axons[uid]
                hotkey = metagraph.hotkeys[uid]
                new_uid_to_axon[uid]    = axon
                new_uid_to_hotkey[uid]  = hotkey
                new_hotkey_to_uid[hotkey] = uid
            except (IndexError, AttributeError):
                continue

        events: List[RegistrationEvent] = []

        with self._lock:
            new_uids  = set(new_uid_to_axon.keys())
            prev_uids = self._active_uids

            # New registrations
            for uid in new_uids - prev_uids:
                events.append(RegistrationEvent(
                    uid=uid,
                    hotkey=new_uid_to_hotkey[uid],
                    axon=new_uid_to_axon[uid],
                    kind="registered",
                ))

            # Deregistrations
            for uid in prev_uids - new_uids:
                events.append(RegistrationEvent(
                    uid=uid,
                    hotkey=self._uid_to_hotkey.get(uid, ""),
                    axon=self._uid_to_axon.get(uid, bt.AxonInfo()),
                    kind="deregistered",
                ))

            # Axon IP/port changes (miner moved)
            for uid in new_uids & prev_uids:
                old = self._uid_to_axon.get(uid)
                new = new_uid_to_axon[uid]
                if old and (old.ip != new.ip or old.port != new.port):
                    events.append(RegistrationEvent(
                        uid=uid,
                        hotkey=new_uid_to_hotkey[uid],
                        axon=new,
                        kind="axon_changed",
                    ))

            # Commit
            self._uid_to_axon   = new_uid_to_axon
            self._uid_to_hotkey = new_uid_to_hotkey
            self._hotkey_to_uid = new_hotkey_to_uid
            self._active_uids   = new_uids
            self._last_sync     = time.time()
            self._sync_count   += 1

        return events

    # ── Lookups (lock-free reads on immutable snapshots) ──────────────

    def axon(self, uid: int) -> Optional[bt.AxonInfo]:
        return self._uid_to_axon.get(uid)

    def hotkey(self, uid: int) -> Optional[str]:
        return self._uid_to_hotkey.get(uid)

    def uid(self, hotkey: str) -> Optional[int]:
        return self._hotkey_to_uid.get(hotkey)

    def all_uids(self) -> List[int]:
        return list(self._active_uids)

    def all_axons(self) -> Dict[int, bt.AxonInfo]:
        return dict(self._uid_to_axon)

    def uid_to_hotkey_map(self) -> Dict[int, str]:
        return dict(self._uid_to_hotkey)

    @property
    def last_sync(self) -> float:
        return self._last_sync

    @property
    def sync_count(self) -> int:
        return self._sync_count

    def is_stale(self, max_age_s: float = 120.0) -> bool:
        return (time.time() - self._last_sync) > max_age_s

    def stats(self) -> Dict:
        return {
            "active_uids": len(self._active_uids),
            "last_sync": self._last_sync,
            "sync_count": self._sync_count,
            "stale": self.is_stale(),
        }


# ---------------------------------------------------------------------------
# MetagraphWatcher
# ---------------------------------------------------------------------------

class MetagraphWatcher:
    """
    Background async task that polls subtensor every METAGRAPH_SYNC_INTERVAL_S
    seconds, updates the AxonCache, and dispatches RegistrationEvents to
    registered callbacks.

    Typical usage:

        watcher = MetagraphWatcher(subtensor, metagraph, cfg)
        watcher.on_registration(lambda e: handle(e))
        asyncio.create_task(watcher.run_forever())

        # Anywhere in the codebase:
        axon = watcher.cache.axon(uid)
    """

    def __init__(
        self,
        subtensor: bt.subtensor,
        metagraph: bt.metagraph,
        cfg: Optional[SubnetConfig] = None,
    ):
        self.subtensor  = subtensor
        self.metagraph  = metagraph
        self.cfg        = cfg or SubnetConfig()
        self.cache      = AxonCache()

        self._callbacks: List[RegistrationCallback] = []
        self._running   = False
        self._sync_lock = asyncio.Lock()

        # Do an initial sync synchronously so the cache is warm before
        # any async code tries to use it.
        self._sync_blocking()

    # ── Callback registration ─────────────────────────────────────────

    def on_registration(self, callback: RegistrationCallback) -> None:
        """Register a callback to be called for every RegistrationEvent."""
        self._callbacks.append(callback)

    def _dispatch(self, events: List[RegistrationEvent]) -> None:
        for event in events:
            level = bt.logging.success if event.kind == "registered" else bt.logging.warning
            level(
                f"MetagraphWatcher: uid={event.uid} hotkey={event.hotkey[:8]}... "
                f"kind={event.kind} axon={event.axon.ip}:{event.axon.port}"
            )
            for cb in self._callbacks:
                try:
                    cb(event)
                except Exception as exc:
                    bt.logging.error(f"Registration callback error: {exc}", exc_info=True)

    # ── Sync ──────────────────────────────────────────────────────────

    def _sync_blocking(self) -> None:
        try:
            self.metagraph.sync(subtensor=self.subtensor)
            events = self.cache.update(self.metagraph)
            if events:
                self._dispatch(events)
        except Exception as exc:
            bt.logging.error(f"MetagraphWatcher sync error: {exc}", exc_info=True)

    async def sync_once(self) -> List[RegistrationEvent]:
        """Force a single sync. Thread-safe via asyncio lock."""
        async with self._sync_lock:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._sync_blocking)
            return []   # events already dispatched inside _sync_blocking

    # ── Background loop ───────────────────────────────────────────────

    async def run_forever(self) -> None:
        self._running = True
        bt.logging.info(
            f"MetagraphWatcher started | netuid={self.cfg.NETUID} "
            f"interval={self.cfg.METAGRAPH_SYNC_INTERVAL_S}s"
        )
        while self._running:
            try:
                await asyncio.sleep(self.cfg.METAGRAPH_SYNC_INTERVAL_S)
                await self.sync_once()
                bt.logging.debug(f"MetagraphWatcher: {self.cache.stats()}")
            except asyncio.CancelledError:
                break
            except Exception as exc:
                bt.logging.error(f"MetagraphWatcher loop error: {exc}", exc_info=True)
                await asyncio.sleep(10)

        bt.logging.info("MetagraphWatcher stopped.")

    def stop(self) -> None:
        self._running = False

    # ── Convenience passthrough ───────────────────────────────────────

    def axon_for_uid(self, uid: int) -> Optional[bt.AxonInfo]:
        axon = self.cache.axon(uid)
        if axon is None or (axon.ip in ("0.0.0.0", "") and axon.port == 0):
            return None
        return axon

    def uid_for_hotkey(self, hotkey: str) -> Optional[int]:
        return self.cache.uid(hotkey)

    def active_uids(self) -> List[int]:
        return self.cache.all_uids()

    def is_registered(self, hotkey: str) -> bool:
        return self.cache.uid(hotkey) is not None
