import os
import sys

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)
sys.path.insert(0, PROJECT_ROOT)

from db.database import get_session
from db.models import User


with get_session() as session:
    users = session.query(User).all()

    print(f"Users count: {len(users)}")

    for u in users:
        print(f"id={u.id}, username={u.username}")