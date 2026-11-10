"""Interactive local credential maintenance; never an HTTP or peer operation.

Stop the owner service first. All prompts are private, and this command preserves
identity keys, peer pins and application records. Lost-password recovery, key
rotation and old-backup invalidation are intentionally not provided.
"""
import argparse
import getpass
import json
import sqlite3
import warnings
from pathlib import Path

from .auth import AuthError, AuthOutcomeUnknown, LocalOwnerAuth


def main(argv=None):
    parser = argparse.ArgumentParser(description="Maintain one local pilot owner's credentials")
    parser.add_argument("command", choices=("change-password",))
    parser.add_argument("--directory", required=True, help="Existing private owner directory; stop its service first")
    args = parser.parse_args(argv)
    directory = Path(args.directory)
    # This is maintenance, never account enrolment. The auth constructor validates
    # permissions, file identities and its exclusive service/process lock.
    if not directory.is_dir() or not (directory / "auth.sqlite").is_file():
        raise SystemExit("An existing enrolled owner directory is required")
    auth = None
    try:
        auth = LocalOwnerAuth(directory)
        auth.public_identity()
        with warnings.catch_warnings():
            # getpass otherwise falls back to echoing stdin when no safe terminal
            # is available. Fail before that fallback can consume a secret.
            warnings.simplefilter("error", getpass.GetPassWarning)
            current = getpass.getpass("Current owner password: ")
            session = auth.login(current)
            new = getpass.getpass("New owner password (at least 12 characters): ")
            confirmation = getpass.getpass("Confirm new owner password: ")
        if new != confirmation:
            raise AuthError("New passwords do not match; credentials unchanged")
        result = auth.change_password(session, current, new)
        print(json.dumps(result, sort_keys=True))
    except getpass.GetPassWarning:
        raise SystemExit("A private interactive terminal is required; no password was requested through echoed input") from None
    except (AuthError, AuthOutcomeUnknown) as error:
        raise SystemExit(str(error)) from None
    except (OSError, sqlite3.Error):
        raise SystemExit("Credential maintenance unavailable. Restart the local pilot and inspect before retrying") from None
    finally:
        if auth is not None:
            auth.close()


if __name__ == "__main__":
    main()
