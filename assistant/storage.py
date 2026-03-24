"""Persistent JSON storage for accounts, pendings, notes, and opportunities."""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).parent.parent / "data"

ACCOUNTS_FILE     = DATA_DIR / "accounts.json"
PENDINGS_FILE     = DATA_DIR / "pendings.json"
NOTES_FILE        = DATA_DIR / "notes.json"
OPPORTUNITIES_FILE = DATA_DIR / "opportunities.json"


def new_id() -> str:
    return str(uuid.uuid4())[:8].upper()


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _load(path: Path) -> list:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
    return []


def _save(path: Path, data: list) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


# --- Accounts ---

def load_accounts() -> list:
    return _load(ACCOUNTS_FILE)


def save_accounts(accounts: list) -> None:
    _save(ACCOUNTS_FILE, accounts)


def find_account(identifier: str) -> Optional[dict]:
    """Find account by ID or name (case-insensitive partial match)."""
    accounts = load_accounts()
    ident_lower = identifier.lower()
    # Exact ID match first
    for a in accounts:
        if a["id"] == identifier:
            return a
    # Name match
    for a in accounts:
        if ident_lower in a["name"].lower():
            return a
    return None


# --- Pendings ---

def load_pendings() -> list:
    return _load(PENDINGS_FILE)


def save_pendings(pendings: list) -> None:
    _save(PENDINGS_FILE, pendings)


# --- Notes ---

def load_notes() -> list:
    return _load(NOTES_FILE)


def save_notes(notes: list) -> None:
    _save(NOTES_FILE, notes)


# --- Opportunities ---

def load_opportunities() -> list:
    return _load(OPPORTUNITIES_FILE)


def save_opportunities(opps: list) -> None:
    _save(OPPORTUNITIES_FILE, opps)
