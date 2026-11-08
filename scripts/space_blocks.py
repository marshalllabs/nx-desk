import ast
import itertools
import sys
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATHS = ("main.py", "nx_desk", "scripts", "tests")

COMPOUND = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.With,
    ast.AsyncWith,
    ast.Try,
    ast.Match,
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
)


def blocks(tree: ast.AST) -> Iterator[list[ast.stmt]]:
    for node in ast.walk(node=tree):
        for field in ("body", "orelse", "finalbody"):
            statements = getattr(node, field, None)

            if isinstance(statements, list) and statements and isinstance(statements[0], ast.stmt):
                yield statements


def first_line(statement: ast.stmt) -> int:
    decorators = getattr(statement, "decorator_list", [])

    return min([statement.lineno, *(decorator.lineno for decorator in decorators)])


# Line numbers (1-based) that need a blank line inserted above them.
def gaps(source: str) -> set[int]:
    lines = source.splitlines()
    found = set()

    for statements in blocks(tree=ast.parse(source=source)):
        for previous, current in itertools.pairwise(statements):
            spaced = isinstance(current, COMPOUND) or isinstance(previous, COMPOUND) or isinstance(current, ast.Return)
            end = previous.end_lineno or previous.lineno

            if not spaced or first_line(statement=current) <= end:
                continue

            start = first_line(statement=current)

            # Comments right above a statement belong to it.
            while start - 1 > end and lines[start - 2].strip().startswith("#"):
                start -= 1

            if lines[start - 2].strip():
                found.add(start)

    return found


def space(source: str) -> str:
    lines = source.splitlines(keepends=True)

    for line in sorted(gaps(source=source), reverse=True):
        lines.insert(line - 1, "\n")

    return "".join(lines)


def files() -> Iterator[Path]:
    for name in PATHS:
        path = ROOT / name

        if path.is_file():
            yield path
        else:
            yield from sorted(path.rglob("*.py"))


def main() -> int:
    check = "--check" in sys.argv
    changed = []

    for path in files():
        source = path.read_text(encoding="utf-8")
        spaced = space(source=source)

        if spaced == source:
            continue

        changed.append(path.relative_to(ROOT))

        if not check:
            path.write_text(data=spaced, encoding="utf-8")

    for path in changed:
        print(f"{'would space' if check else 'spaced'} {path}")

    return 1 if check and changed else 0


if __name__ == "__main__":
    sys.exit(main())
