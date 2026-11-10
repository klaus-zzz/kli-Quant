"""投影 OmniAgent 原生任务事件；本模块不启动或执行后台任务。"""

import re
from datetime import UTC, datetime
from uuid import UUID

from psycopg.types.json import Jsonb


class NativeTasks:
    def __init__(self, research):
        self.repo = research.repo

    def record(self, session, payload):
        """上游给出任务 ID，研究关联还必须匹配数据库中的会话归属。"""
        with self.repo.transaction() as conn:
            if not conn.execute(
                "SELECT 1 FROM agent_sessions WHERE id=%s", (session,)
            ).fetchone():
                return False
            run = None
            match = re.fullmatch(r"research:([0-9a-f-]{36})", payload.get("brief", ""))
            if (
                payload["kind"] == "agent"
                and payload["name"] == "deep-search"
                and match
            ):
                try:
                    run_id = UUID(match[1])
                except ValueError:
                    run_id = None
                run = conn.execute(
                    "SELECT * FROM research_runs WHERE id=%s AND owner=%s FOR UPDATE",
                    (run_id, session),
                ).fetchone()
            if run:
                existing = conn.execute(
                    "SELECT task_id FROM agent_tasks WHERE run_id=%s", (run["id"],)
                ).fetchone()
                if existing and existing["task_id"] != payload["task_id"]:
                    run = None
            saved = conn.execute(
                "INSERT INTO agent_tasks(task_id,session_id,run_id,payload) "
                "VALUES (%s,%s,%s,%s) ON CONFLICT (task_id) DO UPDATE "
                "SET payload=EXCLUDED.payload "
                "WHERE agent_tasks.session_id=EXCLUDED.session_id "
                "AND agent_tasks.payload->>'status'='running' RETURNING run_id",
                (
                    payload["task_id"],
                    session,
                    run["id"] if run else None,
                    Jsonb(payload),
                ),
            ).fetchone()
            if not saved:
                return False
            if run and saved["run_id"] == run["id"]:
                self._advance(conn, run, payload["status"])
        return True

    def _advance(self, conn, run, task_status):
        """执行终态不能冒充报告发布；取消以实际任务终止为准。"""
        state = run["status"]
        if state not in {"queued", "running", "cancelling"}:
            return
        if task_status != "running":
            if state == "cancelling" or task_status == "cancelled":
                self.repo.update_state(conn, run["id"], "cancelled", "ended")
            else:
                self.repo.update_state(
                    conn, run["id"], "failed", "ended", "executor_failed"
                )
        elif run["deadline"] <= datetime.now(UTC) and state != "cancelling":
            self.repo.update_state(
                conn, run["id"], "failed", "ended", "deadline_exceeded"
            )
        elif state == "queued":
            self.repo.update_state(conn, run["id"], "running", "researching")

    def snapshot(self, session, tasks):
        """重连补拉可恢复遗漏事件；上游重启丢失的任务只收尾，不重新执行。"""
        for task in tasks:
            self.record(session, task)
        known = {task["task_id"] for task in tasks}
        for row in self.list(session):
            if row["task_id"] not in known and row["status"] == "running":
                self.record(
                    session, {**row, "status": "failed", "error": "native_task_missing"}
                )

    def list(self, session):
        with self.repo.transaction() as conn:
            rows = conn.execute(
                "SELECT payload,run_id FROM agent_tasks WHERE session_id=%s "
                "ORDER BY task_id",
                (session,),
            ).fetchall()
        return [
            {**r["payload"], "run_id": str(r["run_id"]) if r["run_id"] else None}
            for r in rows
        ]

    def stops(self):
        """预算到期只请求停止对应原生任务，不销毁会话共享沙箱。"""
        with self.repo.transaction() as conn:
            conn.execute(
                "UPDATE research_runs SET status='failed',stage='ended',"
                "error='deadline_exceeded',updated_at=now() "
                "WHERE status IN ('queued','running') AND deadline<=now()"
            )
            return conn.execute(
                "SELECT t.task_id,t.session_id FROM agent_tasks t "
                "LEFT JOIN research_runs r ON r.id=t.run_id "
                "WHERE t.payload->>'status'='running' AND ("
                "r.status IN ('cancelling','cancelled','failed') OR "
                "(t.run_id IS NULL AND t.payload->>'kind'='agent' "
                "AND t.payload->>'name'='deep-search'))"
            ).fetchall()
