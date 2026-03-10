"""Batch-size helpers for resource scaling."""

from __future__ import annotations


def scale_device_batch_size(
    base_batch_size: int,
    resource_pct: int,
    total_batch_size: int,
    max_seq_len: int,
) -> int:
    """Scale batch size by resource percent and snap to a valid divisor."""
    requested = max(1, int(base_batch_size * resource_pct / 100))
    for batch_size in range(requested, 0, -1):
        if total_batch_size % (batch_size * max_seq_len) == 0:
            return batch_size
    return 1
