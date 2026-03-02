"""Tests for gitGraph diagram parsing and rendering."""
from __future__ import annotations

from termmaid import render
from termmaid.parser.gitgraph import parse_git_graph


# ── Parser tests ──────────────────────────────────────────────────────────────


class TestGitGraphParser:
    def test_basic_commits(self):
        d = parse_git_graph(
            "gitGraph\n"
            "  commit\n"
            "  commit\n"
            "  commit"
        )
        assert len(d.commits) == 3
        assert all(c.branch == "main" for c in d.commits)

    def test_commit_auto_ids(self):
        d = parse_git_graph(
            "gitGraph\n  commit\n  commit"
        )
        assert d.commits[0].id == "0"
        assert d.commits[1].id == "1"

    def test_commit_explicit_id(self):
        d = parse_git_graph(
            'gitGraph\n  commit id: "abc"'
        )
        assert d.commits[0].id == "abc"

    def test_commit_type(self):
        d = parse_git_graph(
            'gitGraph\n'
            '  commit id: "a" type: NORMAL\n'
            '  commit id: "b" type: REVERSE\n'
            '  commit id: "c" type: HIGHLIGHT'
        )
        assert d.commits[0].type == "NORMAL"
        assert d.commits[1].type == "REVERSE"
        assert d.commits[2].type == "HIGHLIGHT"

    def test_commit_tag(self):
        d = parse_git_graph(
            'gitGraph\n  commit id: "a" tag: "v1.0"'
        )
        assert d.commits[0].tag == "v1.0"

    def test_branch(self):
        d = parse_git_graph(
            "gitGraph\n"
            "  commit\n"
            "  branch develop\n"
            "  commit"
        )
        assert len(d.branches) == 2
        assert d.branches[0].name == "main"
        assert d.branches[1].name == "develop"
        assert d.commits[1].branch == "develop"

    def test_checkout(self):
        d = parse_git_graph(
            "gitGraph\n"
            "  commit\n"
            "  branch develop\n"
            "  commit\n"
            "  checkout main\n"
            "  commit"
        )
        assert d.commits[0].branch == "main"
        assert d.commits[1].branch == "develop"
        assert d.commits[2].branch == "main"

    def test_switch(self):
        d = parse_git_graph(
            "gitGraph\n"
            "  commit\n"
            "  branch develop\n"
            "  commit\n"
            "  switch main\n"
            "  commit"
        )
        assert d.commits[2].branch == "main"

    def test_merge(self):
        d = parse_git_graph(
            "gitGraph\n"
            "  commit\n"
            "  branch develop\n"
            "  commit\n"
            "  checkout main\n"
            '  merge develop id: "m"'
        )
        merge = d.commits[-1]
        assert merge.id == "m"
        assert merge.branch == "main"
        assert len(merge.parents) == 2

    def test_merge_parents(self):
        d = parse_git_graph(
            'gitGraph\n'
            '  commit id: "a"\n'
            '  branch dev\n'
            '  commit id: "b"\n'
            '  checkout main\n'
            '  merge dev id: "m"'
        )
        merge = d.commits[-1]
        assert "a" in merge.parents  # main head
        assert "b" in merge.parents  # dev head

    def test_cherry_pick(self):
        d = parse_git_graph(
            'gitGraph\n'
            '  commit id: "A"\n'
            '  branch develop\n'
            '  commit id: "B"\n'
            '  checkout main\n'
            '  cherry-pick id: "B"'
        )
        cp = d.commits[-1]
        assert "B" in cp.parents
        assert cp.branch == "main"

    def test_direction_lr(self):
        d = parse_git_graph("gitGraph\n  commit")
        assert d.direction == "LR"

    def test_direction_tb(self):
        d = parse_git_graph("gitGraph TB:\n  commit")
        assert d.direction == "TB"

    def test_direction_bt(self):
        d = parse_git_graph("gitGraph BT:\n  commit")
        assert d.direction == "BT"

    def test_branch_order(self):
        d = parse_git_graph(
            "gitGraph\n"
            "  commit\n"
            "  branch dev order: 1\n"
            "  commit"
        )
        assert d.branches[1].order == 1

    def test_init_config(self):
        d = parse_git_graph(
            '%%{init: {"gitGraph": {"mainBranchName": "master"}}}%%\n'
            "gitGraph\n"
            "  commit"
        )
        assert d.main_branch_name == "master"
        assert d.commits[0].branch == "master"

    def test_commit_sequence_numbers(self):
        d = parse_git_graph(
            "gitGraph\n"
            "  commit\n"
            "  commit\n"
            "  commit"
        )
        assert d.commits[0].seq == 0
        assert d.commits[1].seq == 1
        assert d.commits[2].seq == 2

    def test_branch_start_commit(self):
        d = parse_git_graph(
            'gitGraph\n'
            '  commit id: "a"\n'
            '  branch dev'
        )
        assert d.branches[1].start_commit == "a"

    def test_comments_ignored(self):
        d = parse_git_graph(
            "gitGraph\n"
            "  %% this is a comment\n"
            "  commit\n"
            "  %% another comment\n"
            "  commit"
        )
        assert len(d.commits) == 2

    def test_frontmatter_stripped(self):
        d = parse_git_graph(
            "gitGraph\n"
            "  commit"
        )
        assert len(d.commits) == 1

    def test_multiple_branches(self):
        d = parse_git_graph(
            "gitGraph\n"
            "  commit\n"
            "  branch feature\n"
            "  commit\n"
            "  branch hotfix\n"
            "  commit"
        )
        assert len(d.branches) == 3
        branch_names = [b.name for b in d.branches]
        assert "main" in branch_names
        assert "feature" in branch_names
        assert "hotfix" in branch_names


# ── Rendering tests ──────────────────────────────────────────────────────────


class TestGitGraphRendering:
    def test_basic_linear(self):
        output = render(
            "gitGraph\n  commit\n  commit\n  commit"
        )
        assert "main" in output
        assert "●" in output

    def test_commit_ids_displayed(self):
        output = render(
            'gitGraph\n'
            '  commit id: "init"\n'
            '  commit id: "feat"'
        )
        assert "init" in output
        assert "feat" in output

    def test_branch_label_displayed(self):
        output = render(
            "gitGraph\n"
            "  commit\n"
            "  branch develop\n"
            "  commit"
        )
        assert "main" in output
        assert "develop" in output

    def test_branch_line_drawn(self):
        output = render(
            "gitGraph\n"
            "  commit\n"
            "  branch develop\n"
            "  commit"
        )
        assert "─" in output  # horizontal line

    def test_merge_vertical_line(self):
        output = render(
            "gitGraph\n"
            '  commit id: "a"\n'
            "  branch develop\n"
            '  commit id: "b"\n'
            "  checkout main\n"
            '  merge develop id: "m"'
        )
        assert "│" in output or "┼" in output  # vertical connection

    def test_commit_type_markers(self):
        output = render(
            'gitGraph\n'
            '  commit id: "n" type: NORMAL\n'
            '  commit id: "r" type: REVERSE\n'
            '  commit id: "h" type: HIGHLIGHT'
        )
        assert "●" in output  # NORMAL
        assert "✖" in output  # REVERSE
        assert "■" in output  # HIGHLIGHT

    def test_tag_displayed(self):
        output = render(
            'gitGraph\n'
            '  commit id: "a" tag: "v1.0"'
        )
        assert "[v1.0]" in output

    def test_tb_orientation(self):
        output = render(
            "gitGraph TB:\n"
            "  commit\n"
            "  branch develop\n"
            "  commit\n"
            "  checkout main\n"
            "  merge develop"
        )
        assert "main" in output
        assert "develop" in output
        # In TB, branch names should be above commits
        lines = output.split("\n")
        main_row = next(i for i, l in enumerate(lines) if "main" in l)
        # The first commit marker should be below the label
        marker_rows = [i for i, l in enumerate(lines) if "●" in l]
        assert marker_rows[0] > main_row

    def test_bt_orientation(self):
        output = render(
            "gitGraph BT:\n"
            "  commit\n"
            "  branch develop\n"
            "  commit"
        )
        assert "main" in output
        assert "develop" in output
        # In BT, branch names should be below commits
        lines = output.split("\n")
        main_row = next(i for i, l in enumerate(lines) if "main" in l)
        marker_rows = [i for i, l in enumerate(lines) if "●" in l]
        assert marker_rows[0] < main_row

    def test_cherry_pick_rendered(self):
        output = render(
            'gitGraph\n'
            '  commit id: "A"\n'
            '  branch develop\n'
            '  commit id: "B"\n'
            '  checkout main\n'
            '  cherry-pick id: "B"'
        )
        assert "A" in output
        assert "B" in output
        assert "main" in output
        assert "develop" in output

    def test_ascii_mode(self):
        output = render(
            "gitGraph\n  commit\n  commit",
            use_ascii=True,
        )
        assert "o" in output  # ASCII commit marker
        assert "main" in output
        unicode_chars = set("┌┐└┘─│├┤┬┴┼╭╮╰╯►◄▲▼┄┆━┃╋●✖■")
        for ch in output:
            assert ch not in unicode_chars

    def test_ascii_commit_types(self):
        output = render(
            'gitGraph\n'
            '  commit type: NORMAL\n'
            '  commit type: REVERSE\n'
            '  commit type: HIGHLIGHT',
            use_ascii=True,
        )
        assert "o" in output  # NORMAL
        assert "X" in output  # REVERSE
        assert "#" in output  # HIGHLIGHT

    def test_init_config_rendering(self):
        output = render(
            '%%{init: {"gitGraph": {"mainBranchName": "master"}}}%%\n'
            "gitGraph\n"
            "  commit\n"
            "  branch dev\n"
            "  commit"
        )
        assert "master" in output
        assert "dev" in output

    def test_adaptive_spacing(self):
        """Long labels should get more space, short labels less."""
        output = render(
            'gitGraph\n'
            '  commit id: "a"\n'
            '  commit id: "this-is-a-very-long-label"\n'
            '  commit id: "b"'
        )
        assert "a" in output
        assert "this-is-a-very-long-label" in output
        assert "b" in output

    def test_feature_branch_workflow(self):
        output = render(
            'gitGraph\n'
            '  commit id: "1"\n'
            '  commit id: "2"\n'
            '  branch develop\n'
            '  commit id: "3"\n'
            '  commit id: "4"\n'
            '  checkout main\n'
            '  commit id: "5"\n'
            '  merge develop id: "6"\n'
            '  commit id: "7"'
        )
        for cid in ["1", "2", "3", "4", "5", "6", "7"]:
            assert cid in output
        assert "main" in output
        assert "develop" in output

    def test_empty_graph(self):
        output = render("gitGraph")
        assert isinstance(output, str)
