"""2D character canvas for rendering diagrams.

Row-major indexing: canvas[row][col] holds a single character.
Supports direction-based junction merging when box-drawing characters overlap.
Each cell tracks which directions (UP/DOWN/LEFT/RIGHT) are connected,
and the correct junction character is derived from the combined directions.
"""
from __future__ import annotations

from .charset import CharSet, UNICODE


# Direction bitfield constants
UP = 1
DOWN = 2
LEFT = 4
RIGHT = 8

# Derive the correct box-drawing character from a direction bitfield.
# Always produces standard single-line characters for junctions.
_DIRECTION_TO_CHAR: dict[int, str] = {
    LEFT | RIGHT: "─",
    UP | DOWN: "│",
    RIGHT | DOWN: "┌",
    LEFT | DOWN: "┐",
    RIGHT | UP: "└",
    LEFT | UP: "┘",
    LEFT | RIGHT | DOWN: "┬",
    LEFT | RIGHT | UP: "┴",
    UP | DOWN | RIGHT: "├",
    UP | DOWN | LEFT: "┤",
    LEFT | RIGHT | UP | DOWN: "┼",
    # Single directions (endpoints)
    RIGHT: "─",
    LEFT: "─",
    UP: "│",
    DOWN: "│",
}

# Reverse mapping: infer direction bitfield from a box-drawing character.
# Used when callers place box chars without explicit direction info
# (e.g. node borders, subgraph borders, shape renderers).
_CHAR_TO_DIRECTIONS: dict[str, int] = {
    # Standard single-line
    "─": LEFT | RIGHT,
    "│": UP | DOWN,
    "┌": RIGHT | DOWN,
    "┐": LEFT | DOWN,
    "└": RIGHT | UP,
    "┘": LEFT | UP,
    "├": UP | DOWN | RIGHT,
    "┤": UP | DOWN | LEFT,
    "┬": LEFT | RIGHT | DOWN,
    "┴": LEFT | RIGHT | UP,
    "┼": LEFT | RIGHT | UP | DOWN,
    # Rounded corners (same directions as sharp equivalents)
    "╭": RIGHT | DOWN,
    "╮": LEFT | DOWN,
    "╰": RIGHT | UP,
    "╯": LEFT | UP,
    # Double-line
    "═": LEFT | RIGHT,
    "║": UP | DOWN,
    "╔": RIGHT | DOWN,
    "╗": LEFT | DOWN,
    "╚": RIGHT | UP,
    "╝": LEFT | UP,
    # Thick
    "━": LEFT | RIGHT,
    "┃": UP | DOWN,
    "╋": LEFT | RIGHT | UP | DOWN,
    # Dotted
    "┄": LEFT | RIGHT,
    "┆": UP | DOWN,
}


class Canvas:
    """2D character canvas with row-major indexing.

    Supports cell protection: cells marked as "node" won't be overwritten
    by edge lines. Protected cells only accept junction merges that add
    a new direction (e.g. ─ on a │ border -> ├), preserving node borders.

    Each cell tracks a direction bitfield so that overlapping box-drawing
    characters merge correctly. The final character is derived from the
    combined directions rather than from a pair-lookup table.
    """

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self._grid: list[list[str]] = [
            [" " for _ in range(width)] for _ in range(height)
        ]
        self._style_grid: list[list[str]] = [
            ["default" for _ in range(width)] for _ in range(height)
        ]
        self._protected: list[list[bool]] = [
            [False for _ in range(width)] for _ in range(height)
        ]
        self._directions: list[list[int]] = [
            [0 for _ in range(width)] for _ in range(height)
        ]

    def resize(self, new_width: int, new_height: int) -> None:
        """Expand the canvas to at least the given dimensions."""
        if new_width <= self.width and new_height <= self.height:
            return
        new_w = max(self.width, new_width)
        new_h = max(self.height, new_height)
        for r in range(self.height):
            self._grid[r].extend(" " for _ in range(new_w - self.width))
            self._style_grid[r].extend("default" for _ in range(new_w - self.width))
            self._protected[r].extend(False for _ in range(new_w - self.width))
            self._directions[r].extend(0 for _ in range(new_w - self.width))
        for _ in range(new_h - self.height):
            self._grid.append([" " for _ in range(new_w)])
            self._style_grid.append(["default" for _ in range(new_w)])
            self._protected.append([False for _ in range(new_w)])
            self._directions.append([0 for _ in range(new_w)])
        self.width = new_w
        self.height = new_h

    def get(self, row: int, col: int) -> str:
        if 0 <= row < self.height and 0 <= col < self.width:
            return self._grid[row][col]
        return " "

    def protect(self, row: int, col: int) -> None:
        """Mark a cell as protected (node border). Protected cells only
        accept junction merges, not plain overwrites from edge lines."""
        if 0 <= row < self.height and 0 <= col < self.width:
            self._protected[row][col] = True

    def is_protected(self, row: int, col: int) -> bool:
        if 0 <= row < self.height and 0 <= col < self.width:
            return self._protected[row][col]
        return False

    def put(self, row: int, col: int, ch: str, merge: bool = True, style: str = "") -> None:
        """Place a character on the canvas, optionally merging junctions.

        When merge is True and both the existing cell and the new character
        have directional information (from box-drawing characters), their
        direction bits are OR'd together and the correct junction character
        is derived from the combined bitfield.

        Protected cells (node borders) only accept merges that add new
        directions. Plain overwrites are blocked.
        """
        if not (0 <= row < self.height and 0 <= col < self.width):
            return
        if ch == " ":
            return

        # Infer directions from the character if not otherwise known
        new_dirs = _CHAR_TO_DIRECTIONS.get(ch, 0)

        existing = self._grid[row][col]
        existing_dirs = self._directions[row][col]

        if existing == " ":
            # Empty cell: just place
            self._grid[row][col] = ch
            self._directions[row][col] = new_dirs
        elif merge and existing_dirs and new_dirs:
            # Both cells carry directional info: merge via OR
            combined = existing_dirs | new_dirs
            if self._protected[row][col] and combined == existing_dirs:
                # Protected cell unchanged by merge: skip style update
                return
            derived = _DIRECTION_TO_CHAR.get(combined)
            if derived:
                self._grid[row][col] = derived
                self._directions[row][col] = combined
            elif self._protected[row][col]:
                # Can't derive a valid char, protected: don't overwrite
                return
            else:
                self._grid[row][col] = ch
                self._directions[row][col] = new_dirs
        elif self._protected[row][col]:
            # Protected cell: don't overwrite with non-directional character
            return
        else:
            self._grid[row][col] = ch
            self._directions[row][col] = new_dirs

        if style:
            self._style_grid[row][col] = style

    def put_text(self, row: int, col: int, text: str, style: str = "") -> None:
        """Place a string of characters starting at (row, col)."""
        for i, ch in enumerate(text):
            self.put(row, col + i, ch, merge=False, style=style)

    def put_styled_text(self, row: int, col: int, segments: list[tuple[str, str]]) -> None:
        """Place text with per-segment style keys. Each segment is (text, style_key)."""
        offset = 0
        for text, style in segments:
            for ch in text:
                self.put(row, col + offset, ch, merge=False, style=style)
                offset += 1

    def get_style(self, row: int, col: int) -> str:
        """Get the style key at a position."""
        if 0 <= row < self.height and 0 <= col < self.width:
            return self._style_grid[row][col]
        return "default"

    def to_styled_pairs(self) -> list[list[tuple[str, str]]]:
        """Return (char, style_key) pairs for each cell."""
        result: list[list[tuple[str, str]]] = []
        for r in range(self.height):
            row_pairs: list[tuple[str, str]] = []
            for c in range(self.width):
                row_pairs.append((self._grid[r][c], self._style_grid[r][c]))
            result.append(row_pairs)
        return result

    def draw_horizontal(self, row: int, col_start: int, col_end: int, ch: str, style: str = "") -> None:
        """Draw a horizontal line, setting LEFT|RIGHT directions on each cell."""
        c_min, c_max = min(col_start, col_end), max(col_start, col_end)
        for c in range(c_min, c_max + 1):
            self.put(row, c, ch, style=style)

    def draw_vertical(self, col: int, row_start: int, row_end: int, ch: str, style: str = "") -> None:
        """Draw a vertical line, setting UP|DOWN directions on each cell."""
        r_min, r_max = min(row_start, row_end), max(row_start, row_end)
        for r in range(r_min, r_max + 1):
            self.put(r, col, ch, style=style)

    def to_string(self) -> str:
        """Convert canvas to a string, trimming trailing whitespace per line."""
        lines: list[str] = []
        for row in self._grid:
            line = "".join(row).rstrip()
            lines.append(line)
        # Remove trailing empty lines
        while lines and not lines[-1]:
            lines.pop()
        return "\n".join(lines)

    def flip_vertical(self) -> None:
        """Flip the canvas vertically (for BT direction)."""
        self._grid.reverse()
        self._style_grid.reverse()
        self._directions.reverse()
        # Remap characters
        _flip_map = {
            "┌": "└", "┐": "┘", "└": "┌", "┘": "┐",
            "├": "├", "┤": "┤", "┬": "┴", "┴": "┬",
            "▼": "▲", "▲": "▼",
            "╭": "╰", "╮": "╯", "╰": "╭", "╯": "╮",
            "v": "^", "^": "v",
            "╔": "╚", "╗": "╝", "╚": "╔", "╝": "╗",
        }
        for r in range(self.height):
            for c in range(self.width):
                ch = self._grid[r][c]
                if ch in _flip_map:
                    self._grid[r][c] = _flip_map[ch]
                # Flip direction bits: UP <-> DOWN
                d = self._directions[r][c]
                if d:
                    flipped = d & (LEFT | RIGHT)  # keep horizontal
                    if d & UP:
                        flipped |= DOWN
                    if d & DOWN:
                        flipped |= UP
                    self._directions[r][c] = flipped

    def flip_horizontal(self) -> None:
        """Flip the canvas horizontally (for RL direction)."""
        for r in range(self.height):
            self._grid[r].reverse()
            self._style_grid[r].reverse()
            self._directions[r].reverse()
        _flip_map = {
            "┌": "┐", "┐": "┌", "└": "┘", "┘": "└",
            "├": "┤", "┤": "├", "┬": "┬", "┴": "┴",
            "►": "◄", "◄": "►",
            "╭": "╮", "╮": "╭", "╰": "╯", "╯": "╰",
            ">": "<", "<": ">",
            "╔": "╗", "╗": "╔", "╚": "╝", "╝": "╚",
        }
        for r in range(self.height):
            for c in range(self.width):
                ch = self._grid[r][c]
                if ch in _flip_map:
                    self._grid[r][c] = _flip_map[ch]
                # Flip direction bits: LEFT <-> RIGHT
                d = self._directions[r][c]
                if d:
                    flipped = d & (UP | DOWN)  # keep vertical
                    if d & LEFT:
                        flipped |= RIGHT
                    if d & RIGHT:
                        flipped |= LEFT
                    self._directions[r][c] = flipped
