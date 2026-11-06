"""Parser for Mermaid packet diagrams.

Syntax:
    packet-beta
        0-15: "Source Port"
        16-31: "Destination Port"
        32-63: "Sequence Number"

    Or with +N auto-increment:
        +16: "Source Port"
        +16: "Destination Port"
        +32: "Sequence Number"
"""
from __future__ import annotations

import re

from ..model.packet import Packet, PacketField


def parse_packet(text: str) -> Packet:
    """Parse a mermaid packet diagram definition."""
    lines = text.strip().splitlines()
    packet = Packet()

    if not lines:
        return packet

    next_bit = 0

    for line in lines[1:]:  # skip "packet-beta" header
        comment_idx = line.find("%%")
        if comment_idx >= 0:
            line = line[:comment_idx]

        stripped = line.strip()
        if not stripped:
            continue

        # Try: start-end: "label" or start-end: label
        m = re.match(r'^(\d+)\s*-\s*(\d+)\s*:\s*"?([^"]*)"?', stripped)
        if m:
            start = int(m.group(1))
            end = int(m.group(2))
            label = m.group(3).strip()
            packet.fields.append(PacketField(start=start, end=end, label=label))
            next_bit = end + 1
            continue

        # Try: +N: "label" (auto-increment)
        m = re.match(r'^\+(\d+)\s*:\s*"?([^"]*)"?', stripped)
        if m:
            count = int(m.group(1))
            label = m.group(2).strip()
            start = next_bit
            end = start + count - 1
            packet.fields.append(PacketField(start=start, end=end, label=label))
            next_bit = end + 1
            continue

        # Try: start: "label" (single bit)
        m = re.match(r'^(\d+)\s*:\s*"?([^"]*)"?', stripped)
        if m:
            start = int(m.group(1))
            label = m.group(2).strip()
            packet.fields.append(PacketField(start=start, end=start, label=label))
            next_bit = start + 1
            continue

    return packet
