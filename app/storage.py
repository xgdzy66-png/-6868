"""Durable inventory models and transactional database setup."""
from __future__ import annotations

import os
import json
import ssl
from datetime import datetime, timezone

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Integer, String, Text, create_engine
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (CheckConstraint("quantity >= 0", name="ck_product_nonnegative"),)
    product_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    quantity: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)


class Movement(Base):
    __tablename__ = "movements"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(BigInteger, nullable=False)
    actor_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, default=utc_now, index=True)


class Owner(Base):
    __tablename__ = "owners"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)


class ProcessedUpdate(Base):
    __tablename__ = "processed_updates"
    update_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    response_json: Mapped[str] = mapped_column(LONGTEXT().with_variant(Text(), "sqlite"), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, default=utc_now)


def make_session_factory(database_url: str | None = None):
    url = database_url or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is required; no ephemeral database fallback is allowed")
    if url.startswith("mysql://"):
        url = "mysql+pymysql://" + url[len("mysql://"):]
    parsed = make_url(url)
    connect_args = {}
    if parsed.drivername == "mysql+pymysql":
        if "ssl" in parsed.query:
            raw_ssl = parsed.query["ssl"]
            if isinstance(raw_ssl, tuple):
                if len(raw_ssl) != 1:
                    raise ValueError("Ambiguous database SSL parameter")
                raw_ssl = raw_ssl[0]
            options = json.loads(raw_ssl) if raw_ssl.startswith("{") else {}
            if options.get("rejectUnauthorized", True) is False:
                raise ValueError("Unverified database TLS is not supported")
            # PyMySQL treats an empty dict as SSL disabled and may disable
            # verification without a CA. SSLContext enforces both.
            connect_args["ssl"] = ssl.create_default_context()
            parsed = parsed.difference_update_query(["ssl"])
        elif os.environ.get("ALLOW_PLAINTEXT_DB") == "1" and parsed.host == "db":
            # The self-hosted Compose DB is reachable only on its private network.
            pass
        else:
            raise ValueError("MySQL requires verified TLS; only isolated Compose db may opt out")
    engine = create_engine(parsed, connect_args=connect_args, pool_pre_ping=True, pool_recycle=300)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)
