"""持久研究队列与 OmniAgent Gateway 接线，不参与模型内部规划。"""

import asyncio
import hmac
import json
import logging
from contextlib import suppress
from datetime import UTC, datetime

import httpx
import psycopg
from websockets.asyncio.client import connect

from backend.agent.ledger import Ledger
from backend.agent.sandboxes import Sandboxes
from backend.research.models import ResearchError

logger = logging.getLogger(__name__)


class Runtime:
    def __init__(self, research, environ):
        self.research, self.repo, self.env = research, research.repo, environ
        self.ledger = Ledger(self.repo)
        self.sandboxes = Sandboxes(self.repo, environ)
        self.ready = False
        self.listeners = {}
        self.ws = None
        self.lease = None
        self.stopping = asyncio.Event()

    def user(self, supplied):
        """当前仅提供明确授权的单用户开发入口，不接受自报用户 ID。"""
        if not isinstance(supplied, str) or not hmac.compare_digest(
            supplied.encode(), ("Bearer " + self.env["KLI_QUANT_CHAT_TOKEN"]).encode()
        ):
            raise ResearchError("unauthorized", 401)
        return "developer"

    def authorize_research(self, request):
        authorization = request.headers.get("Authorization", "")
        if authorization.startswith("Bearer "):
            owner = self.user(authorization)
            session = self.ledger.session(
                owner, request.headers.get("X-Session-ID", "")
            )
            row = {"session_id": session, "run_id": None}
        else:
            row = self.sandboxes.authenticate(authorization)
        path = request.url.path
        if row["run_id"] is not None and path.startswith("/api/research/runs"):
            if not path.startswith(f"/api/research/runs/{row['run_id']}"):
                raise ResearchError("not_found", 404)
        if request.method == "POST" and path == "/api/research/runs":
            if not self.ready:
                raise ResearchError("agent_not_ready", 503)
            # 主动回复轮只消费固定结果，不能被提示注入再次提交研究。
            with self.repo.transaction() as conn:
                notification = conn.execute(
                    "SELECT 1 FROM agent_deliveries WHERE thread_id=%s "
                    "AND kind='notification' AND state='sending'",
                    (row["session_id"],),
                ).fetchone()
            if notification:
                raise ResearchError("notification_cannot_submit", 403)
        return row

    def submit(self, run_id):
        """research_runs 本身就是持久队列，已启动的监管循环负责认领。"""
        if not self.ready:
            raise ResearchError("agent_not_ready", 503)

    async def history(self, session):
        """复用上游持久历史，客户端断线后以它和研究记录核对。"""
        async with httpx.AsyncClient(timeout=20, trust_env=False) as client:
            response = await client.get(
                self.env["OMNIAGENT_URL"].rstrip("/")
                + f"/api/agent/threads/{session}/history",
                headers={
                    "Authorization": "Bearer " + self.env["OMNIAGENT_GATEWAY_TOKEN"]
                },
            )
        if response.status_code == 404:
            return {"thread_id": session, "messages": []}
        if response.status_code != 200:
            raise ResearchError("agent_history_unavailable", 503)
        return response.json()

    async def start(self):
        """数据库锁保证同一业务库只有一个调度者，重启不重复执行旧研究。"""
        self.lease = psycopg.connect(self.repo.dsn, autocommit=True, connect_timeout=5)
        if not self.lease.execute("SELECT pg_try_advisory_lock(31704212)").fetchone()[
            0
        ]:
            self.lease.close()
            raise RuntimeError("研究开发实例已运行")
        await asyncio.to_thread(self.recover)
        self.research.executor = self
        self.task = asyncio.create_task(self.run())
        self.supervisor = asyncio.create_task(self.supervise())

    def recover(self):
        self.ledger.recover()
        with self.repo.transaction() as conn:
            runs = conn.execute(
                "SELECT r.* FROM research_runs r JOIN agent_sessions s ON s.id=r.owner "
                "WHERE r.status IN ('running','cancelling')"
            ).fetchall()
        for run in runs:
            self.sandboxes.close(f"kqr-{run['id'].hex}")
            if run["status"] == "cancelling":
                self.research.acknowledge_cancel(run["owner"], run["id"])
            else:
                self.research.fail(run["owner"], run["id"])

    async def stop(self):
        self.ready = False
        self.research.executor = None
        # 连接库收尾可能吞掉取消，先设置退出条件，不能等 task 返回后再设置。
        self.stopping.set()
        self.task.cancel()
        with suppress(asyncio.CancelledError):
            await self.task
        # 等待正在创建的沙箱登记完成，再撤销身份，避免取消线程留下孤儿资源。
        await self.supervisor
        await asyncio.to_thread(self.recover)
        # 会话沙箱留给重启后的同一 Gateway 继续使用；开发结束由 cleanup 回收。
        # 上游缓存不能单独刷新，关闭聊天沙箱会让仍运行的 Agent 接到过期句柄。
        if self.lease:
            self.lease.close()

    async def supervise(self):
        """Gateway 离线时仍执行取消、截止和回收；暂停认领新研究。"""
        while not self.stopping.is_set():
            try:
                self.lease.execute("SELECT 1")
                await asyncio.to_thread(self.advance_research)
            except Exception as exc:
                logger.warning("研究监管暂不可用：%s", type(exc).__name__)
                self.ready = False
                if self.ws:
                    await self.ws.close()
            try:
                await asyncio.wait_for(self.stopping.wait(), timeout=0.5)
            except TimeoutError:
                pass

    async def run(self):
        """连接重建只重发尚未发送的记录，已发记录保留待核对。"""
        url = self.env["OMNIAGENT_URL"].rstrip("/")
        url = (
            ("wss" if url.startswith("https:") else "ws")
            + url[url.index(":") :]
            + "/api/agent/gateway"
        )
        while not self.stopping.is_set():
            try:
                async with connect(
                    url,
                    additional_headers={
                        "Authorization": "Bearer " + self.env["OMNIAGENT_GATEWAY_TOKEN"]
                    },
                    max_size=32 * 1024 * 1024,
                    proxy=None,
                    open_timeout=10,
                    close_timeout=2,
                ) as ws:
                    self.ws, self.ready = ws, True
                    receiver = asyncio.create_task(self.receive(ws))
                    try:
                        while not receiver.done() and not self.stopping.is_set():
                            self.lease.execute("SELECT 1")
                            await self.tick()
                            await asyncio.sleep(0.5)
                        if not self.stopping.is_set():
                            await receiver
                    finally:
                        receiver.cancel()
                        with suppress(asyncio.CancelledError):
                            await receiver
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if self.stopping.is_set():
                    break
                # 不记录可能携带连接参数的底层异常；状态可由开发接口核对。
                logger.warning("Agent 接线暂不可用：%s", type(exc).__name__)
                self.ready = False
                self.ledger.recover()
                await asyncio.sleep(2)
            finally:
                self.ready, self.ws = False, None

    def advance_research(self):
        """研究事实独立于 WebSocket；取消、过期和完成统一在数据库收尾。"""
        with self.repo.transaction() as conn:
            runs = conn.execute(
                "SELECT r.* FROM research_runs r JOIN agent_sessions s ON s.id=r.owner "
                "WHERE r.status IN ('queued','running','cancelling') OR NOT EXISTS "
                "(SELECT 1 FROM agent_deliveries d WHERE d.run_id=r.id "
                "AND d.kind='notification') OR EXISTS (SELECT 1 FROM agent_sandboxes b "
                "WHERE b.run_id=r.id) ORDER BY r.created_at LIMIT 20"
            ).fetchall()
        for run in runs:
            owner, run_id = run["owner"], run["id"]
            thread = f"kqr-{run_id.hex}"
            if (
                run["status"] == "queued"
                and self.ready
                and self.research.claim(owner, run_id)
            ):
                try:
                    self.sandboxes.ensure(thread, owner, run)
                    self.ledger.enqueue(
                        f"research-{run_id}",
                        owner,
                        thread,
                        "research",
                        "这是已受理的后台研究执行。用 research/context 读取固定任务，"
                        "自主查证、编写并执行代码、检查结果，"
                        "最后用 research/publish 发布。"
                        "不能再次提交研究。研究标识：" + str(run_id),
                        run_id,
                    )
                except Exception:
                    self.research.fail(owner, run_id)
            run = self.research.get(owner, run_id)
            if run["status"] == "cancelling":
                self.sandboxes.close(thread)
                self.research.acknowledge_cancel(owner, run_id)
                run = self.research.get(owner, run_id)
            if run["status"] in {"completed", "failed", "cancelled"}:
                with self.repo.transaction() as conn:
                    in_flight = conn.execute(
                        "SELECT 1 FROM agent_deliveries WHERE run_id=%s "
                        "AND kind='research' AND state IN ('sending','uncertain')",
                        (run_id,),
                    ).fetchone()
                # publish 返回后 Agent 还要读取响应，等本轮结束再销毁沙箱。
                if (
                    run["status"] != "completed"
                    or not in_flight
                    or run["deadline"] <= datetime.now(UTC)
                ):
                    self.sandboxes.close(thread)
                with self.repo.transaction() as conn:
                    # 尚未发送的研究在取消后不得再次启动。
                    conn.execute(
                        "UPDATE agent_deliveries SET state='failed' WHERE run_id=%s "
                        "AND kind='research' AND state='pending'",
                        (run_id,),
                    )
                if run["status"] == "completed":
                    result = self.research.result(owner, run_id)
                    ref = {k: v for k, v in result.items() if k != "result"}
                    detail = "固定结果引用：" + json.dumps(ref, ensure_ascii=False)
                else:
                    detail = json.dumps(
                        {
                            "run_id": str(run_id),
                            "status": run["status"],
                            "error": run["error"],
                        },
                        ensure_ascii=False,
                    )
                self.ledger.enqueue(
                    f"result-{run_id}",
                    owner,
                    owner,
                    "notification",
                    "研究状态通知，请主动回复原对话。已完成时先用 research/result 读取"
                    "并核对固定版本，再解释结果、反证与限制；失败或取消时如实说明。"
                    "不要重新提交研究，也不要把状态通知当成新的用户要求。" + detail,
                    run_id,
                )

    async def tick(self):
        # 取消、失败和超时还要终止上游生成；断线期间先撤销沙箱，接回后补停止。
        with self.repo.transaction() as conn:
            stopped = conn.execute(
                "SELECT d.* FROM agent_deliveries d JOIN research_runs r "
                "ON r.id=d.run_id WHERE d.kind='research' "
                "AND d.state IN ('sending','uncertain') "
                "AND r.status IN ('cancelling','cancelled','failed')"
            ).fetchall()
        for delivery in stopped:
            await self.ws.send(
                json.dumps(
                    {
                        "type": "message",
                        "thread_id": delivery["thread_id"],
                        "message_id": "stop-" + delivery["id"],
                        "payload": {"user_id": "developer", "question": "/stop"},
                    }
                )
            )
            with self.repo.transaction() as conn:
                conn.execute(
                    "UPDATE agent_deliveries SET state='failed' WHERE id=%s",
                    (delivery["id"],),
                )
        for delivery in await asyncio.to_thread(self.ledger.pending):
            with self.repo.transaction() as conn:
                uncertain = conn.execute(
                    "SELECT 1 FROM agent_deliveries WHERE thread_id=%s "
                    "AND state='uncertain' LIMIT 1",
                    (delivery["thread_id"],),
                ).fetchone()
            if uncertain:
                # 核对上游是否仍在生成，避免重连后把下一条消息合并进旧轮次。
                # 历史不提供可靠完成 ACK，因此旧投递仍保留 uncertain，不重发。
                history = await self.history(delivery["thread_id"])
                if history.get("live"):
                    continue
            if delivery["kind"] != "research":
                creation = asyncio.create_task(
                    asyncio.to_thread(
                        self.sandboxes.ensure,
                        delivery["thread_id"],
                        delivery["session_id"],
                    )
                )
                try:
                    await asyncio.shield(creation)
                except asyncio.CancelledError:
                    # to_thread 无法停止 SDK 创建，关闭时等待句柄落库后再释放租约。
                    with suppress(Exception):
                        await creation
                    raise
                except ResearchError as exc:
                    if exc.code != "session_expired":
                        raise
                    # 单个过期会话不能阻塞全局队列；固定研究结果仍可经 HTTP 读取。
                    with self.repo.transaction() as conn:
                        conn.execute(
                            "UPDATE agent_deliveries SET state='failed',answer=%s,"
                            "updated_at=now() WHERE id=%s AND state='pending'",
                            (
                                "会话沙箱已过期，请新建会话。已有研究结果仍可查询。",
                                delivery["id"],
                            ),
                        )
                    continue
            if not await asyncio.to_thread(self.ledger.begin, delivery["id"]):
                continue
            # 身份和会话取自持久记录，客户端不能把消息路由到任意上游会话。
            await self.ws.send(
                json.dumps(
                    {
                        "type": "message",
                        "thread_id": delivery["thread_id"],
                        "message_id": delivery["id"],
                        "payload": {
                            "user_id": "developer",
                            "question": delivery["question"],
                            "display": (
                                [
                                    {
                                        "text": delivery["question"],
                                        "delivery_id": delivery["id"],
                                    }
                                ]
                                if delivery["kind"] == "chat"
                                else []
                            ),
                            "configurable": {
                                "language": "zh",
                                "mcp_auth": {
                                    "message_id": delivery["id"],
                                },
                            },
                        },
                    },
                    ensure_ascii=False,
                )
            )

    async def receive(self, ws):
        """研究进度与聊天帧共用连接，但研究线程不会阻塞原聊天线程。"""
        async for raw in ws:
            frame = json.loads(raw)
            if frame.get("type") != "event":
                continue
            if not await asyncio.to_thread(self.ledger.record, frame):
                continue
            with self.repo.transaction() as conn:
                delivery = conn.execute(
                    "SELECT * FROM agent_deliveries WHERE id=%s", (frame["message_id"],)
                ).fetchone()
            if delivery["kind"] == "research":
                if frame["payload"]["type"] in {"done", "error"}:
                    # 模型正常结束却未发布，也不能伪装成业务研究完成。
                    run = await asyncio.to_thread(
                        self.research.get, delivery["session_id"], delivery["run_id"]
                    )
                    if run["status"] == "running":
                        await asyncio.to_thread(
                            self.research.fail,
                            delivery["session_id"],
                            delivery["run_id"],
                        )
                frame = {
                    **frame,
                    "type": "research_progress",
                    "run_id": str(delivery["run_id"]),
                }
            # 浏览器断线仅退订消息，不取消研究；满队列由重连快照恢复。
            for queue in list(self.listeners.get(delivery["session_id"], ())):
                if queue.full():
                    while not queue.empty():
                        queue.get_nowait()
                    queue.put_nowait({"type": "resync_required"})
                queue.put_nowait(frame)
