"""A* pathfinder on the grid coordinate system.

Uses Manhattan distance with +1 corner penalty as heuristic.
4-directional movement only (no diagonals).
Previously-routed edges are soft obstacles (cost +2). A crossing cell holds
an unrelated edge's straight line: a path may only pass it perpendicularly.
"""
from __future__ import annotations

import heapq
from typing import Callable


class _AStarNode(float):
    """Search node; the float value gives heap order by f_cost only."""

    __slots__ = ("f_cost", "g_cost", "cell", "parent", "heading")

    def __new__(
        cls,
        f_cost: float,
        g_cost: float,
        cell: tuple[int, int],
        parent: _AStarNode | None = None,
        heading: tuple[int, int] | None = None,
    ) -> _AStarNode:
        node = float.__new__(cls, f_cost)
        node.f_cost = f_cost
        node.g_cost = g_cost
        node.cell = cell
        node.parent = parent
        # Direction of the step from parent into this node
        node.heading = heading
        return node


# 4-directional movement
DIRS = [(0, -1), (0, 1), (-1, 0), (1, 0)]  # up, down, left, right


def heuristic(c1: int, r1: int, c2: int, r2: int) -> float:
    """Manhattan distance with +1 corner penalty when not axis-aligned."""
    dx = abs(c1 - c2)
    dy = abs(r1 - r2)
    if dx == 0 or dy == 0:
        return float(dx + dy)
    return float(dx + dy + 1)  # corner penalty


def find_path(
    start_col: int,
    start_row: int,
    end_col: int,
    end_row: int,
    is_free: Callable[[int, int], bool],
    soft_obstacles: set[tuple[int, int]] | None = None,
    max_iterations: int = 5000,
    penalty: Callable[[int, int], float] | None = None,
    crossings: dict[tuple[int, int], bool] | None = None,
) -> list[tuple[int, int]] | None:
    """Find a path from start to end using A*.

    Args:
        start_col, start_row: Start grid coordinates
        end_col, end_row: End grid coordinates
        is_free: Function that returns True if a cell is not occupied by a node
        soft_obstacles: Set of cells occupied by previously-routed edges (cost +2)
        max_iterations: Maximum iterations before giving up
        penalty: Extra cost of stepping onto a cell, on top of soft obstacles
        crossings: Cells a path may only cross straight through, mapped to
            True when the line already there runs horizontally

    Returns:
        List of (col, row) waypoints, or None if no path found
    """
    if start_col == end_col and start_row == end_row:
        return [(start_col, start_row)]

    soft = soft_obstacles or set()
    cross = crossings or {}

    start_node = _AStarNode(
        f_cost=heuristic(start_col, start_row, end_col, end_row),
        g_cost=0,
        cell=(start_col, start_row),
    )

    open_set: list[_AStarNode] = [start_node]
    # A crossing cell is a separate state per heading, since a path that
    # enters it cannot turn there.
    closed: set[tuple[int, ...]] = set()
    best_g: dict[tuple[int, ...], float] = {(start_col, start_row): 0}

    heappush = heapq.heappush
    heappop = heapq.heappop
    closed_add = closed.add
    best_g_get = best_g.get

    iterations = 0
    while open_set and iterations < max_iterations:
        iterations += 1
        current = heappop(open_set)
        cell = current.cell
        col, row = cell

        if col == end_col and row == end_row:
            return _reconstruct(current)

        heading = current.heading
        in_crossing = cell in cross
        key: tuple[int, ...] = cell
        if in_crossing and heading is not None:
            key += heading
        if key in closed:
            continue
        closed_add(key)
        current_g = current.g_cost

        directions = (heading,) if in_crossing and heading is not None else DIRS
        for direction in directions:
            dc, dr = direction
            nc, nr = col + dc, row + dr
            nkey = (nc, nr)
            state: tuple[int, ...] = nkey
            cross_horizontal = cross.get(nkey)
            if cross_horizontal is not None:
                if (dc == 0) != cross_horizontal:
                    continue
                state += direction

            if state in closed:
                continue

            # Allow start and end even if "occupied"
            is_endpoint = (nc == end_col and nr == end_row)
            if not is_endpoint and not is_free(nc, nr):
                continue

            # Base cost + soft obstacle penalty
            step_cost = 1.0
            if nkey in soft:
                step_cost += 2.0
            if penalty is not None:
                step_cost += penalty(nc, nr)

            # Corner penalty: if direction changes from parent's direction
            if heading is not None and direction != heading:
                step_cost += 0.5  # slight corner penalty in g-cost too

            new_g = current_g + step_cost

            prev_g = best_g_get(state)
            if prev_g is not None and prev_g <= new_g:
                continue
            best_g[state] = new_g

            h = heuristic(nc, nr, end_col, end_row)
            neighbor = _AStarNode(
                new_g + h,
                new_g,
                nkey,
                current,
                direction,
            )
            heappush(open_set, neighbor)

    return None  # No path found


def _reconstruct(node: _AStarNode) -> list[tuple[int, int]]:
    """Reconstruct path from end node to start."""
    path: list[tuple[int, int]] = []
    current: _AStarNode | None = node
    while current is not None:
        path.append(current.cell)
        current = current.parent
    path.reverse()
    return path


def simplify_path(path: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Remove collinear intermediate points, keeping only corners."""
    if len(path) <= 2:
        return path

    result = [path[0]]
    for i in range(1, len(path) - 1):
        prev = path[i - 1]
        curr = path[i]
        nxt = path[i + 1]
        # Keep if direction changes
        d1 = (curr[0] - prev[0], curr[1] - prev[1])
        d2 = (nxt[0] - curr[0], nxt[1] - curr[1])
        if d1 != d2:
            result.append(curr)
    result.append(path[-1])
    return result
