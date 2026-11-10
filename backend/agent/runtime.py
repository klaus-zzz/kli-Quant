"""OmniAgent Gateway 与原生后台任务接线，不重建研究执行队列。"""

import asyncio
import hmac
import json
import logging
from contextlib import suppress
from uuid import UUID

import httpx
import psycopg
from websockets.asyncio.client import connect

from backend.agent.ledger import Ledger
from backend.agent.sandboxes import Sandboxes
from backend.agent.tasks import NativeTasks
from backend.research.models import ResearchError

logger = logging.getLogger(__name__)


class Runtime:
    def __init__(self, research, environ):
        self.research, self.repo, self.env = research, research.repo, environ
        self.ledger = Ledger(self.repo)
        self.sandboxes = Sandboxes(self.repo, environ)
        self.native = NativeTasks(research)
        self.stop_requests = set()
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
        # run_id 只是业务选择器；认证仍来自宿主身份，归属必须查数据库。
        selected = request.headers.get("X-Research-Run")
        if selected:
            try:
                run_id = UUID(selected)
            except ValueError:
                raise ResearchError("invalid_run_id", 422) from None
            self.research.get(row["session_id"], run_id)
            row = {**row, "run_id": run_id}
        if request.method == "POST" and request.url.path == "/api/research/runs":
            if not self.ready:
                raise ResearchError("agent_not_ready", 503)
            # 原生通知只消费已有结果，不能自行启动下一次研究。
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
        """只确认原生执行入口在线；调用方随后使用返回的 agent 参数启动。"""
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

    async def thinking(self, session):
        """只转发模型能力和当前档位，模型密钥与运行配置不进入浏览器。"""
        try:
            async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
                response = await client.get(
                    self.env["OMNIAGENT_URL"].rstrip("/") + "/api/agent/model",
                    params={"thread_id": session},
                    headers={
                        "Authorization": "Bearer " + self.env["OMNIAGENT_GATEWAY_TOKEN"]
                    },
                )
            response.raise_for_status()
            value = response.json()["thinking"]
            return {
                key: value[key]
                for key in ("control", "levels", "recommended_effort", "current_effort")
            }
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise ResearchError("agent_model_unavailable", 503) from None

    async def start(self):
        """数据库锁保证同一业务库只有一个 Gateway 客户端。"""
        self.lease = psycopg.connect(self.repo.dsn, autocommit=True, connect_timeout=5)
        if not self.lease.execute("SELECT pg_try_advisory_lock(31704212)").fetchone()[
            0
        ]:
            self.lease.close()
            raise RuntimeError("研究开发实例已运行")
        await asyncio.to_thread(self.recover)
        self.research.executor = self
        self.task = asyncio.create_task(self.run())

    def recover(self):
        self.ledger.recover()
        # 原生任务可能仍在 Agent 中运行，重连后以 task_list 核对。

    async def stop(self):
        self.ready = False
        self.research.executor = None
        # 连接库收尾可能吞掉取消，先设置退出条件，不能等 task 返回后再设置。
        self.stopping.set()
        self.task.cancel()
        with suppress(asyncio.CancelledError):
            await self.task
        await asyncio.to_thread(self.recover)
        # 会话沙箱留给重启后的同一 Gateway 继续使用；开发结束由 cleanup 回收。
        # 上游缓存不能单独刷新，关闭聊天沙箱会让仍运行的 Agent 接到过期句柄。
        if self.lease:
            self.lease.close()

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
                    self.stop_requests.clear()
                    with self.repo.transaction() as conn:
                        sessions = conn.execute(
                            "SELECT id FROM agent_sessions"
                        ).fetchall()
                    for session in sessions:
                        await ws.send(
                            json.dumps(
                                {"type": "task_list", "thread_id": session["id"]}
                            )
                        )
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

    async def tick(self):
        # 只转发原生取消请求；聊天投递仍使用原来的消息账本。
        for task in await asyncio.to_thread(self.native.stops):
            if task["task_id"] not in self.stop_requests:
                await self.ws.send(
                    json.dumps(
                        {
                            "type": "task_stop",
                            "thread_id": task["session_id"],
                            "task_id": task["task_id"],
                        }
                    )
                )
                self.stop_requests.add(task["task_id"])
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
                            "effort": delivery["effort"],
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
        """任务帧与主动回复按已登记会话接收，浏览器离线仍然落库。"""
        async for raw in ws:
            frame = json.loads(raw)
            kind, session = frame.get("type"), frame.get("thread_id")
            if kind == "task":
                if not await asyncio.to_thread(
                    self.native.record, session, frame["payload"]
                ):
                    continue
            elif kind == "task_list":
                await asyncio.to_thread(self.native.snapshot, session, frame["tasks"])
            elif kind == "task_stop":
                # 回执不等于任务终态；补拉状态确认停止或已经完成。
                await self.ws.send(
                    json.dumps({"type": "task_list", "thread_id": session})
                )
                continue
            elif kind == "event":
                if not await asyncio.to_thread(self.ledger.record, frame):
                    continue
            else:
                continue
            for queue in list(self.listeners.get(session, ())):
                if queue.full():
                    while not queue.empty():
                        queue.get_nowait()
                    queue.put_nowait({"type": "resync_required"})
                queue.put_nowait(frame)
