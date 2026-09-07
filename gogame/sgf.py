"""SGF FF[4] reading and writing for Go game records.

Supports GM[1], FF[4], SZ, KM, HA, PB, PW, DT on the root node, and
moves as ;B[xy] / ;W[xy], with a pass written as an empty value
(;B[] or ;W[]).

SGF coordinates are two lowercase letters 'a'..'s' (a=0, ..., s=18),
covering the full 19x19 range with no letter skipped. This is *not*
the same as the displayed board labels (which run A..T skipping I) --
that mapping belongs to the UI layer, not here.

The parser is hand-written (no sgflib/gomill/etc.), and only follows
the main line of a game tree: if a node has multiple children
(variations), the first child is treated as the continuation and the
rest are ignored.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .board import Color, Point
from .rules import GameState, Rules

__all__ = [
    "SGFParseError",
    "point_to_sgf",
    "sgf_to_point",
    "game_to_sgf",
    "sgf_to_game",
]

_SGF_LETTERS = "abcdefghijklmnopqrs"  # index 0..18, one letter per coordinate


class SGFParseError(Exception):
    """Raised for malformed or unsupported SGF content."""


# -- coordinate mapping --------------------------------------------------


def point_to_sgf(point: Point) -> str:
    """Convert a (row, col) board point to its two-letter SGF coordinate.

    SGF lists the column first, then the row.
    """
    row, col = point
    if not (0 <= row < len(_SGF_LETTERS) and 0 <= col < len(_SGF_LETTERS)):
        raise ValueError(f"point {point} is out of SGF's representable range")
    return _SGF_LETTERS[col] + _SGF_LETTERS[row]


def sgf_to_point(coord: str) -> Point:
    """Convert a two-letter SGF coordinate to a (row, col) board point."""
    if len(coord) != 2:
        raise SGFParseError(f"invalid SGF coordinate: {coord!r}")
    try:
        col = _SGF_LETTERS.index(coord[0])
        row = _SGF_LETTERS.index(coord[1])
    except ValueError:
        raise SGFParseError(f"invalid SGF coordinate: {coord!r}") from None
    return (row, col)


# -- writing --------------------------------------------------------------


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("]", "\\]")


def _format_number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return str(value)


def game_to_sgf(
    game: GameState,
    black_name: Optional[str] = None,
    white_name: Optional[str] = None,
    date: Optional[str] = None,
) -> str:
    """Serialize a GameState's rules, handicap, and move history to SGF."""
    root_props = [
        "GM[1]",
        "FF[4]",
        f"SZ[{game.rules.board_size}]",
        f"KM[{_format_number(game.rules.komi)}]",
    ]
    if game.handicap >= 2:
        root_props.append(f"HA[{game.handicap}]")
    if black_name is not None:
        root_props.append(f"PB[{_escape(black_name)}]")
    if white_name is not None:
        root_props.append(f"PW[{_escape(white_name)}]")
    if date is not None:
        root_props.append(f"DT[{_escape(date)}]")

    nodes = [";" + "".join(root_props)]
    for move in game.history:
        tag = "B" if move.color == Color.BLACK else "W"
        value = "" if move.is_pass else point_to_sgf(move.point)
        nodes.append(f";{tag}[{value}]")

    return "(" + "".join(nodes) + ")\n"


# -- parsing ----------------------------------------------------------------


class _SGFNode:
    __slots__ = ("properties", "children")

    def __init__(self) -> None:
        self.properties: Dict[str, List[str]] = {}
        self.children: List["_SGFNode"] = []


class _Scanner:
    """Minimal character scanner for the SGF grammar."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.pos = 0

    def _skip_ws(self) -> None:
        while self.pos < len(self.text) and self.text[self.pos].isspace():
            self.pos += 1

    def peek(self) -> Optional[str]:
        self._skip_ws()
        return self.text[self.pos] if self.pos < len(self.text) else None

    def advance(self) -> Optional[str]:
        self._skip_ws()
        if self.pos >= len(self.text):
            return None
        ch = self.text[self.pos]
        self.pos += 1
        return ch

    def raw_advance(self) -> Optional[str]:
        if self.pos >= len(self.text):
            return None
        ch = self.text[self.pos]
        self.pos += 1
        return ch

    def expect(self, ch: str) -> None:
        got = self.advance()
        if got != ch:
            raise SGFParseError(f"expected {ch!r}, got {got!r} at offset {self.pos}")


def _parse_property_value(scanner: _Scanner) -> str:
    scanner.expect("[")
    chars: List[str] = []
    while True:
        ch = scanner.raw_advance()
        if ch is None:
            raise SGFParseError("unterminated property value")
        if ch == "\\":
            nxt = scanner.raw_advance()
            if nxt == "\n":
                continue  # soft line break: drop
            if nxt is not None:
                chars.append(nxt)
            continue
        if ch == "]":
            break
        chars.append(ch)
    return "".join(chars)


def _parse_node(scanner: _Scanner) -> _SGFNode:
    scanner.expect(";")
    node = _SGFNode()
    while True:
        ch = scanner.peek()
        if ch is None or not ch.isupper():
            break
        ident_chars = []
        while scanner.peek() is not None and scanner.peek().isupper():
            ident_chars.append(scanner.advance())
        ident = "".join(ident_chars)
        values = []
        while scanner.peek() == "[":
            values.append(_parse_property_value(scanner))
        node.properties[ident] = values
    return node


def _parse_sequence(scanner: _Scanner) -> List[_SGFNode]:
    nodes = []
    while scanner.peek() == ";":
        nodes.append(_parse_node(scanner))
    return nodes


def _parse_game_tree(scanner: _Scanner) -> Optional[_SGFNode]:
    scanner.expect("(")
    nodes = _parse_sequence(scanner)
    if not nodes:
        raise SGFParseError("game tree has no nodes")
    for i in range(len(nodes) - 1):
        nodes[i].children.append(nodes[i + 1])
    while scanner.peek() == "(":
        nodes[-1].children.append(_parse_game_tree(scanner))
    scanner.expect(")")
    return nodes[0]


def _main_line(root: _SGFNode) -> List[_SGFNode]:
    nodes = []
    node: Optional[_SGFNode] = root
    while node is not None:
        nodes.append(node)
        node = node.children[0] if node.children else None
    return nodes


def _apply_move(game: GameState, color: Color, value: str) -> None:
    if game.to_move != color:
        raise SGFParseError(
            f"SGF move color {color!r} does not match the expected turn {game.to_move!r}"
        )
    if value == "":
        game.pass_move()
    else:
        game.play(sgf_to_point(value))


def sgf_to_game(text: str) -> GameState:
    """Parse SGF text and replay it into a fresh GameState.

    Only the main line is followed; variations are ignored. Every move
    is replayed through GameState.play()/pass_move(), so an SGF file
    encoding an illegal move raises IllegalMoveError just as live play
    would.
    """
    scanner = _Scanner(text)
    if scanner.peek() != "(":
        raise SGFParseError("SGF text must start with a game tree '('")
    root = _parse_game_tree(scanner)
    nodes = _main_line(root)

    root_props = nodes[0].properties
    gm = root_props.get("GM", ["1"])[0]
    if gm != "1":
        raise SGFParseError(f"unsupported GM[{gm}]: only Go (GM[1]) is supported")
    size = int(root_props.get("SZ", ["19"])[0])
    komi = float(root_props.get("KM", ["0"])[0])
    handicap = int(root_props.get("HA", ["0"])[0])

    game = GameState(Rules(board_size=size, komi=komi), handicap=handicap)

    for node in nodes[1:]:
        if "B" in node.properties:
            _apply_move(game, Color.BLACK, node.properties["B"][0])
        elif "W" in node.properties:
            _apply_move(game, Color.WHITE, node.properties["W"][0])

    return game
