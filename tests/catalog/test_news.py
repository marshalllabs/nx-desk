from nx_desk.schemas.catalog import CatalogChanges
from nx_desk.schemas.notice import Notice
from nx_desk.vault.catalogs import catalog_news
from tests.catalog.case import CatalogCase
from tests.helpers import mod


class NewsTests(CatalogCase):
    def test_a_first_load_gives_no_notice(self) -> None:
        self.add(name="Mods", url="https://x.test/c.json", games=("one", "two"))
        self.assertEqual(first=self.store.take_notices(), second=[])

    def test_new_mods_are_noticed_once(self) -> None:
        self.add(name="Mods", url="https://x.test/c.json", games=("one",))

        with self.served(games=("one", "two")):
            self.store.check()

        self.assertEqual(first=self.store.take_notices(), second=[Notice(title="Mods", text="1 new mod: Two")])
        self.assertEqual(first=self.store.take_notices(), second=[])

    def test_no_notice_when_turned_off(self) -> None:
        self.store.set_notify(enabled=False)
        self.add(name="Mods", url="https://x.test/c.json", games=("one",))

        with self.served(games=("one", "two")):
            self.store.check()

        self.assertEqual(first=self.store.take_notices(), second=[])

    def test_changed_files_count_as_updates(self) -> None:
        old = [mod(id="a", name="A", sha256="1" * 64), mod(id="b", name="B", sha256="2" * 64)]
        new = [mod(id="a", name="A", sha256="3" * 64), mod(id="b", name="B", sha256="2" * 64), mod(id="c", name="C")]
        self.assertEqual(first=catalog_news(old=old, new=new), second=CatalogChanges(added=["C"], changed=["A"]))
