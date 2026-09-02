from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ReleaseRow(Base):
    __tablename__ = "releases"
    __table_args__ = (
        Index("ix_releases_normalized_title", "normalized_title"),
        Index("ix_releases_normalized_author", "normalized_author"),
        Index("ix_releases_narrator", "narrator"),
        Index("ix_releases_isbn10", "isbn10"),
        Index("ix_releases_isbn13", "isbn13"),
        Index("ix_releases_asin", "asin"),
        Index("ix_releases_series_position", "series", "series_position"),
        Index("ix_releases_posted_at", "posted_at"),
        Index("ix_releases_wanted_match", "wanted_key"),
        Index("ix_releases_download_status", "download_status"),
        Index("ix_releases_import_status", "import_status"),
        UniqueConstraint("fingerprint", name="ux_releases_fingerprint"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    normalized_title: Mapped[str] = mapped_column(Text)
    author: Mapped[str] = mapped_column(Text)
    normalized_author: Mapped[str] = mapped_column(Text)
    narrator: Mapped[str | None] = mapped_column(Text, nullable=True)
    format: Mapped[str] = mapped_column(String(16))
    size: Mapped[int] = mapped_column(BigInteger)
    completion: Mapped[float] = mapped_column(Float, default=1.0)
    source_subject: Mapped[str] = mapped_column(Text)
    nzb: Mapped[str] = mapped_column(Text, default="")
    isbn10: Mapped[str | None] = mapped_column(String(10), nullable=True)
    isbn13: Mapped[str | None] = mapped_column(String(13), nullable=True)
    asin: Mapped[str | None] = mapped_column(String(16), nullable=True)
    series: Mapped[str | None] = mapped_column(Text, nullable=True)
    series_position: Mapped[Decimal | None] = mapped_column(Numeric(8, 3), nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    wanted_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    download_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    import_status: Mapped[str | None] = mapped_column(String(32), nullable=True)


class ReleaseArticleRow(Base):
    __tablename__ = "release_articles"
    __table_args__ = (
        UniqueConstraint("message_id", name="ux_release_articles_message_id"),
        Index("ix_release_articles_release_id", "release_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    release_id: Mapped[str] = mapped_column(ForeignKey("releases.id", ondelete="CASCADE"), nullable=False)
    message_id: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[str] = mapped_column(Text)
    bytes: Mapped[int] = mapped_column(BigInteger)
    group: Mapped[str] = mapped_column(Text)


class IndexerCheckpointRow(Base):
    __tablename__ = "indexer_checkpoints"

    source: Mapped[str] = mapped_column(String(32), primary_key=True)
    group: Mapped[str] = mapped_column(Text, primary_key=True)
    article_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class LibraryBookRow(Base):
    __tablename__ = "library_books"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    release_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(Text)
    author: Mapped[str] = mapped_column(Text)
    narrator: Mapped[str | None] = mapped_column(Text, nullable=True)
    path: Mapped[str] = mapped_column(Text, nullable=False)


class DownloadJobRow(Base):
    __tablename__ = "download_jobs"
    __table_args__ = (Index("ix_download_jobs_status", "status", "created_order"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    release_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    created_order: Mapped[int] = mapped_column(BigInteger, nullable=False)


class ImportJobRow(Base):
    __tablename__ = "import_jobs"
    __table_args__ = (Index("ix_import_jobs_status", "status"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    release_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
