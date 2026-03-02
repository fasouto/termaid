"""Parser for Mermaid gitGraph syntax.

Supports: gitGraph header with direction, commit, branch, checkout/switch,
merge, cherry-pick, tags, commit types, and %%{init}%% configuration.
"""
from __future__ import annotations

import json
import re

from ..model.gitgraph import Branch, Commit, GitGraph


def parse_git_graph(text: str) -> GitGraph:
    """Parse mermaid gitGraph text into a GitGraph model."""
    parser = _GitGraphParser(text)
    return parser.parse()


class _GitGraphParser:
    def __init__(self, text: str) -> None:
        self.text = text
        self.diagram = GitGraph()
        self.current_branch = "main"
        self.branch_heads: dict[str, str] = {}
        self.auto_id = 0
        self._commit_map: dict[str, Commit] = {}
        self._branch_set: set[str] = set()
        self._seq = 0

    def parse(self) -> GitGraph:
        lines = self._preprocess(self.text)
        if not lines:
            return self.diagram

        # Handle %%{init}%% directives before the header
        remaining: list[str] = []
        for line in lines:
            if line.startswith("%%{init"):
                self._parse_init(line)
            else:
                remaining.append(line)

        if not remaining:
            return self.diagram

        # Parse header
        header = remaining[0]
        if header.startswith("gitGraph"):
            rest = header[len("gitGraph"):].strip()
            # Check for direction: "gitGraph TB:" or "gitGraph LR:"
            dir_match = re.match(r"(LR|TB|BT)\s*:?", rest, re.IGNORECASE)
            if dir_match:
                self.diagram.direction = dir_match.group(1).upper()
            remaining = remaining[1:]

        # Update current_branch from config
        self.current_branch = self.diagram.main_branch_name

        # Ensure main branch exists
        self._ensure_branch(self.current_branch)

        for line in remaining:
            self._parse_line(line)

        return self.diagram

    def _preprocess(self, text: str) -> list[str]:
        """Split into lines, strip inline comments and blank lines."""
        result: list[str] = []
        for line in text.split("\n"):
            stripped = line.strip()
            # Skip pure comment lines (but keep %%{init} directives)
            if stripped.startswith("%%") and not stripped.startswith("%%{"):
                continue
            if stripped:
                result.append(stripped)
        return result

    def _parse_init(self, line: str) -> None:
        """Extract config from %%{init: {...}}%% directive."""
        m = re.search(r"%%\{init:\s*(\{.*\})\s*\}%%", line)
        if not m:
            return
        try:
            config = json.loads(m.group(1))
        except json.JSONDecodeError:
            # Try with single quotes replaced
            try:
                fixed = m.group(1).replace("'", '"')
                config = json.loads(fixed)
            except json.JSONDecodeError:
                return
        git_config = config.get("gitGraph", config)
        if "mainBranchName" in git_config:
            self.diagram.main_branch_name = git_config["mainBranchName"]
        if "mainBranchOrder" in git_config:
            # Will be applied when we create the main branch
            pass

    def _parse_line(self, line: str) -> None:
        # commit
        if line.startswith("commit"):
            self._parse_commit(line)
            return

        # branch
        if line.startswith("branch "):
            self._parse_branch(line)
            return

        # checkout / switch
        if line.startswith("checkout ") or line.startswith("switch "):
            parts = line.split(None, 1)
            if len(parts) >= 2:
                branch_name = parts[1].strip().strip('"')
                if branch_name in self._branch_set:
                    self.current_branch = branch_name
            return

        # merge
        if line.startswith("merge "):
            self._parse_merge(line)
            return

        # cherry-pick
        if line.startswith("cherry-pick"):
            self._parse_cherry_pick(line)
            return

    def _parse_commit(self, line: str) -> None:
        """Parse a commit line with optional id, type, tag attributes."""
        commit_id = None
        commit_type = "NORMAL"
        tag = ""

        # Extract id: "..."
        id_match = re.search(r'id:\s*"([^"]*)"', line)
        if id_match:
            commit_id = id_match.group(1)

        # Extract type: NORMAL|REVERSE|HIGHLIGHT
        type_match = re.search(r'type:\s*(NORMAL|REVERSE|HIGHLIGHT)', line)
        if type_match:
            commit_type = type_match.group(1)

        # Extract tag: "..."
        tag_match = re.search(r'tag:\s*"([^"]*)"', line)
        if tag_match:
            tag = tag_match.group(1)

        if commit_id is None:
            commit_id = str(self.auto_id)
            self.auto_id += 1

        parents = []
        if self.current_branch in self.branch_heads:
            parents.append(self.branch_heads[self.current_branch])

        commit = Commit(
            id=commit_id,
            branch=self.current_branch,
            type=commit_type,
            tag=tag,
            parents=parents,
            seq=self._seq,
        )
        self._seq += 1
        self.diagram.commits.append(commit)
        self._commit_map[commit_id] = commit
        self.branch_heads[self.current_branch] = commit_id

    def _parse_branch(self, line: str) -> None:
        """Parse a branch line: branch <name> [order: N]."""
        m = re.match(r'branch\s+"?([^"]+?)"?\s*(?:order:\s*(\d+))?\s*$', line)
        if not m:
            return
        name = m.group(1).strip()
        order = int(m.group(2)) if m.group(2) else -1

        start_commit = self.branch_heads.get(self.current_branch, "")
        self._ensure_branch(name, order=order, start_commit=start_commit)

        # Copy head from current branch so the new branch forks from here
        if self.current_branch in self.branch_heads:
            self.branch_heads[name] = self.branch_heads[self.current_branch]

        self.current_branch = name

    def _parse_merge(self, line: str) -> None:
        """Parse a merge line: merge <branch> [id: "..."] [type: ...] [tag: "..."]."""
        m = re.match(r'merge\s+"?([^"]+?)"?(?:\s|$)', line)
        if not m:
            return
        merged_branch = m.group(1).strip()

        commit_id = None
        commit_type = "NORMAL"
        tag = ""

        id_match = re.search(r'id:\s*"([^"]*)"', line)
        if id_match:
            commit_id = id_match.group(1)

        type_match = re.search(r'type:\s*(NORMAL|REVERSE|HIGHLIGHT)', line)
        if type_match:
            commit_type = type_match.group(1)

        tag_match = re.search(r'tag:\s*"([^"]*)"', line)
        if tag_match:
            tag = tag_match.group(1)

        if commit_id is None:
            commit_id = str(self.auto_id)
            self.auto_id += 1

        parents = []
        if self.current_branch in self.branch_heads:
            parents.append(self.branch_heads[self.current_branch])
        if merged_branch in self.branch_heads:
            parents.append(self.branch_heads[merged_branch])

        commit = Commit(
            id=commit_id,
            branch=self.current_branch,
            type=commit_type,
            tag=tag,
            parents=parents,
            seq=self._seq,
        )
        self._seq += 1
        self.diagram.commits.append(commit)
        self._commit_map[commit_id] = commit
        self.branch_heads[self.current_branch] = commit_id

    def _parse_cherry_pick(self, line: str) -> None:
        """Parse a cherry-pick line: cherry-pick id: "<id>"."""
        m = re.search(r'id:\s*"([^"]*)"', line)
        if not m:
            return
        source_id = m.group(1)

        if source_id not in self._commit_map:
            return

        commit_id = f"{source_id}-cherry"
        # Avoid duplicate IDs
        while commit_id in self._commit_map:
            commit_id += "-cp"

        tag = ""
        tag_match = re.search(r'tag:\s*"([^"]*)"', line)
        if tag_match:
            tag = tag_match.group(1)

        parents = []
        if self.current_branch in self.branch_heads:
            parents.append(self.branch_heads[self.current_branch])
        parents.append(source_id)

        commit = Commit(
            id=commit_id,
            branch=self.current_branch,
            type="NORMAL",
            tag=tag,
            parents=parents,
            seq=self._seq,
        )
        self._seq += 1
        self.diagram.commits.append(commit)
        self._commit_map[commit_id] = commit
        self.branch_heads[self.current_branch] = commit_id

    def _ensure_branch(
        self, name: str, order: int = -1, start_commit: str = ""
    ) -> None:
        """Add a branch if it doesn't exist yet."""
        if name not in self._branch_set:
            self._branch_set.add(name)
            self.diagram.branches.append(
                Branch(name=name, order=order, start_commit=start_commit)
            )
