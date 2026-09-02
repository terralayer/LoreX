from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker


class PostgresReleaseRepository:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions
