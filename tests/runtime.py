import hashlib
import http.client
import os
import subprocess
import sys
from contextlib import ExitStack, contextmanager
from pathlib import Path
from types import ModuleType
from typing import Dict, Iterator
from unittest import mock

from nx_desk import config


class BuildConfig(ModuleType):
    VALUES: Dict[str, str] = {}


# Configuration tests may parse ordinary fixture files; local environment files stay unopened.
def fixture_config(path: Path) -> Dict[str, str]:
    if path.name == ".env" or path.name.startswith(".env."):
        return {}

    return PARSE_CONFIG(path=path)


PARSE_CONFIG = config.parse_dotenv


def synthetic_key(folder: Path) -> bytes:
    return hashlib.sha256(string=str(folder.resolve()).encode(encoding="utf-8")).digest()


@contextmanager
def isolated_runtime() -> Iterator[None]:
    build_config = BuildConfig(name="nx_desk_build_config")
    build_config.VALUES = {}

    with ExitStack() as stack:
        stack.enter_context(mock.patch.dict(in_dict=os.environ, values={}, clear=True))
        stack.enter_context(mock.patch.dict(in_dict=sys.modules, values={"nx_desk_build_config": build_config}))
        stack.enter_context(mock.patch.object(target=config, attribute="parse_dotenv", side_effect=fixture_config))

        # Import services only after configuration has been isolated.
        from nx_desk import credentials, net

        keyring = mock.Mock()
        keyring.get_password.return_value = ""
        stack.enter_context(mock.patch.object(target=credentials, attribute="keyring", new=keyring))
        stack.enter_context(mock.patch.object(target=credentials, attribute="folder_key", side_effect=synthetic_key))
        stack.enter_context(
            mock.patch.object(target=net, attribute="http_get", side_effect=AssertionError("HTTP must be mocked")),
        )
        stack.enter_context(
            mock.patch.object(
                target=subprocess,
                attribute="run",
                side_effect=AssertionError("Processes must be mocked"),
            ),
        )
        stack.enter_context(
            mock.patch.object(
                target=subprocess,
                attribute="Popen",
                side_effect=AssertionError("Processes must be mocked"),
            ),
        )
        stack.enter_context(
            mock.patch.object(
                target=http.client,
                attribute="HTTPSConnection",
                side_effect=AssertionError("HTTPS must be mocked"),
            ),
        )
        yield
