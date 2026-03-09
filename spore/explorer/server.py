"""Spore Explorer — FastAPI server with REST + WebSocket for the research graph."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from ..node import SporeNode
from ..record import ExperimentRecord, Status

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


class ConnectionManager:
    """Manages active WebSocket connections."""

    def __init__(self):
        self._active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self._active:
            self._active.remove(ws)

    async def broadcast(self, data: dict):
        dead = []
        for ws in self._active:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    @property
    def count(self) -> int:
        return len(self._active)


def _record_to_dict(r: ExperimentRecord) -> dict:
    status = r.status.value if isinstance(r.status, Status) else r.status
    return {
        "id": r.id,
        "parent": r.parent,
        "depth": r.depth,
        "code_cid": r.code_cid,
        "diff": r.diff,
        "dataset_cid": r.dataset_cid,
        "prepare_cid": r.prepare_cid,
        "time_budget": r.time_budget,
        "val_bpb": r.val_bpb,
        "peak_vram_mb": r.peak_vram_mb,
        "num_steps": r.num_steps,
        "num_params": r.num_params,
        "status": status,
        "description": r.description,
        "hypothesis": r.hypothesis,
        "agent_model": r.agent_model,
        "gpu_model": r.gpu_model,
        "cuda_version": r.cuda_version,
        "torch_version": r.torch_version,
        "node_id": r.node_id,
        "timestamp": r.timestamp,
        "signature": r.signature,
        "version": r.version,
    }


def create_app(node: SporeNode) -> FastAPI:
    app = FastAPI(title="Spore Explorer", version="0.1.0")
    ws_manager = ConnectionManager()

    # Register listener so gossip pushes new experiments to WebSocket clients
    def on_new_experiment(record: ExperimentRecord):
        data = {"event": "experiment", "data": _record_to_dict(record)}
        try:
            loop = asyncio.get_running_loop()
            asyncio.ensure_future(ws_manager.broadcast(data), loop=loop)
        except RuntimeError:
            pass  # No event loop running

    node.add_listener(on_new_experiment)

    # --- Static ---

    @app.get("/", response_class=HTMLResponse)
    async def index():
        html_path = STATIC_DIR / "index.html"
        return HTMLResponse(html_path.read_text())

    # --- REST API ---

    @app.get("/api/stat")
    async def stat():
        total = node.graph.count()
        frontier = node.graph.frontier()
        best_bpb = frontier[0].val_bpb if frontier else None
        return {
            "experiment_count": total,
            "frontier_size": len(frontier),
            "best_val_bpb": best_bpb,
            "peer_count": len(node.gossip.peers),
            "node_id": node.node_id,
            "ws_client": ws_manager.count,
        }

    @app.get("/api/graph")
    async def graph():
        records = node.graph.all_records()
        frontier = node.graph.frontier()
        frontier_id = {r.id for r in frontier}

        nodes = []
        edges = []
        for r in records:
            nodes.append(_record_to_dict(r))
            if r.parent:
                edges.append({"source": r.parent, "target": r.id})

        return {
            "node": nodes,
            "edge": edges,
            "frontier_id": list(frontier_id),
        }

    @app.get("/api/frontier")
    async def frontier(gpu: str | None = None):
        results = node.graph.frontier(gpu_class=gpu)
        return [_record_to_dict(r) for r in results]

    @app.get("/api/experiment/{cid}")
    async def experiment(cid: str):
        record = node.graph.get(cid)
        if not record:
            return {"error": "not found"}
        return _record_to_dict(record)

    @app.get("/api/experiment/{cid}/ancestor")
    async def ancestor(cid: str):
        chain = node.graph.ancestors(cid)
        return [_record_to_dict(r) for r in chain]

    @app.get("/api/leaderboard")
    async def leaderboard():
        return node.reputation.leaderboard(limit=50)

    # --- WebSocket ---

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        await ws_manager.connect(ws)
        try:
            while True:
                await ws.receive_text()  # Keep connection alive
        except WebSocketDisconnect:
            ws_manager.disconnect(ws)

    return app
