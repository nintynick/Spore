"""Reputation persistence and idempotent event tracking."""

from __future__ import annotations

import sqlite3
from collections import Counter
from pathlib import Path

from .record import ExperimentRecord, Status

VERIFIED_KEEP_REWARD = 1.0
VERIFIED_FRONTIER_KEEP_REWARD = 2.0
SUCCESSFUL_CHALLENGE_REWARD = 1.0
WINNING_VERIFIER_REWARD = 0.5
WRONG_DISPUTE_SIDE_PENALTY = -1.0
REJECTED_EXPERIMENT_PENALTY = -5.0

REPUTATION_SCHEMA = """
CREATE TABLE IF NOT EXISTS reputation (
    node_id     TEXT PRIMARY KEY,
    score       REAL NOT NULL DEFAULT 0.0,
    experiments_published   INTEGER NOT NULL DEFAULT 0,
    experiments_verified    INTEGER NOT NULL DEFAULT 0,
    verifications_performed INTEGER NOT NULL DEFAULT 0,
    disputes_won            INTEGER NOT NULL DEFAULT 0,
    disputes_lost           INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS reputation_event (
    event_id TEXT PRIMARY KEY,
    kind     TEXT NOT NULL
);
"""


class ReputationStore:
    """SQLite-backed reputation tracking for network nodes."""

    def __init__(self, db_path: str | Path = ":memory:"):
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False, timeout=10)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(REPUTATION_SCHEMA)

    def close(self):
        self.conn.close()

    def get_score(self, node_id: str) -> float:
        row = self.conn.execute(
            "SELECT score FROM reputation WHERE node_id = ?", (node_id,)
        ).fetchone()
        return row["score"] if row else 0.0

    def get_stats(self, node_id: str) -> dict:
        row = self.conn.execute(
            "SELECT * FROM reputation WHERE node_id = ?", (node_id,)
        ).fetchone()
        if not row:
            return {
                "node_id": node_id,
                "score": 0.0,
                "experiments_published": 0,
                "experiments_verified": 0,
                "verifications_performed": 0,
                "disputes_won": 0,
                "disputes_lost": 0,
            }
        return dict(row)

    def update_score(self, node_id: str, delta: float, field: str | None = None):
        """Update a node's reputation score and optionally increment a counter."""
        self._ensure_node(node_id)
        new_score = max(-100.0, min(100.0, self.get_score(node_id) + delta))
        if field:
            self.conn.execute(
                f"UPDATE reputation SET score = ?, {field} = {field} + 1 WHERE node_id = ?",
                (new_score, node_id),
            )
        else:
            self.conn.execute(
                "UPDATE reputation SET score = ? WHERE node_id = ?",
                (new_score, node_id),
            )
        self.conn.commit()

    def increment_counter(self, node_id: str, field: str):
        """Increment a non-score reputation counter."""
        self._ensure_node(node_id)
        self.conn.execute(
            f"UPDATE reputation SET {field} = {field} + 1 WHERE node_id = ?",
            (node_id,),
        )
        self.conn.commit()

    def record_published(self, node_id: str, record: ExperimentRecord):
        """Update reputation when a node publishes an experiment."""
        del record
        self.increment_counter(node_id, "experiments_published")

    def record_verified(
        self, node_id: str, record: ExperimentRecord, is_frontier: bool = False
    ):
        """Update reputation when a node's experiment is verified."""
        status = (
            record.status
            if isinstance(record.status, Status)
            else Status(record.status)
        )
        delta = 0.0
        if status == Status.KEEP:
            delta = (
                VERIFIED_FRONTIER_KEEP_REWARD if is_frontier else VERIFIED_KEEP_REWARD
            )
        self.update_score(node_id, delta, "experiments_verified")

    def verification_performed(self, verifier_id: str):
        """Track that a node performed a verification without changing score."""
        self.increment_counter(verifier_id, "verifications_performed")

    def reward_successful_challenge(self, challenger_id: str):
        """Reward a challenger who exposed a bad claim."""
        self.update_score(challenger_id, SUCCESSFUL_CHALLENGE_REWARD, "disputes_won")

    def reward_winning_verifier(self, verifier_id: str):
        """Reward a verifier on the correct side of a resolved dispute."""
        self.update_score(verifier_id, WINNING_VERIFIER_REWARD, "disputes_won")

    def penalize_wrong_dispute_side(self, node_id: str):
        """Penalize a challenger or verifier that was wrong in dispute resolution."""
        self.update_score(node_id, WRONG_DISPUTE_SIDE_PENALTY, "disputes_lost")

    def penalize_rejected_experiment(self, node_id: str):
        """Strong penalty for a published claim rejected by dispute."""
        self.update_score(node_id, REJECTED_EXPERIMENT_PENALTY, "disputes_lost")

    def leaderboard(self, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM reputation ORDER BY score DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def all_stats(self) -> list[dict]:
        """Return all known reputation rows in a stable order."""
        rows = self.conn.execute(
            """
            SELECT * FROM reputation
            ORDER BY score DESC, experiments_published DESC, node_id ASC
            """
        ).fetchall()
        return [dict(r) for r in rows]

    def record_event(self, event_id: str, kind: str) -> bool:
        """Record a processed event. Returns True if it was new."""
        cursor = self.conn.execute(
            "INSERT OR IGNORE INTO reputation_event (event_id, kind) VALUES (?, ?)",
            (event_id, kind),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def backfill_published(self, records: list[ExperimentRecord]):
        """Ensure publish counts exist for already-synced experiments."""
        counts = Counter(r.node_id for r in records if r.node_id)
        for node_id, published in counts.items():
            self._ensure_node(node_id)
            row = self.conn.execute(
                "SELECT experiments_published FROM reputation WHERE node_id = ?",
                (node_id,),
            ).fetchone()
            current = row["experiments_published"] if row else 0
            if current < published:
                self.conn.execute(
                    "UPDATE reputation SET experiments_published = ? WHERE node_id = ?",
                    (published, node_id),
                )
        self.conn.commit()

    def _ensure_node(self, node_id: str):
        self.conn.execute(
            "INSERT OR IGNORE INTO reputation (node_id, score) VALUES (?, 0.0)",
            (node_id,),
        )
        self.conn.commit()
