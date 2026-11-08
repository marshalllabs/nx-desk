# The size of a card in a grid and which cards are in view. No toolkit here, so the tests can import it.
# A model hands out the Card of a row under this role (Qt.ItemDataRole.UserRole + 1).
CARD_ROLE = 0x0101
# The cover of a card is a tall image of this shape; the most a card may grow is MAX_CELL wide.
SHAPE = (2, 3)
MIN_COVER = 160
MAX_CELL = 260
# Room inside a card around its cover, and between the cover and its text.
PAD = 8
GAP = 6
# Room between one card and the next.
MARGIN = 4
NAME_LINES = 2
MIN_CELL = MIN_COVER + 2 * PAD + 2 * MARGIN
MAX_COVER = (MAX_CELL - 2 * PAD - 2 * MARGIN, (MAX_CELL - 2 * PAD - 2 * MARGIN) * SHAPE[1] // SHAPE[0])


def columns(width: int, cell_width: int = MIN_CELL) -> int:
    return max(1, width // cell_width)


# The cover that fits a cell of this width, in the shape of SHAPE.
def cover_size(cell_width: int) -> tuple[int, int]:
    width = cell_width - 2 * (MARGIN + PAD)

    return width, round(width * SHAPE[1] / SHAPE[0])


# As many cells as fit across the view, each widened to share what is left (up to MAX_CELL), so no strip
# stays empty at the right. A cell holds the cover, the name on up to two lines and the platform on one.
def cell_size(width: int, line: int) -> tuple[int, int]:
    cell_width = min(width // columns(width=width), MAX_CELL) if width >= MIN_CELL else MIN_CELL
    cover_height = cover_size(cell_width=cell_width)[1]

    return cell_width, 2 * MARGIN + PAD + cover_height + GAP + (NAME_LINES + 1) * line + PAD


# The rows from `start` up to `end` that a grid shows, with `extra_rows` of cards after the last one in view.
def visible_slice(
    scroll: int,
    width: int,
    height: int,
    cell: tuple[int, int],
    total: int,
    extra_rows: int = 1,
) -> tuple[int, int]:
    per_row = columns(width=width, cell_width=cell[0])
    first_row = max(0, scroll // cell[1])
    last_row = max(0, scroll + height - 1) // cell[1] + extra_rows

    return min(total, first_row * per_row), min(total, (last_row + 1) * per_row)
