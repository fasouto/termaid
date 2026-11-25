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


def _connected(g, start: str) -> set[str]:
    seen, todo = {start}, [start]
    while todo:
        n = todo.pop()
        for e in g.edges:
            for a, b in ((e.source, e.target), (e.target, e.source)):
                if a == n and b not in seen:
                    seen.add(b)
                    todo.append(b)
    return seen


class TestJunctions:
    """A junction joins every edge that meets it, keeping each edge's arrowheads."""

    T_SHAPE = (
        "architecture-beta\n"
        "    service a(server)[A]\n    service b(server)[B]\n    service c(server)[C]\n"
        "    junction j\n"
        "    a:R -- L:j\n    j:R -- L:b\n    j:B -- T:c\n"
    )

    def test_every_branch_is_kept(self):
        g = parse_architecture(self.T_SHAPE)
        assert _connected(g, "a") == {"a", "b", "c"}

    def test_plain_links_get_no_arrowheads(self):
        g = parse_architecture(self.T_SHAPE)
        assert not any(e.has_arrow_start or e.has_arrow_end for e in g.edges)
        assert "►" not in render(self.T_SHAPE) and "◄" not in render(self.T_SHAPE)

    def test_an_arrow_into_a_junction_reaches_the_service(self):
        g = parse_architecture(self.T_SHAPE.replace("j:R -- L:b", "j:R --> L:b"))
        (edge,) = [e for e in g.edges if "b" in (e.source, e.target)]
        assert (edge.has_arrow_end if edge.target == "b" else edge.has_arrow_start) is True


class TestEdgeSides:
    def test_the_written_order_does_not_change_the_route(self):
        head = "architecture-beta\n    service db(database)[Database]\n    service server(server)[Server]\n"
        assert render(head + "    db:L -- R:server\n") == render(head + "    server:R -- L:db\n")
        assert render(head + "    db:T --> B:server\n") == render(head + "    server:B <-- T:db\n")

    def test_ascii_output_has_no_icons(self):
        out = render(
            "architecture-beta\n    service db(database)[Database]\n    service s(server)[Server]\n    s:R -- L:db\n",
            use_ascii=True,
        )
        assert out.isascii()
        assert "Database" in out and "Server" in out


def test_br_tags_break_or_join_lines():
    out = render('architecture-beta\n  group api(cloud)[API<br/>tier]\n  service db(database)[Main<br/>db] in api\n  service s(server)[Web<br>app] in api\n  s:R -- L:db\n')
    assert "<br" not in out.lower()
    for words in ['API tier', 'Main', 'db', 'Web', 'app']:
        assert words in out, words
