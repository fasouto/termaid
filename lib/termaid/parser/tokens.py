from enum import Enum, auto


class TokenType(Enum):
    # Header
    GRAPH = auto()
    FLOWCHART = auto()
    DIRECTION = auto()  # TB, TD, LR, BT, RL

    # Structural
    SUBGRAPH = auto()
    END = auto()
    DIRECTION_KW = auto()  # 'direction' keyword inside subgraph

    # Nodes
    ID = auto()
    LABEL = auto()      # text inside shape delimiters

    # Shape delimiters (opening)
    BRACKET_OPEN = auto()     # [
    BRACKET_CLOSE = auto()    # ]
    PAREN_OPEN = auto()       # (
    PAREN_CLOSE = auto()      # )
    BRACE_OPEN = auto()       # {
    BRACE_CLOSE = auto()      # }

    # Edges
    ARROW_SOLID = auto()      # -->
    ARROW_DOTTED = auto()     # -.->
    ARROW_THICK = auto()      # ==>
    ARROW_OPEN = auto()       # ---
    ARROW_DOTTED_OPEN = auto()  # -.-
    ARROW_THICK_OPEN = auto()   # ===
    ARROW_INVISIBLE = auto()  # ~~~
    ARROW_BIDIR = auto()      # <-->
    ARROW_CROSS = auto()      # --x
    ARROW_CIRCLE = auto()     # --o

    # Edge labels
    PIPE = auto()             # |
    EDGE_LABEL = auto()       # text between pipes

    # Misc
    AMPERSAND = auto()        # &
    CLASSDEF = auto()         # classDef keyword
    CLASS = auto()            # class keyword (for class assignment)
    STYLE = auto()            # style keyword
    CLICK = auto()            # click keyword
    TRIPLE_COLON = auto()     # ::: for style class shorthand
    SEMICOLON = auto()        # ;
    COMMENT = auto()          # %%
    NEWLINE = auto()
    EOF = auto()
