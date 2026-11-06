"""Theme system for colored diagram output."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    """Maps semantic style keys to Rich style strings."""
    name: str
    node: str
    edge: str
    arrow: str
    subgraph: str
    label: str
    edge_label: str
    subgraph_label: str
    default: str = ""
    # Solid-background themes fill regions with bg colors
    is_solid: bool = False
    bg_default: str = ""     # overall background
    bg_node: str = ""        # node box fill
    bg_subgraph: str = ""    # subgraph region fill
    # Per-section region colors (kanban columns, quadrant regions, timeline sections).
    # First 4 must be visually distinct for quadrant charts: blue, red, green, amber.
    section_colors: tuple[str, ...] = (
        "#14385C", "#5C1424", "#145C28", "#5C4814",
        "#3C145C", "#145C50", "#5C2814", "#28145C",
    )


THEMES: dict[str, Theme] = {
    "default": Theme(
        name="default",
        node="cyan",
        edge="dim white",
        arrow="bold yellow",
        subgraph="dim cyan",
        label="bold white",
        edge_label="italic dim",
        subgraph_label="bold cyan",
        section_colors=("#14385C", "#5C1424", "#145C28", "#5C4814", "#3C145C", "#145C50", "#5C2814", "#28145C"),
    ),
    "terra": Theme(
        name="terra",
        node="bold #D4845A",
        edge="#8B7E6A",
        arrow="bold #E8A87C",
        subgraph="#A07858",
        label="#F5E6D3",
        edge_label="italic #B89A7A",
        subgraph_label="bold #E8A87C",
        section_colors=("#502010", "#104820", "#504008", "#0E2850", "#401038", "#084840", "#503008", "#201050"),
    ),
    "neon": Theme(
        name="neon",
        node="bold magenta",
        edge="dim cyan",
        arrow="bold green",
        subgraph="dim magenta",
        label="bold white",
        edge_label="italic cyan",
        subgraph_label="bold cyan",
        section_colors=("#0A1050", "#500A18", "#0A500A", "#50400A", "#400A50", "#0A5040", "#502A0A", "#1A0A50"),
    ),
    "mono": Theme(
        name="mono",
        node="bold white",
        edge="dim",
        arrow="bold white",
        subgraph="dim",
        label="white",
        edge_label="italic dim",
        subgraph_label="bold white",
        section_colors=("#1A1A1A", "#303030", "#242424", "#383838", "#202020", "#343434", "#282828", "#2C2C2C"),
    ),
    "amber": Theme(
        name="amber",
        node="bold #FFB000",
        edge="#806000",
        arrow="bold #FFD080",
        subgraph="#906800",
        label="#FFD580",
        edge_label="italic #B08030",
        subgraph_label="bold #FFC040",
        section_colors=("#50300A", "#0A2850", "#285008", "#500A28", "#280A50", "#0A5038", "#502008", "#0A1050"),
    ),
    "phosphor": Theme(
        name="phosphor",
        node="bold #33FF33",
        edge="#1A8C1A",
        arrow="bold #66FF66",
        subgraph="#228B22",
        label="#AAFFAA",
        edge_label="italic #339933",
        subgraph_label="bold #55DD55",
        section_colors=("#083008", "#0A4808", "#081850", "#484808", "#081850", "#084830", "#480808", "#180850"),
    ),
    "gruvbox": Theme(
        name="gruvbox",
        node="#FABD2F",
        edge="#8EC07C",
        arrow="bold #FE8019",
        subgraph="#B8BB26",
        label="bold #EBDBB2",
        edge_label="italic #D5C4A1",
        subgraph_label="bold #D5C4A1",
        is_solid=True,
        bg_default="on #282828",
        bg_node="on #3C3836",
        bg_subgraph="on #32302F",
        section_colors=("#502010", "#085020", "#504008", "#082850", "#48082A", "#085048", "#502808", "#180850"),
    ),
    "monokai": Theme(
        name="monokai",
        node="#F92672",
        edge="#66D9EF",
        arrow="bold #A6E22E",
        subgraph="#AE81FF",
        label="bold #F8F8F2",
        edge_label="italic #E6DB74",
        subgraph_label="bold #AE81FF",
        is_solid=True,
        bg_default="on #272822",
        bg_node="on #3E3D32",
        bg_subgraph="on #333328",
        section_colors=("#50102A", "#085040", "#405008", "#380850", "#085038", "#502A08", "#081850", "#501010"),
    ),
    "dracula": Theme(
        name="dracula",
        node="#BD93F9",
        edge="#6272A4",
        arrow="bold #50FA7B",
        subgraph="#FF79C6",
        label="bold #F8F8F2",
        edge_label="italic #8BE9FD",
        subgraph_label="bold #FF79C6",
        is_solid=True,
        bg_default="on #282A36",
        bg_node="on #44475A",
        bg_subgraph="on #383A4A",
        section_colors=("#2A1040", "#0E4028", "#40380A", "#102A40", "#3C0A24", "#0A403A", "#402010", "#1A1040"),
    ),
    "nord": Theme(
        name="nord",
        node="#88C0D0",
        edge="#4C566A",
        arrow="bold #A3BE8C",
        subgraph="#81A1C1",
        label="bold #ECEFF4",
        edge_label="italic #B48EAD",
        subgraph_label="bold #81A1C1",
        is_solid=True,
        bg_default="on #2E3440",
        bg_node="on #3B4252",
        bg_subgraph="on #343C4A",
        section_colors=("#143858", "#0A5830", "#501848", "#584810", "#48100A", "#581020", "#2A5010", "#381058"),
    ),
    "solarized": Theme(
        name="solarized",
        node="#268BD2",
        edge="#586E75",
        arrow="bold #B58900",
        subgraph="#2AA198",
        label="bold #FDF6E3",
        edge_label="italic #CB4B16",
        subgraph_label="bold #2AA198",
        is_solid=True,
        bg_default="on #002B36",
        bg_node="on #073642",
        bg_subgraph="on #053440",
        section_colors=("#0A3048", "#0A4820", "#380A38", "#483808", "#08403A", "#480A20", "#2A4008", "#100A48"),
    ),
}


def get_theme(name: str) -> Theme:
    """Get a theme by name, falling back to default."""
    return THEMES.get(name, THEMES["default"])
