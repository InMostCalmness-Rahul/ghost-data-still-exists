"""Repository path resolution.

Paths are resolved relative to this file so the solution works from any
checkout location and on Windows/macOS/Linux (AGENTS.md section 8).
"""

from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    """Return the repository root (the directory containing `code/`)."""
    return Path(__file__).resolve().parents[2]


def dataset_dir() -> Path:
    return repo_root() / "dataset"


def evidence_dir() -> Path:
    return dataset_dir() / "evidence"
