"""Track assignment for relationship lines that jog sideways between layers.

Class and ER diagrams route a cross-layer relationship as a Z: down from the
source, sideways along one row inside the gap between the layers, then down
into the target. When several relationships share a gap their sideways runs
land on the same row and overwrite each other. This module hands each run
its own row (a track) so the gap can be sized to fit them all.
"""
from __future__ import annotations


def assign_tracks(intervals: dict[int, tuple[int, int]]) -> dict[int, int]:
    """Colour column intervals so overlapping ones get different tracks.

    ``intervals`` maps a key to the inclusive (left, right) columns of a run.
    Returns {key: track_index}; tracks are numbered from 0 and runs on the
    same track are at least one blank column apart so their corners do not
    touch. Greedy in left-to-right order, which is optimal for intervals.
    """
    tracks: list[int] = []  # rightmost column used on each track
    result: dict[int, int] = {}
    for key, (left, right) in sorted(intervals.items(), key=lambda kv: (kv[1][0], kv[1][1])):
        for index, last_right in enumerate(tracks):
            if last_right + 2 <= left:
                tracks[index] = right
                result[key] = index
                break
        else:
            tracks.append(right)
            result[key] = len(tracks) - 1
    return result
