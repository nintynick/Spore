"""Shared test fixtures for Spore tests."""

from __future__ import annotations

import pytest

from spore.graph import ResearchGraph
from spore.record import ExperimentRecord, Status, generate_keypair
from spore.store import ArtifactStore
from spore.verify import ReputationStore


@pytest.fixture
def keypair():
    """Generate a fresh Ed25519 keypair."""
    sk, node_id = generate_keypair()
    return sk, node_id


@pytest.fixture
def second_keypair():
    """Generate a second keypair for multi-node tests."""
    sk, node_id = generate_keypair()
    return sk, node_id


@pytest.fixture
def graph():
    """In-memory research graph."""
    g = ResearchGraph(":memory:")
    yield g
    g.close()


@pytest.fixture
def reputation():
    """In-memory reputation store."""
    r = ReputationStore(":memory:")
    yield r
    r.close()


@pytest.fixture
def store(tmp_path):
    """Temporary artifact store."""
    return ArtifactStore(tmp_path / "artifact")


def make_record(
    keypair,
    parent=None,
    depth=0,
    val_bpb=1.0,
    status=Status.KEEP,
    description="test experiment",
    diff="",
    gpu_model="RTX_4090",
    hypothesis="test hypothesis",
) -> ExperimentRecord:
    """Helper to create and sign a test ExperimentRecord."""
    sk, node_id = keypair
    record = ExperimentRecord(
        parent=parent,
        depth=depth,
        code_cid="a" * 64,
        diff=diff,
        dataset_cid="dataset_v1",
        prepare_cid="prepare_v1",
        time_budget=300,
        val_bpb=val_bpb,
        peak_vram_mb=24000,
        num_steps=500,
        num_params=124_000_000,
        status=status,
        description=description,
        hypothesis=hypothesis,
        agent_model="test-agent",
        gpu_model=gpu_model,
        cuda_version="12.4",
        torch_version="2.5.1",
        node_id=node_id,
    )
    record.sign(sk)
    return record
