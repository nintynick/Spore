"""Tests for challenge coordinator edge cases."""

from __future__ import annotations

from test.conftest import make_record

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
