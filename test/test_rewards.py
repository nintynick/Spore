"""Tests for the reward engine bridge between reputation and tokens."""

from __future__ import annotations

import pytest

from spore import token_config as cfg
from spore.rewards import RewardEngine
from spore.token import TokenManager


@pytest.fixture
def tm():
    t = TokenManager(":memory:")
    yield t
    t.close()


@pytest.fixture
def engine(tm):
    return RewardEngine(tm)


class TestPublishGating:
    def test_genesis_epoch_allows_no_stake(self, engine, tm):
        assert tm.in_genesis_epoch
        assert engine.on_publish("node_a") is True

    def test_post_genesis_requires_stake(self, engine, tm):
        # Exhaust genesis epoch
        for i in range(cfg.GENESIS_EPOCH_EXPERIMENTS):
            tm.reward_verified_keep(f"node_{i}")
        assert not tm.in_genesis_epoch

        # No stake → cannot publish
        assert engine.on_publish("node_a") is False

        # With stake → can publish
        tm.mint_spore("node_a", 1000)
        tm.add_stake("node_a", cfg.STAKE_PUBLISH)
        assert engine.on_publish("node_a") is True


class TestVerificationRewards:
    def test_record_verified(self, engine, tm):
        engine.on_record_verified("node_a", is_frontier=False)
        assert tm.xspore_balance("node_a") == cfg.REWARD_VERIFIED_KEEP

    def test_frontier_bonus(self, engine, tm):
        engine.on_record_verified("node_a", is_frontier=True)
        assert tm.xspore_balance("node_a") == cfg.REWARD_VERIFIED_FRONTIER

    def test_verification_performed(self, engine, tm):
        engine.on_verification_performed("verifier_1")
        assert tm.xspore_balance("verifier_1") == cfg.REWARD_VERIFICATION_PERFORMED


class TestDisputeRewards:
    def test_successful_challenge(self, engine, tm):
        engine.on_successful_challenge("challenger_1")
        assert tm.xspore_balance("challenger_1") == cfg.REWARD_SUCCESSFUL_CHALLENGE

    def test_winning_verifier(self, engine, tm):
        engine.on_winning_verifier("verifier_1")
        assert tm.xspore_balance("verifier_1") == cfg.REWARD_WINNING_VERIFIER

    def test_wrong_dispute_side_penalty(self, engine, tm):
        # Setup: give node something to lose
        tm.mint_xspore("bad_node", 200, "setup")
        tm.mint_spore("bad_node", 1000)
        tm.add_stake("bad_node", 500)

        engine.on_wrong_dispute_side("bad_node")
        assert tm.xspore_balance("bad_node") == 200 - cfg.PENALTY_WRONG_DISPUTE_SIDE
        assert tm.stake_amount("bad_node") == 500 - cfg.SLASH_WRONG_DISPUTE

    def test_rejected_experiment_heavy_penalty(self, engine, tm):
        tm.mint_xspore("publisher", 500, "setup")
        tm.mint_spore("publisher", 2000)
        tm.add_stake("publisher", 1000)

        engine.on_rejected_experiment("publisher")
        assert tm.xspore_balance("publisher") == 500 - cfg.PENALTY_REJECTED_EXPERIMENT
        assert tm.stake_amount("publisher") == 1000 - cfg.SLASH_REJECTED_EXPERIMENT


class TestChallengeGating:
    def test_genesis_allows_no_stake(self, engine, tm):
        assert engine.on_challenge_issued("node_a") is True

    def test_post_genesis_requires_stake(self, engine, tm):
        for i in range(cfg.GENESIS_EPOCH_EXPERIMENTS):
            tm.reward_verified_keep(f"node_{i}")

        assert engine.on_challenge_issued("node_a") is False

        tm.mint_spore("node_a", 1000)
        tm.add_stake("node_a", cfg.STAKE_CHALLENGE)
        assert engine.on_challenge_issued("node_a") is True
