import bcrypt
import sys
import os

# Add project root to Python path
PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)
sys.path.insert(0, PROJECT_ROOT)

from db.database import get_session
from repositories.user_repository import UserRepository


USERNAME = "manager"
NEW_PASSWORD = "manager123"  # Change this


def change_password():
    new_hash = bcrypt.hashpw(
        NEW_PASSWORD.encode("utf-8"),
        bcrypt.gensalt(rounds=12)
    ).decode("utf-8")

    with get_session() as session:
        user = UserRepository.get_by_username(session, USERNAME)

        if user is None:
            print(f"User '{USERNAME}' not found.")
            return

        user.password_hash = new_hash
        session.commit()

        print(f"Password updated successfully for user '{USERNAME}'.")


if __name__ == "__main__":
    change_password()