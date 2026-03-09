"""Wrapper — bridges autoresearch's experiment loop with Spore's record system.

Monitors autoresearch's results.tsv and git history to produce ExperimentRecord
objects after each experiment completes.
"""

from __future__ import annotations

import csv
import hashlib
import re
import subprocess
from pathlib import Path

from .record import ExperimentRecord, Status


def parse_results_tsv(tsv_path: str | Path) -> list[dict]:
    """Parse autoresearch's results.tsv into a list of dicts."""
    path = Path(tsv_path)
    if not path.exists():
        return []

    rows = []
    with open(path) as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            rows.append(row)
    return rows


def get_git_diff(repo_path: str | Path, commit: str) -> str:
    """Get the diff for a specific commit."""
    try:
        result = subprocess.run(
            ["git", "diff", f"{commit}~1", commit, "--", "train.py"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
        )
        return result.stdout
    except Exception:
        return ""


def get_train_code(repo_path: str | Path, commit: str) -> str:
    """Get the train.py contents at a specific commit."""
    try:
        result = subprocess.run(
            ["git", "show", f"{commit}:train.py"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
        )
        return result.stdout
    except Exception:
        return ""


def get_commit_message(repo_path: str | Path, commit: str) -> str:
    """Get the commit message for a specific commit."""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%B", commit],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def detect_gpu() -> str:
    """Detect GPU model via nvidia-smi."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
        )
        return result.stdout.strip().split("\n")[0].replace(" ", "_")
    except Exception:
        return "unknown"


def detect_cuda_version() -> str:
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


def detect_torch_version() -> str:
    try:
        result = subprocess.run(
            ["python", "-c", "import torch; print(torch.__version__)"],
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


def parse_run_log(log_path: str | Path) -> dict:
    """Extract val_bpb and training stats from a run.log file."""
    path = Path(log_path)
    if not path.exists():
        return {}

    content = path.read_text()
    result = {}

    # Extract val_bpb
    bpb_match = re.search(r"val_bpb:\s*([\d.]+)", content)
    if bpb_match:
        result["val_bpb"] = float(bpb_match.group(1))

    # Extract peak VRAM
    vram_match = re.search(r"peak_vram_mb:\s*([\d.]+)", content)
    if vram_match:
        result["peak_vram_mb"] = float(vram_match.group(1))

    # Extract steps
    step_match = re.findall(r"step\s+(\d+)", content)
    if step_match:
        result["num_steps"] = int(step_match[-1])

    # Extract params
    param_match = re.search(r"num_parameters:\s*([\d,]+)", content)
    if param_match:
        result["num_params"] = int(param_match.group(1).replace(",", ""))

    return result


def tsv_row_to_record(
    row: dict,
    repo_path: str | Path,
    parent_cid: str | None,
    parent_depth: int,
    dataset_cid: str,
    prepare_cid: str,
    node_id: str,
    gpu_model: str | None = None,
    cuda_version: str | None = None,
    torch_version: str | None = None,
) -> ExperimentRecord:
    """Convert a results.tsv row + git info into an ExperimentRecord."""
    repo_path = Path(repo_path)
    commit = row.get("commit", "")

    # Get the code and diff
    code = get_train_code(repo_path, commit)
    code_cid = hashlib.sha256(code.encode()).hexdigest() if code else ""
    diff = get_git_diff(repo_path, commit)
    description = row.get("description", get_commit_message(repo_path, commit))

    # Parse status
    status_str = row.get("status", "crash").strip().lower()
    try:
        status = Status(status_str)
    except ValueError:
        status = Status.CRASH

    val_bpb = float(row.get("val_bpb", 0))
    memory_gb = float(row.get("memory_gb", 0))

    return ExperimentRecord(
        parent=parent_cid,
        depth=parent_depth + 1,
        code_cid=code_cid,
        diff=diff,
        dataset_cid=dataset_cid,
        prepare_cid=prepare_cid,
        time_budget=300,
        val_bpb=val_bpb,
        peak_vram_mb=memory_gb * 1024,
        num_steps=0,  # Not in results.tsv; could parse from log
        num_params=0,  # Not in results.tsv; could parse from log
        status=status,
        description=description,
        hypothesis="",  # Not captured by autoresearch
        agent_model="unknown",  # Could be configured
        gpu_model=gpu_model or detect_gpu(),
        cuda_version=cuda_version or detect_cuda_version(),
        torch_version=torch_version or detect_torch_version(),
        node_id=node_id,
    )


def import_results_tsv(
    tsv_path: str | Path,
    repo_path: str | Path,
    dataset_cid: str,
    prepare_cid: str,
    node_id: str,
) -> list[ExperimentRecord]:
    """Import an entire results.tsv into a list of ExperimentRecords.

    Reconstructs the parent chain: each 'keep' becomes the parent of
    the next experiment. 'discard' and 'crash' branch from the last 'keep'.
    """
    rows = parse_results_tsv(tsv_path)
    records = []
    last_keep_cid: str | None = None
    last_keep_depth = -1

    gpu = detect_gpu()
    cuda = detect_cuda_version()
    torch_ver = detect_torch_version()

    for row in rows:
        record = tsv_row_to_record(
            row,
            repo_path,
            parent_cid=last_keep_cid,
            parent_depth=last_keep_depth,
            dataset_cid=dataset_cid,
            prepare_cid=prepare_cid,
            node_id=node_id,
            gpu_model=gpu,
            cuda_version=cuda,
            torch_version=torch_ver,
        )
        # Compute a temporary CID for chaining (will be replaced when signed)
        record.id = record.compute_cid()
        records.append(record)

        if record.status == Status.KEEP:
            last_keep_cid = record.id
            last_keep_depth = record.depth

    return records
