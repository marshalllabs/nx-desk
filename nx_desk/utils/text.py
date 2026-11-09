import difflib
import unicodedata
from typing import List


# Only letters and digits, in lower case and without accents, so names that differ in marks compare equal.
def squash(text: str) -> str:
    return "".join(char for char in unicodedata.normalize("NFKD", text).casefold() if char.isalnum())


# How alike two names are, from 0 to 1: equal names score 1, one inside the other 0.9 (when it is
# long enough to mean something), else the share of matching letters.
def likeness(left: str, right: str) -> float:
    first, second = squash(text=left), squash(text=right)

    if not first or not second:
        return 0.0

    if first == second:
        return 1.0

    short, long = sorted((first, second), key=len)

    if len(short) >= 4 and short in long:
        return 0.9

    return difflib.SequenceMatcher(isjunk=None, a=first, b=second).ratio()


# Thousands are grouped, so counts match the "All (30,030)" style of the filter buttons.
def plural(count: int, word: str) -> str:
    return f"{count:,} {word}" if count == 1 else f"{count:,} {word}s"


# The first few names, then how many more.
def few_names(names: List[str], shown: int = 3) -> str:
    text = ", ".join(names[:shown])

    return f"{text} and {len(names) - shown} more" if len(names) > shown else text


# "Download all" becomes "Re-download all" when the work was done before.
def again(text: str, done: bool) -> str:
    return f"Re-{text[:1].lower()}{text[1:]}" if done and text else text
