"""Spore Explorer — FastAPI server with REST + WebSocket for the research graph."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from ..node import SporeNode
from ..profile import NodeProfile
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


def _profile_to_dict(profile: NodeProfile | None) -> dict | None:
    if profile is None:
        return None
    return {
        "id": profile.id,
        "node_id": profile.node_id,
        "display_name": profile.display_name,
        "bio": profile.bio,
        "website": profile.website,
        "avatar_url": profile.avatar_url,
        "donation_address": profile.donation_address,
        "timestamp": profile.timestamp,
        "schema_version": profile.schema_version,
    }


def _record_with_profile(
    node: SporeNode,
    record: ExperimentRecord,
    *,
    frontier_ids: set[str] | None = None,
    verified_ids: set[str] | None = None,
    profiles_by_id: dict[str, NodeProfile] | None = None,
) -> dict:
    data = _record_to_dict(record)
    profile = None
    if profiles_by_id is not None:
        profile = profiles_by_id.get(record.node_id)
    if profile is None:
        profile = node.get_profile(record.node_id)
    if profile:
        data["node_display_name"] = profile.display_name
        data["node_avatar_url"] = profile.avatar_url
    data["verified"] = (
        record.id in verified_ids
        if verified_ids is not None
        else node.graph.is_verified(record.id)
    )
    data["is_frontier"] = (
        record.id in frontier_ids
        if frontier_ids is not None
        else record.id in {r.id for r in node.graph.frontier()}
    )
    return data


def _classify_node_activity(reputation: dict) -> str:
    published = reputation.get("experiments_published", 0)
    verifier_work = (
        reputation.get("verifications_performed", 0)
        + reputation.get("disputes_won", 0)
        + reputation.get("disputes_lost", 0)
    )
    if published and verifier_work:
        return "hybrid"
    if published:
        return "researcher"
    if verifier_work:
        return "verifier"
    return "observer"


def _record_matches_filters(
    record: ExperimentRecord,
    *,
    status: str = "all",
    gpu: str | None = None,
    verified_only: bool = False,
    frontier_only: bool = False,
    verified_ids: set[str] | None = None,
    frontier_ids: set[str] | None = None,
) -> bool:
    record_status = (
        record.status.value if isinstance(record.status, Status) else record.status
    )
    if status not in {"", "all"} and record_status != status:
        return False
    if gpu and record.gpu_model != gpu:
        return False
    if verified_only and (verified_ids is None or record.id not in verified_ids):
        return False
    if frontier_only and (frontier_ids is None or record.id not in frontier_ids):
        return False
    return True


def _build_node_summary(
    node_id: str,
    records: list[ExperimentRecord],
    profile: NodeProfile | None,
    reputation: dict,
    *,
    frontier_ids: set[str],
    verified_ids: set[str],
    node_ref: SporeNode,
) -> dict:
    keep_count = 0
    discard_count = 0
    crash_count = 0
    frontier_count = 0
    verified_count = 0
    gpu_models: set[str] = set()
    agent_models: set[str] = set()
    best_record: ExperimentRecord | None = None
    latest_record: ExperimentRecord | None = None

    for record in records:
        status = (
            record.status.value if isinstance(record.status, Status) else record.status
        )
        if status == Status.KEEP.value:
            keep_count += 1
        elif status == Status.DISCARD.value:
            discard_count += 1
        elif status == Status.CRASH.value:
            crash_count += 1
        if record.id in frontier_ids:
            frontier_count += 1
        if record.id in verified_ids:
            verified_count += 1
        if record.gpu_model:
            gpu_models.add(record.gpu_model)
        if record.agent_model:
            agent_models.add(record.agent_model)
        if best_record is None or record.val_bpb < best_record.val_bpb:
            best_record = record
        if latest_record is None or (
            record.timestamp,
            record.depth,
            record.id,
        ) >= (
            latest_record.timestamp,
            latest_record.depth,
            latest_record.id,
        ):
            latest_record = record

    summary = {
        "node_id": node_id,
        "display_name": profile.display_name if profile else "",
        "avatar_url": profile.avatar_url if profile else "",
        "bio": profile.bio if profile else "",
        "website": profile.website if profile else "",
        "donation_address": profile.donation_address if profile else "",
        "has_profile": profile is not None,
        "profile": _profile_to_dict(profile),
        "reputation": reputation,
        "activity": _classify_node_activity(reputation),
        "experiment_count": len(records),
        "keep_count": keep_count,
        "discard_count": discard_count,
        "crash_count": crash_count,
        "frontier_count": frontier_count,
        "verified_count": verified_count,
        "first_seen": min((r.timestamp for r in records), default=None),
        "last_seen": max((r.timestamp for r in records), default=None),
        "gpu_models": sorted(gpu_models),
        "agent_models": sorted(agent_models),
        "best_val_bpb": best_record.val_bpb if best_record else None,
        "best_experiment": (
            _record_with_profile(
                node_ref,
                best_record,
                frontier_ids=frontier_ids,
                verified_ids=verified_ids,
            )
            if best_record
            else None
        ),
        "latest_experiment": (
            _record_with_profile(
                node_ref,
                latest_record,
                frontier_ids=frontier_ids,
                verified_ids=verified_ids,
            )
            if latest_record
            else None
        ),
    }
    return summary


def _collect_explorer_state(node: SporeNode) -> dict:
    records = node.graph.all_records()
    frontier = node.graph.frontier()
    frontier_ids = {record.id for record in frontier}
    verified_ids = node.graph.verified_ids()
    profiles_by_id = {profile.node_id: profile for profile in node.profile.all()}
    reputation_by_id = {row["node_id"]: row for row in node.reputation.all_stats()}
    records_by_node: dict[str, list[ExperimentRecord]] = defaultdict(list)
    for record in records:
        records_by_node[record.node_id].append(record)

    all_node_ids = set(records_by_node) | set(profiles_by_id) | set(reputation_by_id)
    summaries = []
    for node_id in all_node_ids:
        reputation = reputation_by_id.get(node_id) or node.reputation.get_stats(node_id)
        profile = profiles_by_id.get(node_id)
        summaries.append(
            _build_node_summary(
                node_id,
                records_by_node.get(node_id, []),
                profile,
                reputation,
                frontier_ids=frontier_ids,
                verified_ids=verified_ids,
                node_ref=node,
            )
        )

    return {
        "records": records,
        "records_by_node": records_by_node,
        "frontier": frontier,
        "frontier_ids": frontier_ids,
        "verified_ids": verified_ids,
        "profiles_by_id": profiles_by_id,
        "summaries": summaries,
        "summaries_by_id": {summary["node_id"]: summary for summary in summaries},
    }


def create_app(node: SporeNode) -> FastAPI:
    app = FastAPI(title="Spore Explorer", version="0.1.0")
    ws_manager = ConnectionManager()

    def on_new_experiment(record: ExperimentRecord):
        data = {"event": "experiment", "data": _record_to_dict(record)}
        try:
            loop = asyncio.get_running_loop()
            asyncio.ensure_future(ws_manager.broadcast(data), loop=loop)
        except RuntimeError:
            pass

    node.add_listener(on_new_experiment)

    # --- Static ---

    @app.get("/", response_class=HTMLResponse)
    async def index():
        html_path = STATIC_DIR / "index.html"
        return HTMLResponse(html_path.read_text())

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # --- REST API ---

    @app.get("/api/stat")
    async def stat():
        explorer = _collect_explorer_state(node)
        best_bpb = explorer["frontier"][0].val_bpb if explorer["frontier"] else None
        return {
            "experiment_count": len(explorer["records"]),
            "frontier_size": len(explorer["frontier"]),
            "best_val_bpb": best_bpb,
            "peer_count": len(node.gossip.peers),
            "node_id": node.node_id,
            "ws_client": ws_manager.count,
            "node_count": len(explorer["summaries"]),
            "profile_count": len(explorer["profiles_by_id"]),
            "verified_experiment_count": len(explorer["verified_ids"]),
            "frontier_node_count": len(
                {
                    summary["node_id"]
                    for summary in explorer["summaries"]
                    if summary["frontier_count"] > 0
                }
            ),
        }

    @app.get("/api/graph")
    async def graph():
        explorer = _collect_explorer_state(node)

        nodes = []
        edges = []
        for record in explorer["records"]:
            nodes.append(
                _record_with_profile(
                    node,
                    record,
                    frontier_ids=explorer["frontier_ids"],
                    verified_ids=explorer["verified_ids"],
                    profiles_by_id=explorer["profiles_by_id"],
                )
            )
            if record.parent:
                edges.append({"source": record.parent, "target": record.id})

        return {
            "node": nodes,
            "edge": edges,
            "frontier_id": list(explorer["frontier_ids"]),
        }

    @app.get("/api/frontier")
    async def frontier(gpu: str | None = None):
        results = node.graph.frontier(gpu_class=gpu)
        frontier_ids = {record.id for record in results}
        verified_ids = node.graph.verified_ids()
        profiles_by_id = {profile.node_id: profile for profile in node.profile.all()}
        return [
            _record_with_profile(
                node,
                record,
                frontier_ids=frontier_ids,
                verified_ids=verified_ids,
                profiles_by_id=profiles_by_id,
            )
            for record in results
        ]

    @app.get("/api/experiment/{cid}")
    async def experiment(cid: str):
        record = node.graph.get(cid)
        if not record:
            return {"error": "not found"}
        return _record_with_profile(
            node,
            record,
            frontier_ids={r.id for r in node.graph.frontier()},
            verified_ids=node.graph.verified_ids(),
        )

    @app.get("/api/experiment/{cid}/ancestor")
    async def ancestor(cid: str):
        chain = node.graph.ancestors(cid)
        frontier_ids = {record.id for record in node.graph.frontier()}
        verified_ids = node.graph.verified_ids()
        profiles_by_id = {profile.node_id: profile for profile in node.profile.all()}
        return [
            _record_with_profile(
                node,
                record,
                frontier_ids=frontier_ids,
                verified_ids=verified_ids,
                profiles_by_id=profiles_by_id,
            )
            for record in chain
        ]

    @app.get("/api/experiment/{cid}/children")
    async def children(cid: str):
        kids = node.graph.children(cid)
        frontier_ids = {record.id for record in node.graph.frontier()}
        verified_ids = node.graph.verified_ids()
        profiles_by_id = {profile.node_id: profile for profile in node.profile.all()}
        return [
            _record_with_profile(
                node,
                record,
                frontier_ids=frontier_ids,
                verified_ids=verified_ids,
                profiles_by_id=profiles_by_id,
            )
            for record in kids
        ]

    @app.get("/api/recent")
    async def recent(limit: int = 50):
        records = node.graph.recent(limit=limit)
        frontier_ids = {record.id for record in node.graph.frontier()}
        verified_ids = node.graph.verified_ids()
        profiles_by_id = {profile.node_id: profile for profile in node.profile.all()}
        return [
            _record_with_profile(
                node,
                record,
                frontier_ids=frontier_ids,
                verified_ids=verified_ids,
                profiles_by_id=profiles_by_id,
            )
            for record in records
        ]

    @app.get("/api/nodes")
    async def nodes(
        activity: str = "all",
        status: str = "all",
        has_profile: bool | None = None,
        sort: str = "recent",
        limit: int = 100,
    ):
        explorer = _collect_explorer_state(node)
        summaries = []
        for summary in explorer["summaries"]:
            if activity not in {"", "all"} and summary["activity"] != activity:
                continue
            if status == Status.KEEP.value and summary["keep_count"] == 0:
                continue
            if status == Status.DISCARD.value and summary["discard_count"] == 0:
                continue
            if status == Status.CRASH.value and summary["crash_count"] == 0:
                continue
            if has_profile is not None and summary["has_profile"] != has_profile:
                continue
            summaries.append(summary)

        if sort == "score":
            summaries.sort(
                key=lambda item: (
                    item["reputation"]["score"],
                    item["reputation"]["experiments_published"],
                    item["last_seen"] or 0,
                ),
                reverse=True,
            )
        elif sort == "published":
            summaries.sort(
                key=lambda item: (
                    item["experiment_count"],
                    item["keep_count"],
                    item["last_seen"] or 0,
                ),
                reverse=True,
            )
        elif sort == "frontier":
            summaries.sort(
                key=lambda item: (
                    item["frontier_count"],
                    -(item["best_val_bpb"] or float("inf")),
                    item["last_seen"] or 0,
                ),
                reverse=True,
            )
        else:
            summaries.sort(
                key=lambda item: (
                    item["last_seen"] or 0,
                    item["experiment_count"],
                    item["reputation"]["score"],
                ),
                reverse=True,
            )

        return summaries[: max(1, min(limit, 500))]

    @app.get("/api/nodes/search")
    async def node_search(
        q: str = "",
        activity: str = "all",
        status: str = "all",
        limit: int = 20,
    ):
        if not q or len(q) < 2:
            return []
        q_lower = q.lower()
        results = []
        for summary in await nodes(
            activity=activity,
            status=status,
            has_profile=None,
            sort="recent",
            limit=max(1, min(limit * 5, 500)),
        ):
            if (
                q_lower in summary["node_id"].lower()
                or q_lower in summary["display_name"].lower()
                or q_lower in summary["bio"].lower()
                or q_lower in summary["website"].lower()
                or any(q_lower in gpu.lower() for gpu in summary["gpu_models"])
            ):
                results.append(summary)
            if len(results) >= limit:
                break
        return results

    @app.get("/api/node/{node_id}")
    async def node_detail(
        node_id: str,
        status: str = "all",
        gpu: str | None = None,
        verified_only: bool = False,
        frontier_only: bool = False,
        limit: int = 100,
        offset: int = 0,
    ):
        explorer = _collect_explorer_state(node)
        summary = explorer["summaries_by_id"].get(node_id)
        if summary is None:
            return {"error": "not found"}

        records = [
            record
            for record in explorer["records_by_node"].get(node_id, [])
            if _record_matches_filters(
                record,
                status=status,
                gpu=gpu,
                verified_only=verified_only,
                frontier_only=frontier_only,
                verified_ids=explorer["verified_ids"],
                frontier_ids=explorer["frontier_ids"],
            )
        ]
        paged_records = records[offset : offset + max(1, min(limit, 500))]
        return {
            "node": summary,
            "experiments": [
                _record_with_profile(
                    node,
                    record,
                    frontier_ids=explorer["frontier_ids"],
                    verified_ids=explorer["verified_ids"],
                    profiles_by_id=explorer["profiles_by_id"],
                )
                for record in paged_records
            ],
            "total_experiments": len(records),
            "filters": {
                "status": status,
                "gpu": gpu,
                "verified_only": verified_only,
                "frontier_only": frontier_only,
                "limit": limit,
                "offset": offset,
            },
        }

    @app.get("/api/node/{node_id}/experiment")
    async def node_experiment(
        node_id: str,
        status: str = "all",
        gpu: str | None = None,
        verified_only: bool = False,
        frontier_only: bool = False,
    ):
        explorer = _collect_explorer_state(node)
        records = [
            record
            for record in explorer["records_by_node"].get(node_id, [])
            if _record_matches_filters(
                record,
                status=status,
                gpu=gpu,
                verified_only=verified_only,
                frontier_only=frontier_only,
                verified_ids=explorer["verified_ids"],
                frontier_ids=explorer["frontier_ids"],
            )
        ]
        return [
            _record_with_profile(
                node,
                record,
                frontier_ids=explorer["frontier_ids"],
                verified_ids=explorer["verified_ids"],
                profiles_by_id=explorer["profiles_by_id"],
            )
            for record in records
        ]

    @app.get("/api/node/{node_id}/reputation")
    async def node_reputation(node_id: str):
        return node.reputation.get_stats(node_id)

    @app.get("/api/node/{node_id}/profile")
    async def node_profile(node_id: str):
        return _profile_to_dict(node.get_profile(node_id)) or {"error": "not found"}

    @app.get("/api/search")
    async def search(q: str = ""):
        """Search experiments by CID prefix, description, or node ID."""
        if not q or len(q) < 2:
            return []
        q_lower = q.lower()
        frontier_ids = {record.id for record in node.graph.frontier()}
        verified_ids = node.graph.verified_ids()
        profiles_by_id = {profile.node_id: profile for profile in node.profile.all()}
        results = []
        for r in node.graph.all_records():
            if (
                (r.id and r.id.startswith(q))
                or q_lower in r.description.lower()
                or (r.node_id and r.node_id.startswith(q))
                or q_lower in (r.gpu_model or "").lower()
                or q_lower
                in (
                    (
                        profiles_by_id.get(r.node_id) or NodeProfile(node_id=r.node_id)
                    ).display_name.lower()
                )
            ):
                results.append(
                    _record_with_profile(
                        node,
                        r,
                        frontier_ids=frontier_ids,
                        verified_ids=verified_ids,
                        profiles_by_id=profiles_by_id,
                    )
                )
            if len(results) >= 20:
                break
        return results

    @app.get("/api/leaderboard")
    async def leaderboard():
        rows = node.reputation.leaderboard(limit=50)
        for row in rows:
            profile = node.get_profile(row["node_id"])
            if profile:
                row["display_name"] = profile.display_name
                row["avatar_url"] = profile.avatar_url
            row["activity"] = _classify_node_activity(row)
            # Attach token balances
            if hasattr(node, "token"):
                token_summary = node.token.node_summary(row["node_id"])
                row["spore_balance"] = token_summary["spore_balance"]
                row["xspore_balance"] = token_summary["xspore_balance"]
                row["staked"] = token_summary["staked"]
        return rows

    # --- Token API ---

    @app.get("/api/token/stats")
    async def token_stats():
        """Global token statistics."""
        if not hasattr(node, "token"):
            return {"error": "token layer not enabled"}
        return node.token.global_stats()

    @app.get("/api/token/leaderboard")
    async def token_leaderboard(limit: int = 50):
        """Token leaderboard by $xSPORE contribution balance."""
        if not hasattr(node, "token"):
            return {"error": "token layer not enabled"}
        entries = node.token.leaderboard(limit)
        for entry in entries:
            profile = node.get_profile(entry["node_id"])
            if profile:
                entry["display_name"] = profile.display_name
                entry["avatar_url"] = profile.avatar_url
        return entries

    @app.get("/api/node/{node_id}/token")
    async def node_token(node_id: str):
        """Token summary for a specific node."""
        if not hasattr(node, "token"):
            return {"error": "token layer not enabled"}
        return node.token.node_summary(node_id)

    @app.get("/api/node/{node_id}/token/history")
    async def node_token_history(node_id: str, limit: int = 50):
        """Token event history for a specific node."""
        if not hasattr(node, "token"):
            return {"error": "token layer not enabled"}
        return node.token.event_history(node_id, limit)

    @app.get("/api/artifact/{cid}")
    async def artifact(cid: str):
        """Get stored code artifact by CID."""
        data = node.store.get(cid)
        if data is None:
            data = await node.fetch_code(cid)
        if data is None:
            return {"error": "not found"}
        return {"cid": cid, "content": data.decode("utf-8", errors="replace")}

    # --- WebSocket ---

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        await ws_manager.connect(ws)
        try:
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            ws_manager.disconnect(ws)

    return app
