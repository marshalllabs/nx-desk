from typing import Callable


# Stands in for any callback whose calls can be ignored, such as progress or report lines.
def quiet(_value: object) -> None:
    pass


# Counts a file's bytes on top of the files of the run sent before it.
def offset(moved: Callable[[int], None], before: int) -> Callable[[int], None]:
    return lambda done: moved(before + done)
