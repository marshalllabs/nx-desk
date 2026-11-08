import unittest
from unittest import mock

from nx_desk import net, steamgriddb
from nx_desk.catalog.ports import card_url
from nx_desk.names import search_names
from nx_desk.schemas.port import Port
from nx_desk.utils.text import likeness, squash
from tests.artwork.case import Response, reply


class LikenessTests(unittest.TestCase):
    def test_equal_names_score_one_whatever_the_marks(self) -> None:
        self.assertEqual(squash(text="Pokémon: Red!"), "pokemonred")
        self.assertEqual(likeness(left="Pokémon Red", right="POKEMON-red"), 1.0)

    def test_a_name_inside_another_scores_high_but_a_tiny_one_does_not(self) -> None:
        self.assertEqual(likeness(left="Labyrinth 2", right="Labyrinth 2: The Ultimate Maze"), 0.9)
        self.assertLess(likeness(left="Go", right="Gone Home"), 0.6)

    def test_other_games_score_low(self) -> None:
        self.assertLess(likeness(left="Data Defense", right="Counter-Strike"), 0.6)
        self.assertEqual(likeness(left="", right="Game"), 0.0)


class SearchNameTests(unittest.TestCase):
    def test_a_plain_name_has_one_spelling(self) -> None:
        self.assertEqual(search_names(name="Super Mario 64"), ["Super Mario 64"])

    def test_port_words_and_repository_separators_are_dropped_in_the_second_spelling(self) -> None:
        self.assertEqual(search_names(name="ff4_nx"), ["ff4nx", "ff4"])
        self.assertEqual(search_names(name="rvgl-for-switch"), ["rvgl-for-switch", "rvgl"])
        self.assertEqual(search_names(name="Kirikiroid2-NX")[1], "Kirikiroid2")
        self.assertEqual(search_names(name="D.Smile NX")[1], "D Smile")

    def test_a_name_that_would_become_empty_or_tiny_is_not_offered(self) -> None:
        self.assertEqual(len(search_names(name="NX")), 1)
        self.assertEqual(len(search_names(name="ab_nx")), 1)


class CardTests(unittest.TestCase):
    def test_only_a_plain_github_repository_has_a_card(self) -> None:
        def port(url: str) -> Port:
            return Port(id="o/r", name="R", platform="PC", url=url)

        self.assertEqual(
            card_url(port=port(url="https://github.com/Owner/Repo")),
            "https://opengraph.githubassets.com/1/Owner/Repo",
        )
        self.assertEqual(
            card_url(port=port(url="https://github.com/Owner/Repo/")),
            "https://opengraph.githubassets.com/1/Owner/Repo",
        )

        for url in ("", "https://gitlab.com/o/r", "https://github.com/o/r/tree/x", "https://github.com/o"):
            self.assertEqual(card_url(port=port(url=url)), "")


# Search hits by name, then art by game id.
class FakeSearch:
    def __init__(self, hits: dict[str, list[tuple[int, str]]], art: dict[int, str]) -> None:
        self.hits = hits
        self.art = art
        self.searches: list[str] = []

    def __call__(self, url: str, headers: dict[str, str] | None = None, timeout: int = 30) -> Response:
        path = url.split("/api/v2", 1)[1].split("?", 1)[0]

        if path.startswith("/search/autocomplete/"):
            name = path.removeprefix("/search/autocomplete/").replace("%20", " ")
            self.searches.append(name)

            return reply(data=[{"id": game_id, "name": title} for game_id, title in self.hits.get(name, [])])

        kind, game_id = path.split("/")[1], int(path.rsplit("/", 1)[1])
        url_found = self.art.get(game_id)

        return reply(data=[{"url": f"{url_found}/{kind}.png"}] if url_found else [])


class SearchTests(unittest.TestCase):
    def lookup(self, fake: FakeSearch, name: str, others: tuple[str, ...] = ()) -> steamgriddb.ArtLookup:
        with mock.patch.object(net, "http_get", side_effect=fake):
            return steamgriddb.lookup(name=name, key="k", others=others)

    def test_the_best_named_hit_wins_not_the_first(self) -> None:
        fake = FakeSearch(
            hits={"Data Defense": [(1, "Something Else"), (2, "Data Defense")]},
            art={1: "https://cdn.test/one", 2: "https://cdn.test/two"},
        )
        self.assertEqual(self.lookup(fake=fake, name="Data Defense").game_id, 2)

    def test_a_hit_with_another_name_is_refused(self) -> None:
        fake = FakeSearch(hits={"Labyrinth 2": [(9, "Counter-Strike")]}, art={9: "https://cdn.test/nine"})
        found = self.lookup(fake=fake, name="Labyrinth 2")
        self.assertEqual((found.game_id, found.cover), (0, ""))
        self.assertEqual(found.rules, 1)

    def test_another_spelling_is_tried_until_one_has_art(self) -> None:
        fake = FakeSearch(hits={"ff4nx": [], "ff4": [(5, "FF4")]}, art={5: "https://cdn.test/five"})
        found = self.lookup(fake=fake, name="ff4nx", others=("ff4",))
        self.assertEqual((found.game_id, fake.searches), (5, ["ff4nx", "ff4"]))
        self.assertTrue(found.cover)

    def test_a_game_found_without_art_is_kept_when_no_spelling_does_better(self) -> None:
        fake = FakeSearch(hits={"Game": [(3, "Game")], "Game Two": []}, art={})
        found = self.lookup(fake=fake, name="Game", others=("Game Two",))
        self.assertEqual((found.game_id, found.cover, found.background), (3, "", ""))
