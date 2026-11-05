"""业务索引与事务锁；所有外部值使用 SQL 参数绑定。"""

from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from backend.research.models import ResearchError

TERMINAL = {"completed", "failed", "cancelled"}


class Repository:
    def __init__(self, dsn):
        self.dsn = dsn

    @contextmanager
    def transaction(self):
        """短连接配有界超时；事务异常自动回滚。"""
        with psycopg.connect(
            self.dsn,
            connect_timeout=5,
            row_factory=dict_row,
            options="-c statement_timeout=30000 -c lock_timeout=5000",
        ) as conn:
            yield conn

    def run(self, conn, owner, run_id, lock=False):
        """归属条件与查找同一语句，越权不泄漏执行是否存在。"""
        query = "SELECT * FROM research_runs WHERE id = %s AND owner = %s"
        if lock:
            query += " FOR UPDATE"
        row = conn.execute(query, (run_id, owner)).fetchone()
        if row is None:
            raise ResearchError("not_found", 404)
        return row

    def evidence(self, conn, run, evidence_id):
        """只接受当前执行或明确关联的同归属历史执行。"""
        row = conn.execute(
            "SELECT e.* FROM research_evidence e JOIN research_runs r ON r.id=e.run_id "
            "WHERE e.id=%s AND r.owner=%s AND (r.id=%s OR r.id=%s)",
            (evidence_id, run["owner"], run["id"], run["previous_run_id"]),
        ).fetchone()
        if row is None:
            raise ResearchError("invalid_reference")
        return row

    def update_state(self, conn, run_id, status, stage, error=None):
        """调用方持有行锁后更新，终态竞争由同一事务裁决。"""
        conn.execute(
            "UPDATE research_runs SET status=%s, stage=%s, error=%s, updated_at=now() "
            "WHERE id=%s",
            (status, stage, error, run_id),
        )
