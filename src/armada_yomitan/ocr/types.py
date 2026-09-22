"""OCR result types."""

from dataclasses import dataclass


@dataclass
class Word:
    text: str
    left: int
    top: int
    width: int
    height: int
    conf: float
    block: int
    par: int
    line: int


@dataclass
class Line:
    text: str
    box: tuple       # (left, top, right, bottom), crop pixels
    glyphs: list     # one (left, top, right, bottom) per character of text
    conf: float      # 0-100
    exact: bool
    vertical: bool


@dataclass
class Hit:
    line: Line
    index: int
    char: str
    context: str
    offset: int
    scan_text: str
    box: tuple
    tap: tuple
