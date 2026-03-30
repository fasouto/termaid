from enum import Enum, auto


class NodeShape(Enum):
    """Supported node shapes in Mermaid flowcharts."""
    RECTANGLE = auto()      # A[text] or plain A
    ROUNDED = auto()        # A(text)
    STADIUM = auto()        # A([text])
    SUBROUTINE = auto()     # A[[text]]
    DIAMOND = auto()        # A{text}
    HEXAGON = auto()        # A{{text}}
    CIRCLE = auto()         # A((text))
    DOUBLE_CIRCLE = auto()  # A(((text)))
    ASYMMETRIC = auto()     # A>text]
    CYLINDER = auto()       # A[(text)]
    PARALLELOGRAM = auto()  # A[/text/]
    PARALLELOGRAM_ALT = auto()  # A[\text\]
    TRAPEZOID = auto()      # A[/text\]
    TRAPEZOID_ALT = auto()  # A[\text/]
    START_STATE = auto()    # [*] start (filled circle ●)
    END_STATE = auto()      # [*] end (bullseye ◉)
    FORK_JOIN = auto()      # <<fork>>/<<join>> (thick bar ━━━)
    JUNCTION = auto()       # invisible routing point (architecture junctions)
