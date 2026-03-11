"""Mycelia — Fungal Intelligence Network local ledger.

SQLite-backed ledger that tracks the mycelium economy:
  $MYCO  balances (liquid token — the underground network currency)
  $HYPHA balances (non-transferable contribution hyphae)
  Inoculation positions (staked $MYCO)
  Pending fruiting rewards and decomposition-based fee redistribution

Operates in local mode by default (no blockchain required).
On-chain settlement on Base L2 is opt-in for production.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from . import token_config as cfg

log = logging.getLogger(__name__)

MYCELIUM_SCHEMA = """
CREATE TABLE IF NOT EXISTS myco_balance (
    node_id TEXT PRIMARY KEY,
    balance REAL NOT NULL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS hypha_balance (
    node_id TEXT PRIMARY KEY,
    balance REAL NOT NULL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS inoculation (
    node_id TEXT PRIMARY KEY,
    amount  REAL NOT NULL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS fruiting_body (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id   TEXT NOT NULL,
    amount    REAL NOT NULL,
    grown_at  REAL NOT NULL,
    harvested INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_fruiting_node ON fruiting_body(node_id, harvested);

CREATE TABLE IF NOT EXISTS mycelium_event (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id  TEXT UNIQUE NOT NULL,
    node_id   TEXT NOT NULL,
    kind      TEXT NOT NULL,
    amount    REAL NOT NULL,
    detail    TEXT NOT NULL DEFAULT '',
    timestamp REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mycelium_event_node ON mycelium_event(node_id);

CREATE TABLE IF NOT EXISTS substrate_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


@dataclass
class HarvestResult:
    """Result of harvesting matured $HYPHA into $MYCO."""
    hypha_consumed: float
    myco_yielded: float
    decomposed: float       # fee that decomposed back into substrate
    nutrient_recycled: float  # amount redistributed to other cultivators


# Backward-compatible aliases
ClaimResult = HarvestResult


class MyceliumLedger:
    """SQLite-backed local ledger for the Mycelia fungal intelligence network.

    Tracks $MYCO (liquid token), $HYPHA (contribution hyphae),
    inoculation (staking), and fruiting/harvesting cycles.
    """

    def __init__(self, db_path: str | Path = ":memory:"):
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False, timeout=10)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(MYCELIUM_SCHEMA)
        self._init_meta()

    def close(self):
        self.conn.close()

    # -------------------------------------------------------------------
    # Substrate metadata
    # -------------------------------------------------------------------

    def _init_meta(self):
        self.conn.execute(
            "INSERT OR IGNORE INTO substrate_meta (key, value) VALUES ('total_myco_minted', '0')"
        )
        self.conn.execute(
            "INSERT OR IGNORE INTO substrate_meta (key, value) VALUES ('total_myco_composted', '0')"
        )
        self.conn.execute(
            "INSERT OR IGNORE INTO substrate_meta (key, value) VALUES ('flush_count', '0')"
        )
        self.conn.commit()

    def _get_meta(self, key: str) -> str:
        row = self.conn.execute(
            "SELECT value FROM substrate_meta WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else "0"

    def _set_meta(self, key: str, value: str):
        self.conn.execute(
            "INSERT OR REPLACE INTO substrate_meta (key, value) VALUES (?, ?)",
            (key, value),
        )

    @property
    def total_myco_minted(self) -> float:
        return float(self._get_meta("total_myco_minted"))

    # Backward compat
    total_spore_minted = total_myco_minted

    @property
    def total_myco_composted(self) -> float:
        return float(self._get_meta("total_myco_composted"))

    total_spore_burned = total_myco_composted

    @property
    def flush_count(self) -> int:
        return int(self._get_meta("flush_count"))

    # Backward compat
    genesis_experiments = flush_count

    @property
    def in_first_flush(self) -> bool:
        return self.flush_count < cfg.FIRST_FLUSH_EXPERIMENTS

    in_genesis_epoch = in_first_flush

    # -------------------------------------------------------------------
    # Balance queries
    # -------------------------------------------------------------------

    def _ensure_cultivator(self, node_id: str):
        self.conn.execute(
            "INSERT OR IGNORE INTO myco_balance (node_id, balance) VALUES (?, 0.0)",
            (node_id,),
        )
        self.conn.execute(
            "INSERT OR IGNORE INTO hypha_balance (node_id, balance) VALUES (?, 0.0)",
            (node_id,),
        )
        self.conn.execute(
            "INSERT OR IGNORE INTO inoculation (node_id, amount) VALUES (?, 0.0)",
            (node_id,),
        )

    _ensure_node = _ensure_cultivator

    def myco_balance(self, node_id: str) -> float:
        self._ensure_cultivator(node_id)
        row = self.conn.execute(
            "SELECT balance FROM myco_balance WHERE node_id = ?", (node_id,)
        ).fetchone()
        return row["balance"] if row else 0.0

    spore_balance = myco_balance  # backward compat

    def hypha_balance(self, node_id: str) -> float:
        self._ensure_cultivator(node_id)
        row = self.conn.execute(
            "SELECT balance FROM hypha_balance WHERE node_id = ?", (node_id,)
        ).fetchone()
        return row["balance"] if row else 0.0

    xspore_balance = hypha_balance  # backward compat

    def inoculation_amount(self, node_id: str) -> float:
        self._ensure_cultivator(node_id)
        row = self.conn.execute(
            "SELECT amount FROM inoculation WHERE node_id = ?", (node_id,)
        ).fetchone()
        return row["amount"] if row else 0.0

    stake_amount = inoculation_amount  # backward compat

    # -------------------------------------------------------------------
    # $MYCO operations
    # -------------------------------------------------------------------

    def grow_myco(self, node_id: str, amount: float, reason: str = "") -> bool:
        """Grow (mint) $MYCO to a cultivator. Respects max supply."""
        if amount <= 0:
            return False
        if self.total_myco_minted + amount > cfg.MYCO_MAX_SUPPLY:
            log.warning("Growth would exceed max supply, capping")
            amount = cfg.MYCO_MAX_SUPPLY - self.total_myco_minted
            if amount <= 0:
                return False
        self._ensure_cultivator(node_id)
        self.conn.execute(
            "UPDATE myco_balance SET balance = balance + ? WHERE node_id = ?",
            (amount, node_id),
        )
        self._set_meta("total_myco_minted", str(self.total_myco_minted + amount))
        self._record_event(node_id, "myco_growth", amount, reason)
        self.conn.commit()
        return True

    mint_spore = grow_myco  # backward compat

    def compost_myco(self, node_id: str, amount: float, reason: str = "") -> float:
        """Compost (burn) $MYCO from a cultivator. Returns actual composted."""
        if amount <= 0:
            return 0.0
        self._ensure_cultivator(node_id)
        balance = self.myco_balance(node_id)
        actual = min(amount, balance)
        if actual <= 0:
            return 0.0
        self.conn.execute(
            "UPDATE myco_balance SET balance = balance - ? WHERE node_id = ?",
            (actual, node_id),
        )
        self._set_meta("total_myco_composted", str(self.total_myco_composted + actual))
        self._record_event(node_id, "myco_compost", actual, reason)
        self.conn.commit()
        return actual

    burn_spore = compost_myco  # backward compat

    # -------------------------------------------------------------------
    # $HYPHA operations
    # -------------------------------------------------------------------

    def extend_hypha(self, node_id: str, amount: float, reason: str = "") -> bool:
        """Extend (mint) $HYPHA hyphae to a cultivator."""
        if amount <= 0:
            return False
        self._ensure_cultivator(node_id)
        self.conn.execute(
            "UPDATE hypha_balance SET balance = balance + ? WHERE node_id = ?",
            (amount, node_id),
        )
        self.conn.execute(
            "INSERT INTO fruiting_body (node_id, amount, grown_at) VALUES (?, ?, ?)",
            (node_id, amount, time.time()),
        )
        self._record_event(node_id, "hypha_extend", amount, reason)
        self.conn.commit()
        return True

    mint_xspore = extend_hypha  # backward compat

    def wither_hypha(self, node_id: str, amount: float, reason: str = "") -> float:
        """Wither (burn) $HYPHA from a cultivator (blight). Returns actual withered."""
        if amount <= 0:
            return 0.0
        self._ensure_cultivator(node_id)
        balance = self.hypha_balance(node_id)
        actual = min(amount, balance)
        if actual <= 0:
            return 0.0
        self.conn.execute(
            "UPDATE hypha_balance SET balance = balance - ? WHERE node_id = ?",
            (actual, node_id),
        )
        self._record_event(node_id, "hypha_wither", actual, reason)
        self.conn.commit()
        return actual

    burn_xspore = wither_hypha  # backward compat

    # -------------------------------------------------------------------
    # Inoculation (staking)
    # -------------------------------------------------------------------

    def inoculate(self, node_id: str, amount: float) -> bool:
        """Inoculate (stake) $MYCO into the substrate."""
        if amount <= 0:
            return False
        self._ensure_cultivator(node_id)
        balance = self.myco_balance(node_id)
        if balance < amount:
            return False
        self.conn.execute(
            "UPDATE myco_balance SET balance = balance - ? WHERE node_id = ?",
            (amount, node_id),
        )
        self.conn.execute(
            "UPDATE inoculation SET amount = amount + ? WHERE node_id = ?",
            (amount, node_id),
        )
        self._record_event(node_id, "inoculate", amount, "")
        self.conn.commit()
        return True

    add_stake = inoculate  # backward compat

    def extract(self, node_id: str, amount: float) -> bool:
        """Extract (unstake) $MYCO from the substrate."""
        if amount <= 0:
            return False
        self._ensure_cultivator(node_id)
        current = self.inoculation_amount(node_id)
        if current < amount:
            return False
        self.conn.execute(
            "UPDATE inoculation SET amount = amount - ? WHERE node_id = ?",
            (amount, node_id),
        )
        self.conn.execute(
            "UPDATE myco_balance SET balance = balance + ? WHERE node_id = ?",
            (amount, node_id),
        )
        self._record_event(node_id, "extract", amount, "")
        self.conn.commit()
        return True

    remove_stake = extract  # backward compat

    def blight(self, node_id: str, amount: float, reason: str = "") -> float:
        """Blight (slash) inoculated $MYCO — composted, not returned."""
        if amount <= 0:
            return 0.0
        self._ensure_cultivator(node_id)
        current = self.inoculation_amount(node_id)
        actual = min(amount, current)
        if actual <= 0:
            return 0.0
        self.conn.execute(
            "UPDATE inoculation SET amount = amount - ? WHERE node_id = ?",
            (actual, node_id),
        )
        self._set_meta("total_myco_composted", str(self.total_myco_composted + actual))
        self._record_event(node_id, "blight", actual, reason)
        self.conn.commit()
        return actual

    slash_stake = blight  # backward compat

    def has_sufficient_inoculation(self, node_id: str, required: float) -> bool:
        return self.inoculation_amount(node_id) >= required

    has_sufficient_stake = has_sufficient_inoculation  # backward compat

    # -------------------------------------------------------------------
    # Harvesting (claiming / fruiting cycle)
    # -------------------------------------------------------------------

    def harvest(self, node_id: str) -> HarvestResult | None:
        """Harvest matured fruiting bodies: $HYPHA → $MYCO.

        Conversion rate depends on fruiting age (patience rewards).
        Harvest fees decompose back into the substrate for other cultivators.
        Returns None if nothing to harvest.
        """
        self._ensure_cultivator(node_id)
        rows = self.conn.execute(
            "SELECT id, amount, grown_at FROM fruiting_body "
            "WHERE node_id = ? AND harvested = 0",
            (node_id,),
        ).fetchall()

        if not rows:
            return None

        now = time.time()
        total_hypha = 0.0
        total_myco = 0.0
        total_decomposed = 0.0

        for row in rows:
            age_days = (now - row["grown_at"]) / 86400
            rate, fee_pct = self._fruiting_rate(age_days)
            amount = row["amount"]
            myco_out = amount * rate
            decomposed = amount * fee_pct

            total_hypha += amount
            total_myco += myco_out
            total_decomposed += decomposed

            self.conn.execute(
                "UPDATE fruiting_body SET harvested = 1 WHERE id = ?",
                (row["id"],),
            )

        # Consume hyphae
        self.conn.execute(
            "UPDATE hypha_balance SET balance = balance - ? WHERE node_id = ?",
            (total_hypha, node_id),
        )

        # Grow $MYCO
        if total_myco > 0:
            self._grow_myco_internal(node_id, total_myco)

        # Decompose fees back into substrate for other cultivators
        nutrient_recycled = 0.0
        if total_decomposed > 0:
            nutrient_recycled = self._decompose(node_id, total_decomposed)

        self._record_event(node_id, "harvest", total_myco, f"decomposed={total_decomposed:.2f}")
        self.conn.commit()

        return HarvestResult(
            hypha_consumed=total_hypha,
            myco_yielded=total_myco,
            decomposed=total_decomposed,
            nutrient_recycled=nutrient_recycled,
        )

    claim_rewards = harvest  # backward compat

    def estimate_harvest(self, node_id: str) -> tuple[float, float, float]:
        """Estimate harvestable $MYCO without actually harvesting.

        Returns (myco_yield, decomposition_fee, hypha_consumed).
        """
        rows = self.conn.execute(
            "SELECT amount, grown_at FROM fruiting_body "
            "WHERE node_id = ? AND harvested = 0",
            (node_id,),
        ).fetchall()

        now = time.time()
        total_myco = 0.0
        total_fee = 0.0
        total_hypha = 0.0

        for row in rows:
            age_days = (now - row["grown_at"]) / 86400
            rate, fee_pct = self._fruiting_rate(age_days)
            amount = row["amount"]
            total_myco += amount * rate
            total_fee += amount * fee_pct
            total_hypha += amount

        return total_myco, total_fee, total_hypha

    estimate_claim = estimate_harvest  # backward compat

    @staticmethod
    def _fruiting_rate(age_days: float) -> tuple[float, float]:
        """Return (conversion_rate, decomposition_rate) based on fruiting age."""
        for min_days, rate, fee in reversed(cfg.FRUITING_TIERS):
            if age_days >= min_days:
                return rate / 100.0, fee / 100.0
        return 0.50, 0.50

    _maturation_rate = _fruiting_rate  # backward compat

    def _grow_myco_internal(self, node_id: str, amount: float):
        """Internal growth without event recording (used by harvest)."""
        current_minted = self.total_myco_minted
        if current_minted + amount > cfg.MYCO_MAX_SUPPLY:
            amount = cfg.MYCO_MAX_SUPPLY - current_minted
        if amount <= 0:
            return
        self.conn.execute(
            "UPDATE myco_balance SET balance = balance + ? WHERE node_id = ?",
            (amount, node_id),
        )
        self._set_meta("total_myco_minted", str(current_minted + amount))

    def _decompose(self, harvester_id: str, fee_amount: float) -> float:
        """Decompose harvest fees back into substrate for other cultivators.

        Nature's recycling: what one organism discards feeds the network.
        """
        rows = self.conn.execute(
            "SELECT node_id, SUM(amount) as total "
            "FROM fruiting_body WHERE harvested = 0 AND node_id != ? "
            "GROUP BY node_id HAVING total > 0",
            (harvester_id,),
        ).fetchall()
        if not rows:
            return 0.0
        total_unharvested = sum(r["total"] for r in rows)
        distributed = 0.0
        for row in rows:
            share = (row["total"] / total_unharvested) * fee_amount
            self.conn.execute(
                "INSERT INTO fruiting_body (node_id, amount, grown_at) VALUES (?, ?, ?)",
                (row["node_id"], share, time.time()),
            )
            self.conn.execute(
                "UPDATE hypha_balance SET balance = balance + ? WHERE node_id = ?",
                (share, row["node_id"]),
            )
            distributed += share
        return distributed

    # -------------------------------------------------------------------
    # Reward actions (called by the FungalRewardEngine)
    # -------------------------------------------------------------------

    def reward_verified_keep(self, node_id: str, is_frontier: bool = False):
        """Reward a cultivator for a verified 'keep' — healthy fruiting body."""
        amount = cfg.REWARD_VERIFIED_CANOPY if is_frontier else cfg.REWARD_VERIFIED_KEEP
        reason = "canopy_specimen" if is_frontier else "healthy_fruiting"

        # During First Flush, also grow $MYCO directly
        if self.in_first_flush:
            self.grow_myco(node_id, amount, f"first_flush_{reason}")
            flush = self.flush_count + 1
            self._set_meta("flush_count", str(flush))
            self.conn.commit()

        self.extend_hypha(node_id, amount, reason)

    def reward_verification_performed(self, node_id: str):
        """Reward a mycologist for performing a spore print (verification)."""
        self.extend_hypha(node_id, cfg.REWARD_SPORE_PRINT, "spore_print")

    def reward_successful_challenge(self, node_id: str):
        """Reward for catching contamination (exposing fraudulent claim)."""
        self.extend_hypha(node_id, cfg.REWARD_CONTAMINATION_CATCH, "contamination_catch")

    def reward_winning_verifier(self, node_id: str):
        """Reward a mycologist on the correct side of a dispute."""
        self.extend_hypha(node_id, cfg.REWARD_WINNING_MYCOLOGIST, "winning_mycologist")

    def penalize_wrong_dispute_side(self, node_id: str):
        """Bad identification — wrong side of a dispute."""
        self.wither_hypha(node_id, cfg.PENALTY_BAD_IDENTIFICATION, "bad_identification")
        self.blight(node_id, cfg.BLIGHT_BAD_ID, "bad_identification")

    def penalize_rejected_experiment(self, node_id: str):
        """Toxic fruiting — published claim rejected by dispute."""
        self.wither_hypha(node_id, cfg.PENALTY_TOXIC_FRUITING, "toxic_fruiting")
        self.blight(node_id, cfg.BLIGHT_TOXIC_FRUITING, "toxic_fruiting")

    # -------------------------------------------------------------------
    # Queries
    # -------------------------------------------------------------------

    def leaderboard(self, limit: int = 20) -> list[dict]:
        """Return top cultivators by $HYPHA balance (canopy view)."""
        rows = self.conn.execute(
            "SELECT h.node_id, h.balance as hypha, "
            "COALESCE(m.balance, 0) as myco, "
            "COALESCE(i.amount, 0) as inoculated "
            "FROM hypha_balance h "
            "LEFT JOIN myco_balance m ON h.node_id = m.node_id "
            "LEFT JOIN inoculation i ON h.node_id = i.node_id "
            "ORDER BY h.balance DESC LIMIT ?",
            (limit,),
        ).fetchall()
        # Return with backward-compat keys too
        results = []
        for r in rows:
            d = dict(r)
            d["xspore"] = d["hypha"]
            d["spore"] = d["myco"]
            d["staked"] = d["inoculated"]
            results.append(d)
        return results

    def node_summary(self, node_id: str) -> dict:
        """Return full fungal summary for a cultivator."""
        self._ensure_cultivator(node_id)
        myco_out, fee, hypha_used = self.estimate_harvest(node_id)
        return {
            "node_id": node_id,
            "myco_balance": self.myco_balance(node_id),
            "hypha_balance": self.hypha_balance(node_id),
            "inoculated": self.inoculation_amount(node_id),
            "fruiting_bodies": self.conn.execute(
                "SELECT COUNT(*) as c FROM fruiting_body WHERE node_id = ? AND harvested = 0",
                (node_id,),
            ).fetchone()["c"],
            "harvestable_myco": myco_out,
            "decomposition_fee": fee,
            # backward compat
            "spore_balance": self.myco_balance(node_id),
            "xspore_balance": self.hypha_balance(node_id),
            "staked": self.inoculation_amount(node_id),
            "pending_rewards": self.conn.execute(
                "SELECT COUNT(*) as c FROM fruiting_body WHERE node_id = ? AND harvested = 0",
                (node_id,),
            ).fetchone()["c"],
            "claimable_spore": myco_out,
            "claim_fee": fee,
        }

    def event_history(self, node_id: str, limit: int = 50) -> list[dict]:
        """Return recent mycelium events for a cultivator."""
        rows = self.conn.execute(
            "SELECT * FROM mycelium_event WHERE node_id = ? ORDER BY timestamp DESC LIMIT ?",
            (node_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def global_stats(self) -> dict:
        """Return global substrate statistics."""
        return {
            "total_myco_minted": self.total_myco_minted,
            "total_myco_composted": self.total_myco_composted,
            "circulating_myco": self.total_myco_minted - self.total_myco_composted,
            "max_supply": cfg.MYCO_MAX_SUPPLY,
            "flush_count": self.flush_count,
            "in_first_flush": self.in_first_flush,
            # backward compat
            "total_spore_minted": self.total_myco_minted,
            "total_spore_burned": self.total_myco_composted,
            "circulating_spore": self.total_myco_minted - self.total_myco_composted,
            "genesis_experiments": self.flush_count,
            "in_genesis_epoch": self.in_first_flush,
        }

    # -------------------------------------------------------------------
    # Internal
    # -------------------------------------------------------------------

    def _record_event(self, node_id: str, kind: str, amount: float, detail: str):
        event_id = f"{kind}:{node_id}:{time.time()}"
        self.conn.execute(
            "INSERT OR IGNORE INTO mycelium_event "
            "(event_id, node_id, kind, amount, detail, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (event_id, node_id, kind, amount, detail, time.time()),
        )


# Backward-compatible alias
TokenManager = MyceliumLedger
