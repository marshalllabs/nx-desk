from .. import credentials, uploader
from ..schemas.api import GitHubOwner
from .logs import Logs

TOKEN_NAME = "github"


class GitHubAuth(Logs):
    def set_github_token(self, token: str) -> None:
        value = token.strip()

        if any(character.isspace() for character in value):
            raise ValueError("The token must not contain spaces or line breaks.")

        if not self.github_lock.acquire(blocking=False):
            raise ValueError("Wait for the GitHub operation to finish before changing the token.")

        try:
            user = credentials.account(name=TOKEN_NAME, folder=self.catalogs_dir)

            if value:
                if not credentials.keyring_set(user=user, value=value):
                    raise ValueError("Could not save the token. Unlock or enable the system keyring and try again.")

            else:
                # Unlike artwork secrets, GitHub tokens have no file-based fallback.
                if not credentials.keyring_delete(user=user):
                    raise ValueError("Could not remove the token. Unlock the system keyring and try again.")

            with self.lock:
                self.github_secret = value
                self.github_token_saved = bool(value)
                self.github_ready = None if value else False
                self._save_registry()

        finally:
            self.github_lock.release()

    def _github_token(self) -> str:
        with self.lock:
            if self.github_secret is None:
                value = credentials.keyring_get(
                    user=credentials.account(name=TOKEN_NAME, folder=self.catalogs_dir),
                )

                if value:
                    self.github_secret = value

                elif self.github_token_saved:
                    raise uploader.command.GitHubError(
                        "The saved GitHub token is unavailable. Unlock the system keyring or replace it in Settings.",
                    )

                else:
                    return ""

            return self.github_secret

    def _bind_github(self) -> None:
        uploader.command.authenticate(provider=self._github_token)

    def _login(self) -> None:
        self._bind_github()

        try:
            user = GitHubOwner.model_validate(obj=uploader.api.request(path="user"))

            if not user.login:
                raise uploader.command.GitHubError("GitHub did not return an authenticated account")

        except uploader.command.GitHubError:
            self.github_ready = False
            raise

        self.github_ready = True
