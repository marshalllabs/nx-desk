from collections.abc import Callable

# (level, time, game, text); game is empty for lines that belong to no game.
LogEntry = tuple[str, str, str, str]
# Called with the bytes moved so far.
Progress = Callable[[int], None]
# Called with one line about a running job.
Report = Callable[[str], None]
