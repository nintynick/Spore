"""Tests for resource-aware batch-size scaling."""

from spore.workspace.batching import scale_device_batch_size


def test_scale_device_batch_size_snaps_to_valid_divisor():
    batch_size = scale_device_batch_size(
        base_batch_size=16,
        resource_pct=70,
        total_batch_size=2**19,
        max_seq_len=2048,
    )
    assert batch_size == 8


def test_scale_device_batch_size_preserves_grad_accum_divisibility():
    batch_size = scale_device_batch_size(
        base_batch_size=128,
        resource_pct=37,
        total_batch_size=2**19,
        max_seq_len=2048,
    )
    assert batch_size > 0
    assert (2**19) % (batch_size * 2048) == 0
