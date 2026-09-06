"""异步数据库：SQLAlchemy 2.0 async engine + 会话工厂。"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    pass


_settings = get_settings()

engine = create_async_engine(
    _settings.database_url,
    echo=False,
    pool_pre_ping=True,
    # SQLite 需要该参数以支持并发读写
    connect_args={"check_same_thread": False} if _settings.database_url.startswith("sqlite") else {},
)

SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session():
    """FastAPI 依赖：每个请求一个异步会话。"""
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    """建表（幂等）+ SQLite 轻量列迁移。"""
    from app.db import models  # noqa: F401  确保模型已注册

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_migrate_sqlite)


def _migrate_sqlite(conn) -> None:
    """为已存在的 SQLite 表补充新增列（幂等）。"""
    if conn.dialect.name != "sqlite":
        return
    _ensure_columns(
        conn,
        "trips",
        {"payment_status": "VARCHAR(32) DEFAULT 'draft'", "price": "FLOAT DEFAULT 0"},
    )


def _ensure_columns(conn, table: str, columns: dict[str, str]) -> None:
    existing = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
    for name, ddl in columns.items():
        if name not in existing:
            conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
