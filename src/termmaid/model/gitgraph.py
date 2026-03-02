"""Data model for gitGraph diagrams."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Commit:
    id: str
    branch: str
    type: str = "NORMAL"  # "NORMAL", "REVERSE", "HIGHLIGHT"
    tag: str = ""
    parents: list[str] = field(default_factory=list)
    seq: int = 0


@dataclass
class Branch:
    name: str
    order: int = -1
    start_commit: str = ""


@dataclass
class GitGraph:
    commits: list[Commit] = field(default_factory=list)
    branches: list[Branch] = field(default_factory=list)
    direction: str = "LR"
    main_branch_name: str = "main"
