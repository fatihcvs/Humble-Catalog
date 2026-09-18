"""What `serve --lan` keeps on disk, and how each piece is made.

Everything lives in a `lan/` folder beside catalog.db: the pairing token,
the private certificate authority, and the server certificate issued
from it. Deliberately NOT inside catalog.db: `restore` would otherwise
bring back an old token and silently re-pair a phone that had been
unpaired. Backups and `reset` never touch this folder, and deleting it
resets the whole feature.

See docs/superpowers/specs/2026-09-18-lan-viewer-design.md.
"""
import secrets
from pathlib import Path

LAN_DIR = "lan"
TOKEN_FILE = "token"


class LanStateError(Exception):
    """lan/ is in a state that must not be repaired silently.

    The message always says what to run next.
    """


def lan_dir_for(db_path):
    return Path(db_path).resolve().parent / LAN_DIR


def rotate_token(lan_dir):
    """Write a fresh token, unpairing every device, and return it."""
    path = Path(lan_dir) / TOKEN_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    path.write_text(token + "\n", encoding="ascii")
    return token


def load_or_create_token(lan_dir):
    """The pairing token, created on first use.

    A token file that exists but cannot be read is an error, never a
    reason to write a new one: that would unpair every phone with no
    explanation.
    """
    path = Path(lan_dir) / TOKEN_FILE
    if not path.exists():
        return rotate_token(lan_dir)
    try:
        token = path.read_text(encoding="ascii").strip()
    except (OSError, UnicodeDecodeError) as exc:
        raise LanStateError(
            f"cannot read the pairing token at {path} ({exc}) -- run "
            "`serve --lan --new-token` to replace it") from exc
    if not token:
        raise LanStateError(
            f"the pairing token at {path} is empty -- run "
            "`serve --lan --new-token` to replace it")
    return token
