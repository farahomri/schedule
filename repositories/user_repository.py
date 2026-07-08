from __future__ import annotations

from sqlalchemy.orm import Session

from db.models import User


class UserRepository:
    @staticmethod
    def get_by_username(session: Session, username: str) -> User | None:
        return session.query(User).filter_by(username=username).first()

    @staticmethod
    def create(session: Session, username: str, password_hash: str, role: str) -> User:
        user = User(username=username, password_hash=password_hash, role=role)
        session.add(user)
        session.flush()  # assigns user.id without committing
        return user
