"""显式、事务性的版本迁移；不在业务请求中隐式建表。"""

import argparse
import hashlib
import os
from pathlib import Path

import psycopg

MIGRATIONS = Path(__file__).with_name("migrations")


def migrate(dsn: str, direction: str = "up"):
    """串行迁移并校验历史文件，避免两个进程同时修改表结构。"""
    with psycopg.connect(dsn, connect_timeout=5) as conn:
        conn.execute("SELECT pg_advisory_xact_lock(31704211)")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS research_migrations "
            "(version TEXT PRIMARY KEY, sha256 TEXT NOT NULL)"
        )
        applied = dict(conn.execute("SELECT version, sha256 FROM research_migrations"))
        files = {p.name.removesuffix(".up.sql"): p for p in MIGRATIONS.glob("*.up.sql")}
        for version, digest in applied.items():
            if (
                version not in files
                or hashlib.sha256(files[version].read_bytes()).hexdigest() != digest
            ):
                raise RuntimeError("迁移历史不匹配")
        if direction == "down":
            if applied:
                version = max(applied)
                conn.execute((MIGRATIONS / f"{version}.down.sql").read_text())
                conn.execute(
                    "DELETE FROM research_migrations WHERE version = %s", (version,)
                )
            return
        if direction != "up":
            raise ValueError("迁移方向无效")
        for version, path in sorted(files.items()):
            if version not in applied:
                conn.execute(path.read_text())
                conn.execute(
                    "INSERT INTO research_migrations VALUES (%s, %s)",
                    (version, hashlib.sha256(path.read_bytes()).hexdigest()),
                )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="研究业务表版本迁移")
    parser.add_argument("direction", choices=["up", "down"])
    args = parser.parse_args()
    migrate(os.environ["RESEARCH_DATABASE_URL"], args.direction)
