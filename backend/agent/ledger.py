"""会话归属和投递账本；研究结果仍以原研究表为准。"""

from uuid import uuid4

from backend.research.models import ResearchError


class Ledger:
    def __init__(self, repository):
        self.repo = repository

    def create_session(self, owner):
        """只由认证后的服务端分配会话标识。"""
        session = f"kq-{uuid4().hex}"
        with self.repo.transaction() as conn:
            conn.execute(
                "INSERT INTO agent_sessions(id,owner) VALUES (%s,%s)", (session, owner)
            )
        return session

    def session(self, owner, session):
        with self.repo.transaction() as conn:
            row = conn.execute(
                "SELECT id FROM agent_sessions WHERE id=%s AND owner=%s",
                (session, owner),
            ).fetchone()
        if not row:
            raise ResearchError("not_found", 404)
        return session

    def sessions(self, owner):
        """标题取首条用户问题，更新时间取最后投递；始终按认证归属筛选。"""
        with self.repo.transaction() as conn:
            return conn.execute(
                "SELECT s.id, COALESCE((SELECT left(question,80) FROM agent_deliveries "
                "WHERE session_id=s.id AND kind='chat' ORDER BY created_at LIMIT 1),"
                "'新建对话') AS title, COALESCE((SELECT max(updated_at) "
                "FROM agent_deliveries WHERE session_id=s.id),"
                "s.created_at) AS updated_at "
                "FROM agent_sessions s WHERE owner=%s ORDER BY updated_at DESC",
                (owner,),
            ).fetchall()

    def enqueue(
        self, message_id, session, thread, kind, question, run_id=None, effort=None
    ):
        """消息 ID 和研究版本均唯一；重复请求必须保持原始内容。"""
        with self.repo.transaction() as conn:
            conn.execute(
                "INSERT INTO agent_deliveries "
                "(id,session_id,thread_id,kind,question,run_id,effort) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (message_id, session, thread, kind, question, run_id, effort),
            )
            row = conn.execute(
                "SELECT * FROM agent_deliveries WHERE id=%s", (message_id,)
            ).fetchone()
            expected = (session, thread, kind, question, run_id, effort)
            if (
                not row
                or tuple(
                    row[k]
                    for k in (
                        "session_id",
                        "thread_id",
                        "kind",
                        "question",
                        "run_id",
                        "effort",
                    )
                )
                != expected
            ):
                raise ResearchError("idempotency_conflict")

    def pending(self):
        """同一会话串行投递，避免 Gateway 的忙时合并吞掉完成通知。"""
        with self.repo.transaction() as conn:
            return conn.execute(
                "SELECT d.* FROM agent_deliveries d WHERE d.state='pending' "
                "AND NOT EXISTS (SELECT 1 FROM agent_deliveries busy "
                "WHERE busy.thread_id=d.thread_id AND busy.state='sending') "
                "ORDER BY d.created_at LIMIT 20"
            ).fetchall()

    def begin(self, message_id):
        """发送前持久标记；进程此后崩溃不能安全假定消息未被处理。"""
        with self.repo.transaction() as conn:
            return bool(
                conn.execute(
                    "UPDATE agent_deliveries SET state='sending',updated_at=now() "
                    "WHERE id=%s AND state='pending' AND NOT EXISTS ("
                    "SELECT 1 FROM agent_deliveries busy WHERE busy.thread_id="
                    "agent_deliveries.thread_id AND busy.state='sending') RETURNING id",
                    (message_id,),
                ).fetchone()
            )

    def recover(self):
        """无 ACK 的在途消息保留为待核对，不自动重放模型执行。"""
        with self.repo.transaction() as conn:
            conn.execute(
                "UPDATE agent_deliveries SET state='uncertain',updated_at=now() "
                "WHERE state='sending'"
            )

    def record(self, frame):
        """按消息和序号去重；错误会话及终态后的迟到帧均丢弃。"""
        with self.repo.transaction() as conn:
            # 上游主动回复没有预先投递记录，只能归入服务端已登记的会话。
            if frame["message_id"].startswith("agent-"):
                conn.execute(
                    "INSERT INTO agent_deliveries"
                    "(id,session_id,thread_id,kind,question,state) "
                    "SELECT %s,id,id,'notification','','sending' FROM agent_sessions "
                    "WHERE id=%s ON CONFLICT DO NOTHING",
                    (frame["message_id"], frame["thread_id"]),
                )
            row = conn.execute(
                "SELECT * FROM agent_deliveries WHERE id=%s AND thread_id=%s "
                "FOR UPDATE",
                (frame["message_id"], frame["thread_id"]),
            ).fetchone()
            if (
                not row
                or row["state"] not in {"sending", "uncertain"}
                or frame["message_seq"] <= row["last_seq"]
            ):
                return False
            payload = frame["payload"]
            state = {"done": "done", "error": "failed"}.get(
                payload["type"], row["state"]
            )
            text = payload.get("text", "") if payload["type"] == "delta" else ""
            if len(row["answer"]) + len(text) > 200000:
                raise ResearchError("agent_response_too_large", 502)
            conn.execute(
                "UPDATE agent_deliveries SET state=%s,last_seq=%s,"
                "answer=answer||%s,updated_at=now() WHERE id=%s",
                (state, frame["message_seq"], text, row["id"]),
            )
        return True

    def deliveries(self, session):
        """公开视图只含投递状态和正文，内部提示及控制端凭据不出库。"""
        with self.repo.transaction() as conn:
            return conn.execute(
                "SELECT id,kind,run_id,state,answer,"
                "CASE WHEN kind='chat' THEN question ELSE '' END AS question "
                "FROM agent_deliveries "
                "WHERE session_id=%s AND kind<>'research' ORDER BY created_at",
                (session,),
            ).fetchall()
