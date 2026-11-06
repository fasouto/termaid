"""Data model for packet diagrams."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PacketField:
    start: int
    end: int  # inclusive
    label: str

    @property
    def bits(self) -> int:
        return self.end - self.start + 1


@dataclass
class Packet:
    fields: list[PacketField] = field(default_factory=list)
    row_bits: int = 32  # bits per row (standard network packet)
    warnings: list[str] = field(default_factory=list)
