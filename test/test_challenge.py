"""Tests for challenge coordinator edge cases."""

from __future__ import annotations

from test.conftest import make_record

from spore.challenge_state import apply_dispute_event
from spore.node import NodeConfig, SporeNode
from spore.record import Status


def test_on_challenge_does_not_reward_challenger(tmp_path):
    node = SporeNode(NodeConfig(port=0, data_dir=str(tmp_path)))

    node.challenger.on_challenge(
        {
            "event_id": "challenge:test",
            "experiment_id": "exp",
            "challenger_id": "challenger_1",
            "challenger_gpu": "RTX_3060",
        }
    )

    assert node.reputation.get_score("challenger_1") == 0.0
    node.graph.close()
    node.reputation.close()


def test_crash_records_do_not_schedule_spot_checks(tmp_path, keypair, monkeypatch):
    node = SporeNode(NodeConfig(port=0, data_dir=str(tmp_path)))
    record = make_record(
        keypair, status=Status.CRASH, gpu_model=node.challenger.gpu_model
    )
    scheduled: list[object] = []

    monkeypatch.setattr(node.verifier, "should_verify", lambda _record: True)
    monkeypatch.setattr(
        "spore.challenge.asyncio.create_task", lambda coro: scheduled.append(coro)
    )

    node.challenger.on_experiment_received(record)

    assert scheduled == []
    node.graph.close()
    node.reputation.close()


def test_rejected_dispute_rewards_challenger_and_winning_verifier(tmp_path, keypair):
    node = SporeNode(NodeConfig(port=0, data_dir=str(tmp_path)))
    record = make_record(keypair, status=Status.KEEP)
    node.graph.insert(record)

    applied = apply_dispute_event(
        node,
        node.verifier,
        {
            "event_id": f"dispute:{record.id}:challenger_1",
            "experiment_id": record.id,
            "original_node_id": record.node_id,
            "challenger_id": "challenger_1",
            "outcome": "rejected",
            "winner_verifier_ids": ["verifier_right"],
            "loser_verifier_ids": ["verifier_wrong"],
        },
    )

    assert applied is True
    assert node.reputation.get_score("challenger_1") == 1.0
    assert node.reputation.get_score("verifier_right") == 0.5
    assert node.reputation.get_score("verifier_wrong") == -1.0
    assert node.reputation.get_score(record.node_id) == -5.0
    node.graph.close()
    node.reputation.close()


def test_upheld_dispute_verifies_record_and_penalizes_challenger(tmp_path, keypair):
    node = SporeNode(NodeConfig(port=0, data_dir=str(tmp_path)))
    record = make_record(keypair, status=Status.KEEP)
    node.graph.insert(record)

    applied = apply_dispute_event(
        node,
        node.verifier,
        {
            "event_id": f"dispute:{record.id}:challenger_1",
            "experiment_id": record.id,
            "original_node_id": record.node_id,
            "challenger_id": "challenger_1",
            "outcome": "upheld",
            "winner_verifier_ids": ["verifier_right"],
            "loser_verifier_ids": ["verifier_wrong"],
        },
    )

    assert applied is True
    assert node.graph.is_verified(record.id) is True
    assert node.reputation.get_score(record.node_id) == 2.0
    assert node.reputation.get_score("challenger_1") == -1.0
    assert node.reputation.get_score("verifier_right") == 0.5
    assert node.reputation.get_score("verifier_wrong") == -1.0
    node.graph.close()
    node.reputation.close()
