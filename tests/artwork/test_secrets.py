import json

from nx_desk import credentials
from nx_desk.utils.seal import seal, unseal
from tests.artwork.case import ArtCase


class SealTests(ArtCase):
    def test_sealed_text_comes_back_with_its_key_only(self) -> None:
        sealed = seal(key=b"k" * 32, text="secret")

        self.assertNotIn("secret", sealed)
        self.assertEqual(unseal(key=b"k" * 32, sealed=sealed), "secret")

        with self.assertRaises(ValueError):
            unseal(key=b"o" * 32, sealed=sealed)

    def test_each_seal_differs(self) -> None:
        self.assertNotEqual(seal(key=b"k" * 32, text="secret"), seal(key=b"k" * 32, text="secret"))


class KeyStorageTests(ArtCase):
    def registry_text(self) -> str:
        return (self.folder / "settings.json").read_text(encoding="utf-8")

    def test_the_keyring_holds_the_key_and_the_registry_only_its_place(self) -> None:
        self.assertEqual(self.vault.set_art_key(key="abc123"), "keyring")

        self.assertNotIn("abc123", self.registry_text())
        self.assertEqual(json.loads(self.registry_text())["art_key"], {"place": "keyring", "sealed": ""})
        self.assertIn("abc123", self.keyring.values())

    def test_without_a_keyring_the_key_is_sealed(self) -> None:
        self.break_keyring()

        self.assertEqual(self.vault.set_art_key(key="abc123"), "sealed")
        self.assertNotIn("abc123", self.registry_text())
        stored = self.vault.art_key
        self.assertEqual(
            credentials.load_secret(name="steamgriddb", stored=stored, folder=self.folder / ".catalogs"),
            "abc123",
        )

    def test_a_new_start_reads_the_key_back(self) -> None:
        self.vault.set_art_key(key="abc123")

        from nx_desk.vault import Vault

        again = Vault(base=self.folder)
        self.assertTrue(again.has_art_key())
        self.assertEqual(again._art_secret(), "abc123")

    def test_an_empty_key_forgets_it(self) -> None:
        self.vault.set_art_key(key="abc123")

        self.assertEqual(self.vault.set_art_key(key=""), "")
        self.assertFalse(self.vault.has_art_key())
        self.assertEqual(self.keyring, {})
