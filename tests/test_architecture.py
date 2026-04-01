"""Tests for architecture diagram parsing and rendering."""
from __future__ import annotations

from termaid import render
from termaid.parser.architecture import parse_architecture, _compute_grid_positions


class TestArchitectureParser:
    def test_groups_and_services(self):
        g = parse_architecture(
            'architecture-beta\n'
            '    group api(cloud)[API]\n'
            '    service db(database)[Database] in api\n'
            '    service srv(server)[Server] in api\n'
        )
        assert g.subgraphs[0].label == "API"
        assert len(g.subgraphs[0].node_ids) == 2
        assert "Database" in g.nodes["db"].label
        assert "Server" in g.nodes["srv"].label

    def test_edges_with_directions(self):
        g = parse_architecture(
            'architecture-beta\n'
            '    service a(server)[A]\n'
            '    service b(server)[B]\n'
            '    a:R --> L:b\n'
        )
        assert g.edges[0].source == "a"
        assert g.edges[0].target == "b"
        assert g.edges[0].has_arrow_end is True

    def test_nested_groups(self):
        g = parse_architecture(
            'architecture-beta\n'
            '    group outer(cloud)[Outer]\n'
            '    group inner(cloud)[Inner] in outer\n'
            '    service s1(server)[S1] in inner\n'
        )
        assert g.subgraphs[0].label == "Outer"
        assert g.subgraphs[0].children[0].label == "Inner"


class TestGridPositions:
    def test_lr_chain(self):
        pos = _compute_grid_positions(
            ["a", "b", "c"],
            [("a", "R", "b", "L"), ("b", "R", "c", "L")],
        )
        assert pos["a"][0] < pos["b"][0] < pos["c"][0]

    def test_tb_placement(self):
        pos = _compute_grid_positions(
            ["a", "b"],
            [("a", "B", "b", "T")],
        )
        assert pos["b"][1] > pos["a"][1]

    def test_cross_layout(self):
        pos = _compute_grid_positions(
            ["center", "left", "right", "top", "bottom"],
            [
                ("left", "R", "center", "L"),
                ("center", "R", "right", "L"),
                ("top", "B", "center", "T"),
                ("bottom", "T", "center", "B"),
            ],
        )
        assert pos["left"][0] < pos["center"][0] < pos["right"][0]
        assert pos["top"][1] < pos["center"][1] < pos["bottom"][1]


class TestArchitectureRendering:
    def test_render_with_group(self):
        output = render(
            'architecture-beta\n'
            '    group cloud(cloud)[Cloud Infra]\n'
            '    service web(server)[Web App] in cloud\n'
            '    service db(database)[Data Store] in cloud\n'
            '    web:R --> L:db\n'
        )
        assert "Cloud Infra" in output
        assert "Web App" in output
        assert "Data Store" in output
        assert "┌" in output  # box drawing
        assert "►" in output  # arrow
