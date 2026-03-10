"""Tests for the Spore token manager (local SQLite mode)."""

from __future__ import annotations

import time

import pytest

from spore.token import TokenManager, ClaimResult
from spore import token_config as cfg


@pytest.fixture
def tm():
    """In-memory token manager."""
    t = TokenManager(":memory:")
    yield t
    t.close()


class TestSporeBalance:
    def test_initial_balance_zero(self, tm):
        assert tm.spore_balance("node_a") == 0.0

    def test_mint_spore(self, tm):
        assert tm.mint_spore("node_a", 100)
        assert tm.spore_balance("node_a") == 100.0

    def test_mint_respects_max_supply(self, tm):
        tm.mint_spore("node_a", cfg.SPORE_MAX_SUPPLY)
        assert not tm.mint_spore("node_a", 1.0)

    def test_burn_spore(self, tm):
        tm.mint_spore("node_a", 100)
        burned = tm.burn_spore("node_a", 30)
        assert burned == 30.0
        assert tm.spore_balance("node_a") == 70.0

    def test_burn_more_than_balance(self, tm):
        tm.mint_spore("node_a", 50)
        burned = tm.burn_spore("node_a", 100)
        assert burned == 50.0
        assert tm.spore_balance("node_a") == 0.0


class TestXSporeBalance:
    def test_initial_xspore_zero(self, tm):
        assert tm.xspore_balance("node_a") == 0.0

    def test_mint_xspore(self, tm):
        assert tm.mint_xspore("node_a", 100, "test_reward")
        assert tm.xspore_balance("node_a") == 100.0

    def test_burn_xspore(self, tm):
        tm.mint_xspore("node_a", 100)
        burned = tm.burn_xspore("node_a", 30, "penalty")
        assert burned == 30.0
        assert tm.xspore_balance("node_a") == 70.0


class TestStaking:
    def test_stake_and_unstake(self, tm):
        tm.mint_spore("node_a", 1000)
        assert tm.add_stake("node_a", 200)
        assert tm.stake_amount("node_a") == 200.0
        assert tm.spore_balance("node_a") == 800.0

        assert tm.remove_stake("node_a", 100)
        assert tm.stake_amount("node_a") == 100.0
        assert tm.spore_balance("node_a") == 900.0

    def test_stake_insufficient_balance(self, tm):
        tm.mint_spore("node_a", 50)
        assert not tm.add_stake("node_a", 100)

    def test_unstake_insufficient(self, tm):
        tm.mint_spore("node_a", 100)
        tm.add_stake("node_a", 50)
        assert not tm.remove_stake("node_a", 100)

    def test_slash_stake(self, tm):
        tm.mint_spore("node_a", 1000)
        tm.add_stake("node_a", 500)
        slashed = tm.slash_stake("node_a", 200, "bad_dispute")
        assert slashed == 200.0
        assert tm.stake_amount("node_a") == 300.0
        # Slashed tokens are burned
        assert tm.total_spore_burned == 200.0

    def test_slash_more_than_staked(self, tm):
        tm.mint_spore("node_a", 100)
        tm.add_stake("node_a", 50)
        slashed = tm.slash_stake("node_a", 200, "big_penalty")
        assert slashed == 50.0
        assert tm.stake_amount("node_a") == 0.0

    def test_has_sufficient_stake(self, tm):
        tm.mint_spore("node_a", 1000)
        tm.add_stake("node_a", 150)
        assert tm.has_sufficient_stake("node_a", 100)
        assert not tm.has_sufficient_stake("node_a", 200)


class TestMaturation:
    def test_immediate_claim_50pct_fee(self, tm):
        tm.mint_xspore("node_a", 100.0, "test")
        result = tm.claim_rewards("node_a")
        assert result is not None
        assert result.xspore_burned == 100.0
        assert result.spore_minted == pytest.approx(50.0, abs=0.01)
        assert result.fee_paid == pytest.approx(50.0, abs=0.01)

    def test_maturation_rate_tiers(self, tm):
        # _maturation_rate returns (conversion_rate, fee_rate) as decimals
        assert tm._maturation_rate(0) == (0.50, 0.50)    # immediate: 50% conversion, 50% fee
        assert tm._maturation_rate(3) == (0.50, 0.50)    # still tier 0
        assert tm._maturation_rate(7) == (0.75, 0.25)    # tier 1
        assert tm._maturation_rate(10) == (0.75, 0.25)   # still tier 1
        assert tm._maturation_rate(14) == (0.90, 0.10)   # tier 2
        assert tm._maturation_rate(20) == (0.90, 0.10)   # still tier 2
        assert tm._maturation_rate(30) == (1.00, 0.00)   # tier 3
        assert tm._maturation_rate(100) == (1.00, 0.00)  # still tier 3

    def test_nothing_to_claim(self, tm):
        assert tm.claim_rewards("node_a") is None

    def test_estimate_claim(self, tm):
        tm.mint_xspore("node_a", 100.0, "test")
        spore_out, fee, xburned = tm.estimate_claim("node_a")
        assert spore_out == pytest.approx(50.0, abs=0.01)
        assert fee == pytest.approx(50.0, abs=0.01)
        assert xburned == 100.0

    def test_claim_fee_redistribution(self, tm):
        # Two nodes with pending rewards
        tm.mint_xspore("node_a", 100.0, "test")
        tm.mint_xspore("node_b", 100.0, "test")

        # node_a claims immediately — 50% fee should go to node_b
        result = tm.claim_rewards("node_a")
        assert result is not None
        assert result.fee_paid == pytest.approx(50.0, abs=0.01)
        assert result.fee_redistributed == pytest.approx(50.0, abs=0.01)

        # node_b should now have more xspore from redistribution
        assert tm.xspore_balance("node_b") > 100.0


class TestRewardActions:
    def test_reward_verified_keep(self, tm):
        tm.reward_verified_keep("node_a", is_frontier=False)
        assert tm.xspore_balance("node_a") == cfg.REWARD_VERIFIED_KEEP

    def test_reward_verified_frontier(self, tm):
        tm.reward_verified_keep("node_a", is_frontier=True)
        assert tm.xspore_balance("node_a") == cfg.REWARD_VERIFIED_FRONTIER

    def test_reward_verification_performed(self, tm):
        tm.reward_verification_performed("node_a")
        assert tm.xspore_balance("node_a") == cfg.REWARD_VERIFICATION_PERFORMED

    def test_reward_successful_challenge(self, tm):
        tm.reward_successful_challenge("node_a")
        assert tm.xspore_balance("node_a") == cfg.REWARD_SUCCESSFUL_CHALLENGE

    def test_reward_winning_verifier(self, tm):
        tm.reward_winning_verifier("node_a")
        assert tm.xspore_balance("node_a") == cfg.REWARD_WINNING_VERIFIER

    def test_penalize_wrong_dispute_side(self, tm):
        # Give the node something to lose
        tm.mint_xspore("node_a", 200, "setup")
        tm.mint_spore("node_a", 1000)
        tm.add_stake("node_a", 500)

        tm.penalize_wrong_dispute_side("node_a")
        assert tm.xspore_balance("node_a") == 200 - cfg.PENALTY_WRONG_DISPUTE_SIDE
        assert tm.stake_amount("node_a") == 500 - cfg.SLASH_WRONG_DISPUTE

    def test_penalize_rejected_experiment(self, tm):
        tm.mint_xspore("node_a", 500, "setup")
        tm.mint_spore("node_a", 2000)
        tm.add_stake("node_a", 1000)

        tm.penalize_rejected_experiment("node_a")
        assert tm.xspore_balance("node_a") == 500 - cfg.PENALTY_REJECTED_EXPERIMENT
        assert tm.stake_amount("node_a") == 1000 - cfg.SLASH_REJECTED_EXPERIMENT


class TestGenesisEpoch:
    def test_genesis_mints_spore_directly(self, tm):
        assert tm.in_genesis_epoch
        tm.reward_verified_keep("node_a")
        # Should have both $xSPORE and $SPORE during genesis
        assert tm.xspore_balance("node_a") == cfg.REWARD_VERIFIED_KEEP
        assert tm.spore_balance("node_a") == cfg.REWARD_VERIFIED_KEEP

    def test_genesis_epoch_ends(self, tm):
        for i in range(cfg.GENESIS_EPOCH_EXPERIMENTS):
            tm.reward_verified_keep(f"node_{i}")
        assert not tm.in_genesis_epoch


class TestQueries:
    def test_leaderboard(self, tm):
        tm.mint_xspore("node_a", 300, "test")
        tm.mint_xspore("node_b", 100, "test")
        tm.mint_xspore("node_c", 200, "test")

        board = tm.leaderboard(limit=2)
        assert len(board) == 2
        assert board[0]["node_id"] == "node_a"
        assert board[1]["node_id"] == "node_c"

    def test_node_summary(self, tm):
        tm.mint_spore("node_a", 500)
        tm.mint_xspore("node_a", 200, "test")
        tm.add_stake("node_a", 100)

        summary = tm.node_summary("node_a")
        assert summary["spore_balance"] == 400.0
        assert summary["xspore_balance"] == 200.0
        assert summary["staked"] == 100.0

    def test_global_stats(self, tm):
        tm.mint_spore("node_a", 1000)
        tm.burn_spore("node_a", 200)

        stats = tm.global_stats()
        assert stats["total_spore_minted"] == 1000.0
        assert stats["total_spore_burned"] == 200.0
        assert stats["circulating_spore"] == 800.0
        assert stats["max_supply"] == cfg.SPORE_MAX_SUPPLY

    def test_event_history(self, tm):
        tm.mint_spore("node_a", 100, "test_reason")
        history = tm.event_history("node_a")
        assert len(history) >= 1
        assert history[0]["kind"] == "spore_mint"
