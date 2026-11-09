import unittest

from nx_desk import names


class GameGroupTests(unittest.TestCase):
    def test_game_of_reads_the_folder_name(self) -> None:
        self.assertEqual(first=names.game_of(folder="Ori - [VI] - [1.0.2-v131072]"), second="Ori")
        self.assertEqual(first=names.game_of(folder="Final Fantasy - [VI] - [Miss]"), second="Final Fantasy")
        self.assertEqual(first=names.game_of(folder="[On Switch]"), second="")

    def test_only_games_seen_twice_are_grouped(self) -> None:
        games = {
            "a": "Ori",
            "b": "Ori",
            "c": "Hades",
            "d": "",
            "e": "",
        }
        self.assertEqual(first=names.shared_games(games=games), second={"Ori": ["a", "b"]})
