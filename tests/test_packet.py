"""Tests for packet diagram parsing and rendering."""
from __future__ import annotations

from termaid import render
from termaid.parser.packet import parse_packet


class TestPacketParser:
    def test_fields_and_ranges(self):
        d = parse_packet(
            'packet-beta\n'
            '    0-15: "Source Port"\n'
            '    16-31: "Dest Port"\n'
            '    32-63: "Sequence Number"\n'
        )
        assert len(d.fields) == 3
        assert d.fields[0].label == "Source Port"
        assert d.fields[0].start == 0
        assert d.fields[0].end == 15
        assert d.fields[1].start == 16
        assert d.fields[2].end == 63

    def test_single_bit_field(self):
        d = parse_packet(
            'packet-beta\n'
            '    0-15: "Port"\n'
            '    16: "Flag"\n'
        )
        assert d.fields[1].start == 16
        assert d.fields[1].end == 16


class TestPacketRendering:
    def test_render_udp(self):
        output = render(
            'packet-beta\n'
            '    0-15: "Source Port"\n'
            '    16-31: "Destination Port"\n'
            '    32-47: "Length"\n'
            '    48-63: "Checksum"\n'
        )
        assert "Source Port" in output
        assert "Destination Port" in output
        assert "Length" in output
        assert "Checksum" in output
        assert "╭" in output  # rounded box

    def test_field_wider_than_a_row_keeps_continuation_rows(self):
        output = render('packet-beta\n    0-63: "Payload"\n')
        assert "Payload" in output
        assert "32" in output
        assert "63" in output
        assert sum(line.count("╭") for line in output.split("\n")) == 2


class TestPacketWideChars:
    def test_cjk_label_does_not_overflow_borders(self):
        from termaid.utils import display_width
        output = render(
            'packet-beta\n'
            '  0-3: "源端口字段名称很长"\n'
            '  4-15: "Rest"'
        )
        lines = output.split("\n")
        border_w = max(display_width(l) for l in lines if "╭" in l or "┌" in l)
        assert all(display_width(l) <= border_w for l in lines)
        # The truncated label must not destroy the field borders: the
        # content row keeps its left border, field separator, and right border
        content_row = next(l for l in lines if "Rest" in l)
        assert content_row.count("│") >= 3


TCP_FLAGS = (
    "packet-beta\n"
    '0-9: "Reserved"\n10: "URG"\n11: "ACK"\n12: "PSH"\n13: "RST"\n14: "SYN"\n15: "FIN"\n'
    '16-31: "Window"\n'
)


class TestPacketNarrowFields:
    def test_one_bit_fields_can_be_told_apart(self):
        out = render(TCP_FLAGS)
        box_row = next(line for line in out.splitlines() if "Reserved" in line)
        keys = [cell.strip() for cell in box_row.split("│")[2:8]]
        assert len(set(keys)) == 6 and all(keys)
        for key, name, bit in zip(keys, ("URG", "ACK", "PSH", "RST", "SYN", "FIN"), range(10, 16)):
            assert f"{key} = {name} [{bit}]" in out

    def test_one_bit_fields_show_their_bit_numbers(self):
        numbers = render(TCP_FLAGS).splitlines()[0].split()
        assert numbers == ["0", "9", "10", "11", "12", "13", "14", "15", "16", "31"]

    def test_the_last_row_ends_at_its_last_field(self):
        out = render('packet-beta\n0-15: "Source Port"\n16-31: "Destination Port"\n32: "A"\n33: "B"\n')
        last_box = [line for line in out.splitlines() if "B" in line and "│" in line][-1]
        assert last_box.rstrip().endswith("│B │")


class TestPacketTitle:
    def test_title_keyword(self):
        out = render('packet-beta\n  title UDP Packet\n  0-15: "Source Port"\n')
        assert out.splitlines()[0].strip() == "UDP Packet"

    def test_frontmatter_title(self):
        out = render('---\ntitle: TCP Packet\n---\npacket-beta\n  0-15: "Source Port"\n')
        assert out.splitlines()[0].strip() == "TCP Packet"

    def test_labels_stay_inside_at_no_vertical_padding(self):
        out = render('packet-beta\n  0-15: "Source Port"\n', padding_y=0)
        assert any(line.startswith(" │") and "Source Port" in line for line in out.splitlines())
