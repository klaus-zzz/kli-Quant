"""可信控制端创建、接回和回收本项目沙箱。"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path

from backend.research.models import ResearchError
from sandbox.binding import bound_options
from sandbox.create_sandbox import ROOT, creation_options

CLI = Path(__file__).resolve().parents[2] / "sandbox" / "cli"


class Sandboxes:
    def __init__(self, repo, environ):
        self.repo, self.env = repo, environ

    def row(self, thread_id):
        with self.repo.transaction() as conn:
            return conn.execute(
                "SELECT * FROM agent_sandboxes WHERE thread_id=%s", (thread_id,)
            ).fetchone()

    def authenticate(self, identity):
        """只认宿主注入的随机身份，run_id 和来源 Header 不参与认证。"""
        digest = hashlib.sha256(identity.encode()).hexdigest()
        with self.repo.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM agent_sandboxes WHERE identity_sha256=%s "
                "AND active AND expires_at>now()",
                (digest,),
            ).fetchone()
        if not row:
            raise ResearchError("unauthorized", 401)
        return row

    def attach(self, row):
        """私有访问令牌只交给宿主 SDK；不经沙箱环境或业务响应传递。"""
        from cubesandbox import Sandbox

        config = creation_options(self.env)["config"]
        return Sandbox(
            {
                "sandboxID": row["sandbox_id"],
                "templateID": self.env["CUBESANDBOX_TEMPLATE_ID"],
                "domain": self.env["CUBESANDBOX_DOMAIN"],
                "trafficAccessToken": row["traffic_token"],
            },
            config=config,
        )

    def ensure(self, thread_id, session):
        """聊天与原生子 Agent 共用会话沙箱；研究结束不回收它。"""
        row = self.row(thread_id)
        if row and row["active"] and row["expires_at"] > datetime.now(UTC):
            return self.attach(row)
        if row:
            # 上游缓存不能热替换实例，过期会话明确结束，避免产生无法接回的新实例。
            raise ResearchError("session_expired")
        from cubesandbox import Sandbox

        identity = secrets.token_urlsafe(32)
        deadline = datetime.now(UTC) + timedelta(hours=1)
        timeout = max(1, int((deadline - datetime.now(UTC)).total_seconds()))
        source = (CLI / "research.py").read_bytes()
        with self.repo.transaction() as conn:
            conn.execute("DELETE FROM agent_sandboxes WHERE thread_id=%s", (thread_id,))
            conn.execute(
                "INSERT INTO agent_sandboxes "
                "(thread_id,session_id,identity_sha256,cli_sha256,expires_at) "
                "VALUES (%s,%s,%s,%s,%s)",
                (
                    thread_id,
                    session,
                    hashlib.sha256(identity.encode()).hexdigest(),
                    hashlib.sha256(source).hexdigest(),
                    deadline,
                ),
            )
        sb = Sandbox.create(
            **bound_options(self.env, identity, thread_id, "developer", timeout)
        )
        try:
            if not sb.traffic_access_token:
                raise ResearchError("private_sandbox_not_supported", 503)
            # 先保存回收句柄；初始化中断也能在重启时定位本次资源。
            with self.repo.transaction() as conn:
                conn.execute(
                    "UPDATE agent_sandboxes SET sandbox_id=%s,traffic_token=%s "
                    "WHERE thread_id=%s",
                    (sb.sandbox_id, sb.traffic_access_token, thread_id),
                )
            sb.files.write(f"{ROOT}/sandbox/cli/research.py", source)
            sb.files.write(
                f"{ROOT}/sandbox/cli/tushare.py", (CLI / "tushare.py").read_bytes()
            )
            sb.files.write(
                f"{ROOT}/sandbox/cli/axi.json",
                (CLI / "axi.json").read_bytes(),
            )
            with self.repo.transaction() as conn:
                conn.execute(
                    "UPDATE agent_sandboxes SET active=true WHERE thread_id=%s",
                    (thread_id,),
                )
            return sb
        except BaseException:
            sb.kill()
            raise

    def close(self, thread_id):
        """先撤销业务身份再销毁；销毁失败保留句柄供下一次重试。"""
        row = self.row(thread_id)
        if not row:
            return
        with self.repo.transaction() as conn:
            conn.execute(
                "UPDATE agent_sandboxes SET active=false WHERE thread_id=%s",
                (thread_id,),
            )
        if row["sandbox_id"]:
            from cubesandbox import SandboxNotFoundError

            try:
                self.attach(row).kill()
            except SandboxNotFoundError:
                pass
        with self.repo.transaction() as conn:
            conn.execute("DELETE FROM agent_sandboxes WHERE thread_id=%s", (thread_id,))
