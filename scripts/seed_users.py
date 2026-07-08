"""
Seed initial users into the database.

Run once after the baseline migration:
    python scripts/seed_users.py

Passwords are read from environment variables. If a variable is not set
the script prompts interactively using getpass (input is hidden).

Environment variables (optional):
    SEED_ADMIN_PASSWORD    password for the 'admin' account
    SEED_MANAGER_PASSWORD  password for the 'manager' account
    SEED_USER_PASSWORD     password for the 'user' account
"""

import getpass
import os
import sys

# Allow running the script directly from any working directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bcrypt

from db.database import get_session
from repositories.user_repository import UserRepository

_USERS = [
    ("admin",   "admin",   "SEED_ADMIN_PASSWORD"),
    ("manager", "manager", "SEED_MANAGER_PASSWORD"),
    ("user",    "user",    "SEED_USER_PASSWORD"),
]


def _read_password(username: str, env_key: str) -> str:
    value = os.environ.get(env_key, "")
    if value:
        return value
    return getpass.getpass(f"  Password for '{username}': ")


def _hash(plaintext: str) -> str:
    return bcrypt.hashpw(plaintext.encode(), bcrypt.gensalt(rounds=12)).decode()


def main() -> None:
    print("Seeding users...")
    with get_session() as session:
        for username, role, env_key in _USERS:
            if UserRepository.get_by_username(session, username):
                print(f"  SKIP    '{username}' already exists")
                continue

            plaintext = _read_password(username, env_key)
            if not plaintext:
                print(f"  SKIP    no password provided for '{username}'")
                continue

            UserRepository.create(session, username, _hash(plaintext), role)
            print(f"  CREATED '{username}' (role={role})")

    print("\nDone.")


if __name__ == "__main__":
    main()

