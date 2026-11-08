import re

from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat, QTextDocument

from ..theme import COLORS


# Colors the template the way code editors color JSON: keys, text, numbers and the rest.
class JsonHighlighter(QSyntaxHighlighter):
    TOKENS = re.compile(
        pattern=r'(?P<key>"(?:[^"\\]|\\.)*"(?=\s*:))|(?P<text>"(?:[^"\\]|\\.)*")|(?P<number>-?\d+(?:\.\d+)?)|(?P<word>true|false|null)|(?P<mark>[{}\[\]:,])',
    )
    COLORS = {"key": "accent", "text": "ok", "number": "miss", "word": "miss", "mark": "muted"}

    def __init__(self, document: QTextDocument) -> None:
        super().__init__(document)
        self.formats: dict[str, QTextCharFormat] = {}

        for kind, color in self.COLORS.items():
            shown = QTextCharFormat()
            shown.setForeground(QColor(COLORS[color]))

            if kind == "key":
                shown.setFontWeight(QFont.Weight.Bold)

            self.formats[kind] = shown

    def highlightBlock(self, text: str) -> None:
        for match in self.TOKENS.finditer(string=text):
            kind = match.lastgroup

            if kind:
                self.setFormat(match.start(), match.end() - match.start(), self.formats[kind])
