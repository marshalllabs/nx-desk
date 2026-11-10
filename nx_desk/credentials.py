import hashlib
import os
import secrets
from pathlib import Path

import keyring
from keyring.errors import PasswordDeleteError

from .schemas.artwork import StoredSecret
from .utils.seal import seal, unseal

SERVICE = "NX Desk"
KEY_FILE = "secret_key"
KEY_SIZE = 32


# One entry per data folder, so two copies of the app keep their own secrets.
def account(name: str, folder: Path) -> str:
    digest = hashlib.sha256(string=str(folder.resolve()).encode(encoding="utf-8")).hexdigest()[:12]

    return f"{name}@{digest}"


# The key that seals secrets when no keyring works; made once, readable by the user only.
def folder_key(folder: Path) -> bytes:
    path = folder / KEY_FILE

    try:
        saved = bytes.fromhex(path.read_text(encoding="utf-8").strip())

        if len(saved) == KEY_SIZE:
            return saved

    except (OSError, ValueError):
        pass

    fresh = secrets.token_bytes(nbytes=KEY_SIZE)
    folder.mkdir(parents=True, exist_ok=True)
    handle = os.open(path=path, flags=os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode=0o600)

    with os.fdopen(fd=handle, mode="w", encoding="utf-8") as file:
        file.write(fresh.hex() + "\n")

    return fresh


# Keyring backends raise their own errors (D-Bus, a locked or missing service), so any failure
# means the keyring cannot be used here.
def keyring_set(user: str, value: str) -> bool:
    try:
        keyring.set_password(service_name=SERVICE, username=user, password=value)

        return keyring.get_password(service_name=SERVICE, username=user) == value

    except Exception:
        return False


def keyring_get(user: str) -> str:
    try:
        return keyring.get_password(service_name=SERVICE, username=user) or ""

    except Exception:
        return ""


def keyring_delete(user: str) -> bool:
    try:
        keyring.delete_password(service_name=SERVICE, username=user)

    except PasswordDeleteError:
        return True

    except Exception:
        return False

    return True


# An empty value forgets the secret. The keyring comes first; without one the value is sealed.
def save_secret(name: str, value: str, folder: Path) -> StoredSecret:
    user = account(name=name, folder=folder)

    if not value:
        keyring_delete(user=user)

        return StoredSecret()

    if keyring_set(user=user, value=value):
        return StoredSecret(place="keyring")

    keyring_delete(user=user)

    return StoredSecret(place="sealed", sealed=seal(key=folder_key(folder=folder), text=value))


def load_secret(name: str, stored: StoredSecret, folder: Path) -> str:
    if stored.place == "keyring":
        return keyring_get(user=account(name=name, folder=folder))

    if stored.place == "sealed" and stored.sealed:
        try:
            return unseal(key=folder_key(folder=folder), sealed=stored.sealed)

        except ValueError:
            return ""

    return ""
