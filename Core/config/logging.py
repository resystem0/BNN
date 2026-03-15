"""
config/logging.py
Structured JSON logger for axon-graph.

Wraps structlog to emit newline-delimited JSON to stdout (and optionally a
rotating file). Every log record is tagged with:
  - service   : "validator" | "domain_miner" | "narrative_miner" | "gateway" | ...
  - epoch     : current epoch number (set via set_epoch())
  - netuid    : subnet netuid from SubnetConfig
  - node_id   : miner's node_id if applicable (set via set_node_id())
  - ts        : ISO-8601 timestamp

Usage:
    from config.logging import get_logger, set_epoch, set_node_id

    log = get_logger("validator")
    set_epoch(42)

    log.info("scoring_started", uids=[0, 1, 2])
    log.warning("low_score", uid=5, score=0.01)
    log.error("set_weights_failed", error=str(exc))

Bittensor's own bt.logging is left intact alongside this logger; they
write to different handlers and don't interfere.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Any, Optional

import structlog
from structlog.types import EventDict, WrappedLogger

from config.subnet_config import SubnetConfig

# ---------------------------------------------------------------------------
# Shared mutable context (process-global, updated by set_epoch / set_node_id)
# ---------------------------------------------------------------------------

_CURRENT_EPOCH: int = 0
_CURRENT_NODE_ID: Optional[str] = None
_SERVICE_NAME: str = "axon-graph"
_NETUID: int = SubnetConfig().NETUID


def set_epoch(epoch: int) -> None:
    global _CURRENT_EPOCH
    _CURRENT_EPOCH = epoch


def set_node_id(node_id: str) -> None:
    global _CURRENT_NODE_ID
    _CURRENT_NODE_ID = node_id


def set_service(name: str) -> None:
    global _SERVICE_NAME
    _SERVICE_NAME = name


# ---------------------------------------------------------------------------
# structlog processors
# ---------------------------------------------------------------------------

def _inject_context(
    logger: WrappedLogger, method: str, event_dict: EventDict
) -> EventDict:
    """Inject shared runtime context into every log record."""
    event_dict["service"] = _SERVICE_NAME
    event_dict["epoch"]   = _CURRENT_EPOCH
    event_dict["netuid"]  = _NETUID
    if _CURRENT_NODE_ID is not None:
        event_dict["node_id"] = _CURRENT_NODE_ID
    return event_dict


def _order_keys(
    logger: WrappedLogger, method: str, event_dict: EventDict
) -> EventDict:
    """
    Re-order keys so the most important fields appear first in JSON output.
    structlog doesn't guarantee key order; we nudge it here.
    """
    priority = ["timestamp", "level", "service", "epoch", "netuid", "node_id", "event"]
    ordered: EventDict = {}
    for key in priority:
        if key in event_dict:
            ordered[key] = event_dict.pop(key)
    ordered.update(event_dict)
    return ordered


# ---------------------------------------------------------------------------
# Stdlib logging setup (feeds into structlog)
# ---------------------------------------------------------------------------

def _configure_stdlib_logging(
    log_dir: Optional[str] = None,
    log_level: int = logging.INFO,
    max_bytes: int = 50 * 1024 * 1024,  # 50 MB
    backup_count: int = 5,
) -> None:
    root = logging.getLogger()
    root.setLevel(log_level)

    # Remove any existing handlers to avoid duplicate output
    root.handlers.clear()

    # stdout handler
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(log_level)
    root.addHandler(stdout_handler)

    # Rotating file handler (optional)
    if log_dir:
        log_path = Path(log_dir) / f"{_SERVICE_NAME}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            filename=str(log_path),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(log_level)
        root.addHandler(file_handler)


# ---------------------------------------------------------------------------
# structlog configuration
# ---------------------------------------------------------------------------

def configure(
    service: str = "axon-graph",
    log_level: str = "INFO",
    log_dir: Optional[str] = None,
    json_output: bool = True,
) -> None:
    """
    Call once at process startup, e.g. in __main__ or Nomad entrypoint.

        from config.logging import configure
        configure(service="validator", log_level="DEBUG")
    """
    set_service(service)

    level = getattr(logging, log_level.upper(), logging.INFO)
    _configure_stdlib_logging(log_dir=log_dir, log_level=level)

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
        _inject_context,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if json_output:
        shared_processors.append(_order_keys)
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


# ---------------------------------------------------------------------------
# Logger factory
# ---------------------------------------------------------------------------

def get_logger(name: str = "") -> structlog.BoundLogger:
    """
    Return a bound structlog logger.

        log = get_logger("validator")
        log.info("epoch_start", epoch=42)
    """
    return structlog.get_logger(name)


# ---------------------------------------------------------------------------
# EpochLogger — convenience wrapper that auto-tags epoch on every call
# ---------------------------------------------------------------------------

class EpochLogger:
    """
    Thin wrapper around a structlog logger that automatically stamps
    the current epoch and an optional node_id on every call.

    Usage:
        logger = EpochLogger("validator")
        logger.info("scoring_started", uids=[0, 1, 2])
    """

    def __init__(self, service: str, node_id: Optional[str] = None):
        self._log = get_logger(service)
        self._node_id = node_id

    def _bind(self, **kwargs: Any) -> structlog.BoundLogger:
        bound = self._log.bind(epoch=_CURRENT_EPOCH)
        if self._node_id:
            bound = bound.bind(node_id=self._node_id)
        if kwargs:
            bound = bound.bind(**kwargs)
        return bound

    def debug(self, event: str, **kw: Any) -> None:
        self._bind(**kw).debug(event)

    def info(self, event: str, **kw: Any) -> None:
        self._bind(**kw).info(event)

    def warning(self, event: str, **kw: Any) -> None:
        self._bind(**kw).warning(event)

    def error(self, event: str, **kw: Any) -> None:
        self._bind(**kw).error(event)

    def critical(self, event: str, **kw: Any) -> None:
        self._bind(**kw).critical(event)


# ---------------------------------------------------------------------------
# Auto-configure with sensible defaults if imported without explicit setup
# ---------------------------------------------------------------------------

_configured = False

def _auto_configure() -> None:
    global _configured
    if not _configured:
        configure(service="axon-graph", log_level="INFO", json_output=True)
        _configured = True

_auto_configure()
