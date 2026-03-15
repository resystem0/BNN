"""
orchestrator/gateway.py
FastAPI application — the public-facing entry point for end-user clients.

Endpoints:
  POST /enter              — start a new session at a knowledge-graph entry node
  POST /hop                — advance the session by one hop along the graph
  GET  /session/{id}       — retrieve current session state
  WS   /session/{id}/live  — WebSocket stream for real-time hop delivery
  GET  /healthz            — liveness probe
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from config.subnet_config import SubnetConfig
from orchestrator.session import OrchestratorSession, SessionState
from orchestrator.router import Router
from orchestrator.embedder import Embedder
from orchestrator.safety_guard import PathSafetyGuard
from subnet.graph_store import GraphStore

import bittensor as bt


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class EnterRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000, description="User's entry query")
    persona: str = Field(default="neutral", description="Narrative persona")
    max_hops: int = Field(default=5, ge=1, le=20)
    entry_node_id: Optional[str] = Field(default=None, description="Override entry node")


class EnterResponse(BaseModel):
    session_id: str
    entry_node_id: str
    entry_narrative: str
    path: List[str]
    available_next_nodes: List[str]


class HopRequest(BaseModel):
    session_id: str
    to_node_id: str


class HopResponse(BaseModel):
    session_id: str
    from_node_id: str
    to_node_id: str
    hop_text: str
    path: List[str]
    available_next_nodes: List[str]
    is_terminal: bool


class SessionResponse(BaseModel):
    session_id: str
    path: List[str]
    narrative_so_far: str
    current_node_id: Optional[str]
    is_terminal: bool
    hop_count: int


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(
    graph_store: GraphStore,
    embedder: Embedder,
    router: Router,
    safety_guard: PathSafetyGuard,
    wallet: bt.wallet,
    subtensor: bt.subtensor,
    metagraph: bt.metagraph,
    cfg: Optional[SubnetConfig] = None,
) -> FastAPI:
    cfg = cfg or SubnetConfig()

    app = FastAPI(
        title="axon-graph gateway",
        version="0.1.0",
        description="Knowledge-graph narrative traversal API",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.GATEWAY_CORS_ORIGINS,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # In-memory session registry (replace with Redis for multi-instance HA)
    _sessions: Dict[str, OrchestratorSession] = {}

    # ── helpers ──────────────────────────────────────────────────────────

    def _get_session(session_id: str) -> OrchestratorSession:
        sess = _sessions.get(session_id)
        if sess is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session '{session_id}' not found.",
            )
        return sess

    def _make_session() -> OrchestratorSession:
        session_id = str(uuid.uuid4())
        sess = OrchestratorSession(
            session_id=session_id,
            graph_store=graph_store,
            embedder=embedder,
            router=router,
            safety_guard=safety_guard,
            wallet=wallet,
            subtensor=subtensor,
            metagraph=metagraph,
            cfg=cfg,
        )
        _sessions[session_id] = sess
        return sess

    # ── /healthz ─────────────────────────────────────────────────────────

    @app.get("/healthz", tags=["meta"])
    async def healthz() -> Dict[str, Any]:
        return {
            "status": "ok",
            "active_sessions": len(_sessions),
            "graph_stats": graph_store.stats(),
        }

    # ── POST /enter ───────────────────────────────────────────────────────

    @app.post("/enter", response_model=EnterResponse, tags=["traversal"])
    async def enter(req: EnterRequest) -> EnterResponse:
        sess = _make_session()
        try:
            result = await sess.enter(
                query=req.query,
                persona=req.persona,
                max_hops=req.max_hops,
                entry_node_id=req.entry_node_id,
            )
        except Exception as exc:
            bt.logging.error(f"[session={sess.session_id}] /enter error: {exc}", exc_info=True)
            _sessions.pop(sess.session_id, None)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(exc),
            )

        return EnterResponse(
            session_id=sess.session_id,
            entry_node_id=result["entry_node_id"],
            entry_narrative=result["entry_narrative"],
            path=sess.path,
            available_next_nodes=result["available_next_nodes"],
        )

    # ── POST /hop ─────────────────────────────────────────────────────────

    @app.post("/hop", response_model=HopResponse, tags=["traversal"])
    async def hop(req: HopRequest) -> HopResponse:
        sess = _get_session(req.session_id)

        if sess.state == SessionState.TERMINAL:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Session has reached its terminal node.",
            )

        try:
            result = await sess.hop(to_node_id=req.to_node_id)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
        except Exception as exc:
            bt.logging.error(f"[session={req.session_id}] /hop error: {exc}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(exc),
            )

        return HopResponse(
            session_id=sess.session_id,
            from_node_id=result["from_node_id"],
            to_node_id=result["to_node_id"],
            hop_text=result["hop_text"],
            path=sess.path,
            available_next_nodes=result["available_next_nodes"],
            is_terminal=sess.state == SessionState.TERMINAL,
        )

    # ── GET /session/{id} ────────────────────────────────────────────────

    @app.get("/session/{session_id}", response_model=SessionResponse, tags=["session"])
    async def get_session(session_id: str) -> SessionResponse:
        sess = _get_session(session_id)
        return SessionResponse(
            session_id=sess.session_id,
            path=sess.path,
            narrative_so_far=sess.narrative_so_far,
            current_node_id=sess.current_node_id,
            is_terminal=sess.state == SessionState.TERMINAL,
            hop_count=len(sess.path) - 1 if sess.path else 0,
        )

    # ── WS /session/{id}/live ────────────────────────────────────────────

    @app.websocket("/session/{session_id}/live")
    async def ws_session(websocket: WebSocket, session_id: str) -> None:
        """
        WebSocket endpoint: the client sends hop requests as JSON
        ``{"to_node_id": "..."}`` and receives streamed hop responses.

        The connection is closed when the session reaches a terminal node
        or the client disconnects.
        """
        await websocket.accept()
        sess = _sessions.get(session_id)
        if sess is None:
            await websocket.send_json({"error": f"session '{session_id}' not found"})
            await websocket.close(code=1008)
            return

        try:
            while True:
                data = await websocket.receive_json()
                to_node = data.get("to_node_id")
                if not to_node:
                    await websocket.send_json({"error": "missing to_node_id"})
                    continue

                if sess.state == SessionState.TERMINAL:
                    await websocket.send_json({"event": "terminal", "path": sess.path})
                    await websocket.close()
                    return

                try:
                    result = await sess.hop(to_node_id=to_node)
                    await websocket.send_json({
                        "event": "hop",
                        "from_node_id": result["from_node_id"],
                        "to_node_id": result["to_node_id"],
                        "hop_text": result["hop_text"],
                        "path": sess.path,
                        "available_next_nodes": result["available_next_nodes"],
                        "is_terminal": sess.state == SessionState.TERMINAL,
                    })
                except ValueError as exc:
                    await websocket.send_json({"error": str(exc)})
                except Exception as exc:
                    bt.logging.error(f"WS hop error: {exc}", exc_info=True)
                    await websocket.send_json({"error": "internal error"})

        except WebSocketDisconnect:
            bt.logging.info(f"WebSocket disconnected for session={session_id}")

    return app
