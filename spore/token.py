"""Local token manager for the Spore incentive layer.

Provides an SQLite-backed local ledger that mirrors on-chain token state.
Operates in two modes:
  - ``local``  (default): All state is tracked in SQLite. No blockchain needed.
                          Suitable for development, testing, and solo operation.
  - ``chain``: Reads/writes from Base L2 via an RPC endpoint.  (future)

The local ledger tracks $SPORE balances, $xSPORE (contribution) balances,
staking positions, pending maturation rewards, and claim-fee redistribution.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from . import token_config as cfg

log = logging.getLogger(__name__)

TOKEN_SCHEMA = """
CREATE TABLE IF NOT EXISTS spore_balance (
    node_id TEXT PRIMARY KEY,
    balance REAL NOT NULL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS xspore_balance (
    node_id TEXT PRIMARY KEY,
    balance REAL NOT NULL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS stake (
    node_id TEXT PRIMARY KEY,
    amount  REAL NOT NULL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS pending_reward (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id   TEXT NOT NULL,
    amount    REAL NOT NULL,
    earned_at REAL NOT NULL,
    claimed   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_pending_node ON pending_reward(node_id, claimed);

CREATE TABLE IF NOT EXISTS token_event (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id  TEXT UNIQUE NOT NULL,
    node_id   TEXT NOT NULL,
    kind      TEXT NOT NULL,
    amount    REAL NOT NULL,
    detail    TEXT NOT NULL DEFAULT '',
    timestamp REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_token_event_node ON token_event(node_id);

CREATE TABLE IF NOT EXISTS token_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


@dataclass
class ClaimResult:
    xspore_burned: float
    spore_minted: float
    fee_paid: float
    fee_redistributed: float


class TokenManager:
    """SQLite-backed local token ledger for the Spore incentive layer."""

    def __init__(self, db_path: str | Path = ":memory:"):
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False, timeout=10)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(TOKEN_SCHEMA)
        self._init_meta()

    def close(self):
        self.conn.close()

    # -------------------------------------------------------------------
    # Meta
    # -------------------------------------------------------------------

    def _init_meta(self):
        self.conn.execute(
            "INSERT OR IGNORE INTO token_meta (key, value) VALUES ('total_spore_minted', '0')"
        )
        self.conn.execute(
            "INSERT OR IGNORE INTO token_meta (key, value) VALUES ('total_spore_burned', '0')"
        )
        self.conn.execute(
            "INSERT OR IGNORE INTO token_meta (key, value) VALUES ('genesis_experiments', '0')"
        )
        self.conn.commit()

    def _get_meta(self, key: str) -> str:
        row = self.conn.execute(
            "SELECT value FROM token_meta WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else "0"

    def _set_meta(self, key: str, value: str):
        self.conn.execute(
            "INSERT OR REPLACE INTO token_meta (key, value) VALUES (?, ?)",
            (key, value),
        )

    @property
    def total_spore_minted(self) -> float:
        return float(self._get_meta("total_spore_minted"))

    @property
    def total_spore_burned(self) -> float:
        return float(self._get_meta("total_spore_burned"))

    @property
    def genesis_experiments(self) -> int:
        return int(self._get_meta("genesis_experiments"))

    @property
    def in_genesis_epoch(self) -> bool:
        return self.genesis_experiments < cfg.GENESIS_EPOCH_EXPERIMENTS

    # -------------------------------------------------------------------
    # Balance queries
    # -------------------------------------------------------------------

    def _ensure_node(self, node_id: str):
        self.conn.execute(
            "INSERT OR IGNORE INTO spore_balance (node_id, balance) VALUES (?, 0.0)",
            (node_id,),
        )
        self.conn.execute(
            "INSERT OR IGNORE INTO xspore_balance (node_id, balance) VALUES (?, 0.0)",
            (node_id,),
        )
        self.conn.execute(
            "INSERT OR IGNORE INTO stake (node_id, amount) VALUES (?, 0.0)",
            (node_id,),
        )

    def spore_balance(self, node_id: str) -> float:
        self._ensure_node(node_id)
        row = self.conn.execute(
            "SELECT balance FROM spore_balance WHERE node_id = ?", (node_id,)
        ).fetchone()
        return row["balance"] if row else 0.0

    def xspore_balance(self, node_id: str) -> float:
        self._ensure_node(node_id)
        row = self.conn.execute(
            "SELECT balance FROM xspore_balance WHERE node_id = ?", (node_id,)
        ).fetchone()
        return row["balance"] if row else 0.0

    def stake_amount(self, node_id: str) -> float:
        self._ensure_node(node_id)
        row = self.conn.execute(
            "SELECT amount FROM stake WHERE node_id = ?", (node_id,)
        ).fetchone()
        return row["amount"] if row else 0.0

    # -------------------------------------------------------------------
    # $SPORE operations
    # -------------------------------------------------------------------

    def mint_spore(self, node_id: str, amount: float, reason: str = "") -> bool:
        """Mint $SPORE to a node. Respects max supply."""
        if amount <= 0:
            return False
        if self.total_spore_minted + amount > cfg.SPORE_MAX_SUPPLY:
            log.warning("Mint would exceed max supply, capping")
            amount = cfg.SPORE_MAX_SUPPLY - self.total_spore_minted
            if amount <= 0:
                return False
        self._ensure_node(node_id)
        self.conn.execute(
            "UPDATE spore_balance SET balance = balance + ? WHERE node_id = ?",
            (amount, node_id),
        )
        self._set_meta("total_spore_minted", str(self.total_spore_minted + amount))
        self._record_event(node_id, "spore_mint", amount, reason)
        self.conn.commit()
        return True

    def burn_spore(self, node_id: str, amount: float, reason: str = "") -> float:
        """Burn $SPORE from a node. Returns actual amount burned."""
        if amount <= 0:
            return 0.0
        self._ensure_node(node_id)
        balance = self.spore_balance(node_id)
        actual = min(amount, balance)
        if actual <= 0:
            return 0.0
        self.conn.execute(
            "UPDATE spore_balance SET balance = balance - ? WHERE node_id = ?",
            (actual, node_id),
        )
        self._set_meta("total_spore_burned", str(self.total_spore_burned + actual))
        self._record_event(node_id, "spore_burn", actual, reason)
        self.conn.commit()
        return actual

    # -------------------------------------------------------------------
    # $xSPORE operations
    # -------------------------------------------------------------------

    def mint_xspore(self, node_id: str, amount: float, reason: str = "") -> bool:
        """Mint $xSPORE (contribution credits) to a node."""
        if amount <= 0:
            return False
        self._ensure_node(node_id)
        self.conn.execute(
            "UPDATE xspore_balance SET balance = balance + ? WHERE node_id = ?",
            (amount, node_id),
        )
        self.conn.execute(
            "INSERT INTO pending_reward (node_id, amount, earned_at) VALUES (?, ?, ?)",
            (node_id, amount, time.time()),
        )
        self._record_event(node_id, "xspore_mint", amount, reason)
        self.conn.commit()
        return True

    def burn_xspore(self, node_id: str, amount: float, reason: str = "") -> float:
        """Burn $xSPORE from a node (penalty). Returns actual amount burned."""
        if amount <= 0:
            return 0.0
        self._ensure_node(node_id)
        balance = self.xspore_balance(node_id)
        actual = min(amount, balance)
        if actual <= 0:
            return 0.0
        self.conn.execute(
            "UPDATE xspore_balance SET balance = balance - ? WHERE node_id = ?",
            (actual, node_id),
        )
        self._record_event(node_id, "xspore_burn", actual, reason)
        self.conn.commit()
        return actual

    # -------------------------------------------------------------------
    # Staking
    # -------------------------------------------------------------------

    def add_stake(self, node_id: str, amount: float) -> bool:
        """Stake $SPORE (transfers from balance to stake)."""
        if amount <= 0:
            return False
        self._ensure_node(node_id)
        balance = self.spore_balance(node_id)
        if balance < amount:
            return False
        self.conn.execute(
            "UPDATE spore_balance SET balance = balance - ? WHERE node_id = ?",
            (amount, node_id),
        )
        self.conn.execute(
            "UPDATE stake SET amount = amount + ? WHERE node_id = ?",
            (amount, node_id),
        )
        self._record_event(node_id, "stake", amount, "")
        self.conn.commit()
        return True

    def remove_stake(self, node_id: str, amount: float) -> bool:
        """Unstake $SPORE (transfers from stake to balance)."""
        if amount <= 0:
            return False
        self._ensure_node(node_id)
        current_stake = self.stake_amount(node_id)
        if current_stake < amount:
            return False
        self.conn.execute(
            "UPDATE stake SET amount = amount - ? WHERE node_id = ?",
            (amount, node_id),
        )
        self.conn.execute(
            "UPDATE spore_balance SET balance = balance + ? WHERE node_id = ?",
            (amount, node_id),
        )
        self._record_event(node_id, "unstake", amount, "")
        self.conn.commit()
        return True

    def slash_stake(self, node_id: str, amount: float, reason: str = "") -> float:
        """Slash staked $SPORE (burned, not returned). Returns actual slashed."""
        if amount <= 0:
            return 0.0
        self._ensure_node(node_id)
        current = self.stake_amount(node_id)
        actual = min(amount, current)
        if actual <= 0:
            return 0.0
        self.conn.execute(
            "UPDATE stake SET amount = amount - ? WHERE node_id = ?",
            (actual, node_id),
        )
        self._set_meta("total_spore_burned", str(self.total_spore_burned + actual))
        self._record_event(node_id, "slash", actual, reason)
        self.conn.commit()
        return actual

    def has_sufficient_stake(self, node_id: str, required: float) -> bool:
        """Check if a node has enough staked $SPORE."""
        return self.stake_amount(node_id) >= required

    # -------------------------------------------------------------------
    # Claiming / maturation
    # -------------------------------------------------------------------

    def claim_rewards(self, node_id: str) -> ClaimResult | None:
        """Claim all pending $xSPORE → $SPORE with maturation curve.

        Returns None if nothing to claim.
        """
        self._ensure_node(node_id)
        rows = self.conn.execute(
            "SELECT id, amount, earned_at FROM pending_reward "
            "WHERE node_id = ? AND claimed = 0",
            (node_id,),
        ).fetchall()

        if not rows:
            return None

        now = time.time()
        total_xburned = 0.0
        total_spore = 0.0
        total_fee = 0.0

        for row in rows:
            age_days = (now - row["earned_at"]) / 86400
            rate, fee_pct = self._maturation_rate(age_days)
            amount = row["amount"]
            spore_out = amount * rate
            fee = amount * fee_pct

            total_xburned += amount
            total_spore += spore_out
            total_fee += fee

            self.conn.execute(
                "UPDATE pending_reward SET claimed = 1 WHERE id = ?",
                (row["id"],),
            )

        # Burn $xSPORE
        self.conn.execute(
            "UPDATE xspore_balance SET balance = balance - ? WHERE node_id = ?",
            (total_xburned, node_id),
        )

        # Mint $SPORE
        if total_spore > 0:
            self._mint_spore_internal(node_id, total_spore)

        # Redistribute fees to other unclaimed holders
        fee_redistributed = 0.0
        if total_fee > 0:
            fee_redistributed = self._redistribute_fee(node_id, total_fee)

        self._record_event(node_id, "claim", total_spore, f"fee={total_fee:.2f}")
        self.conn.commit()

        return ClaimResult(
            xspore_burned=total_xburned,
            spore_minted=total_spore,
            fee_paid=total_fee,
            fee_redistributed=fee_redistributed,
        )

    def estimate_claim(self, node_id: str) -> tuple[float, float, float]:
        """Estimate claimable $SPORE without actually claiming.

        Returns (spore_out, fee, xspore_burned).
        """
        rows = self.conn.execute(
            "SELECT amount, earned_at FROM pending_reward "
            "WHERE node_id = ? AND claimed = 0",
            (node_id,),
        ).fetchall()

        now = time.time()
        total_spore = 0.0
        total_fee = 0.0
        total_xburned = 0.0

        for row in rows:
            age_days = (now - row["earned_at"]) / 86400
            rate, fee_pct = self._maturation_rate(age_days)
            amount = row["amount"]
            total_spore += amount * rate
            total_fee += amount * fee_pct
            total_xburned += amount

        return total_spore, total_fee, total_xburned

    @staticmethod
    def _maturation_rate(age_days: float) -> tuple[float, float]:
        """Return (conversion_rate, fee_rate) based on age in days."""
        for min_days, rate, fee in reversed(cfg.MATURATION_TIERS):
            if age_days >= min_days:
                return rate / 100.0, fee / 100.0
        return 0.50, 0.50

    def _mint_spore_internal(self, node_id: str, amount: float):
        """Internal mint without event recording (used by claim)."""
        current_minted = self.total_spore_minted
        if current_minted + amount > cfg.SPORE_MAX_SUPPLY:
            amount = cfg.SPORE_MAX_SUPPLY - current_minted
        if amount <= 0:
            return
        self.conn.execute(
            "UPDATE spore_balance SET balance = balance + ? WHERE node_id = ?",
            (amount, node_id),
        )
        self._set_meta("total_spore_minted", str(current_minted + amount))

    def _redistribute_fee(self, claimer_id: str, fee_amount: float) -> float:
        """Redistribute claim fees to all other nodes with unclaimed $xSPORE."""
        rows = self.conn.execute(
            "SELECT node_id, SUM(amount) as total "
            "FROM pending_reward WHERE claimed = 0 AND node_id != ? "
            "GROUP BY node_id HAVING total > 0",
            (claimer_id,),
        ).fetchall()
        if not rows:
            return 0.0
        total_unclaimed = sum(r["total"] for r in rows)
        distributed = 0.0
        for row in rows:
            share = (row["total"] / total_unclaimed) * fee_amount
            self.conn.execute(
                "INSERT INTO pending_reward (node_id, amount, earned_at) VALUES (?, ?, ?)",
                (row["node_id"], share, time.time()),
            )
            self.conn.execute(
                "UPDATE xspore_balance SET balance = balance + ? WHERE node_id = ?",
                (share, row["node_id"]),
            )
            distributed += share
        return distributed

    # -------------------------------------------------------------------
    # Reward actions (called by reputation hooks)
    # -------------------------------------------------------------------

    def reward_verified_keep(self, node_id: str, is_frontier: bool = False):
        """Reward a node for a verified 'keep' experiment."""
        amount = cfg.REWARD_VERIFIED_FRONTIER if is_frontier else cfg.REWARD_VERIFIED_KEEP
        reason = "verified_frontier_keep" if is_frontier else "verified_keep"

        # During genesis epoch, also mint $SPORE directly
        if self.in_genesis_epoch:
            self.mint_spore(node_id, amount, f"genesis_{reason}")
            genesis_count = self.genesis_experiments + 1
            self._set_meta("genesis_experiments", str(genesis_count))
            self.conn.commit()

        self.mint_xspore(node_id, amount, reason)

    def reward_verification_performed(self, node_id: str):
        """Reward a verifier for performing a spot-check."""
        self.mint_xspore(node_id, cfg.REWARD_VERIFICATION_PERFORMED, "verification_performed")

    def reward_successful_challenge(self, node_id: str):
        """Reward a challenger who exposed a fraudulent claim."""
        self.mint_xspore(node_id, cfg.REWARD_SUCCESSFUL_CHALLENGE, "successful_challenge")

    def reward_winning_verifier(self, node_id: str):
        """Reward a verifier on the correct side of a dispute."""
        self.mint_xspore(node_id, cfg.REWARD_WINNING_VERIFIER, "winning_verifier")

    def penalize_wrong_dispute_side(self, node_id: str):
        """Penalize for being on the wrong side of a dispute."""
        self.burn_xspore(node_id, cfg.PENALTY_WRONG_DISPUTE_SIDE, "wrong_dispute_side")
        self.slash_stake(node_id, cfg.SLASH_WRONG_DISPUTE, "wrong_dispute_side")

    def penalize_rejected_experiment(self, node_id: str):
        """Heavy penalty for a published claim rejected by dispute."""
        self.burn_xspore(node_id, cfg.PENALTY_REJECTED_EXPERIMENT, "rejected_experiment")
        self.slash_stake(node_id, cfg.SLASH_REJECTED_EXPERIMENT, "rejected_experiment")

    # -------------------------------------------------------------------
    # Queries
    # -------------------------------------------------------------------

    def leaderboard(self, limit: int = 20) -> list[dict]:
        """Return top nodes by $xSPORE balance."""
        rows = self.conn.execute(
            "SELECT x.node_id, x.balance as xspore, "
            "COALESCE(s.balance, 0) as spore, "
            "COALESCE(st.amount, 0) as staked "
            "FROM xspore_balance x "
            "LEFT JOIN spore_balance s ON x.node_id = s.node_id "
            "LEFT JOIN stake st ON x.node_id = st.node_id "
            "ORDER BY x.balance DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def node_summary(self, node_id: str) -> dict:
        """Return full token summary for a node."""
        self._ensure_node(node_id)
        spore_out, fee, xburned = self.estimate_claim(node_id)
        return {
            "node_id": node_id,
            "spore_balance": self.spore_balance(node_id),
            "xspore_balance": self.xspore_balance(node_id),
            "staked": self.stake_amount(node_id),
            "pending_rewards": self.conn.execute(
                "SELECT COUNT(*) as c FROM pending_reward WHERE node_id = ? AND claimed = 0",
                (node_id,),
            ).fetchone()["c"],
            "claimable_spore": spore_out,
            "claim_fee": fee,
        }

    def event_history(self, node_id: str, limit: int = 50) -> list[dict]:
        """Return recent token events for a node."""
        rows = self.conn.execute(
            "SELECT * FROM token_event WHERE node_id = ? ORDER BY timestamp DESC LIMIT ?",
            (node_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def global_stats(self) -> dict:
        """Return global token statistics."""
        return {
            "total_spore_minted": self.total_spore_minted,
            "total_spore_burned": self.total_spore_burned,
            "circulating_spore": self.total_spore_minted - self.total_spore_burned,
            "max_supply": cfg.SPORE_MAX_SUPPLY,
            "genesis_experiments": self.genesis_experiments,
            "in_genesis_epoch": self.in_genesis_epoch,
        }

    # -------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------

    def _record_event(self, node_id: str, kind: str, amount: float, detail: str):
        event_id = f"{kind}:{node_id}:{time.time()}"
        self.conn.execute(
            "INSERT OR IGNORE INTO token_event "
            "(event_id, node_id, kind, amount, detail, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (event_id, node_id, kind, amount, detail, time.time()),
        )
