import unittest

from nx_desk import names


class GameGroupTests(unittest.TestCase):
    def test_game_of_reads_the_folder_name(self) -> None:
        self.assertEqual(names.game_of(folder="Ori - [VI] - [1.0.2-v131072]"), "Ori")
        self.assertEqual(names.game_of(folder="Final Fantasy - [VI] - [Miss]"), "Final Fantasy")
        self.assertEqual(names.game_of(folder="[On Switch]"), "")

    def test_only_games_seen_twice_are_grouped(self) -> None:
        games = {
            "a": "Ori",
            "b": "Ori",
            "c": "Hades",
            "d": "",
            "e": "",
        }
        self.assertEqual(names.shared_games(games=games), {"Ori": ["a", "b"]})
