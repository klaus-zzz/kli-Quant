"""研究业务事务；真实执行器通过服务端注入，不注册虚假后台任务。"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from psycopg.types.json import Jsonb

from backend.research.models import ResearchError, Submission
from backend.research.repository import TERMINAL


class ResearchService:
    def __init__(self, repository, archive, executor=None, max_calls=30, seconds=300):
        self.repo, self.archive, self.executor = repository, archive, executor
        self.max_calls, self.seconds = max_calls, seconds

    def get(self, owner, run_id):
        # 查询前收尾已过期执行；取消中必须等待执行器确认实际停止。
        self.expire(owner, run_id)
        with self.repo.transaction() as conn:
            return self.repo.run(conn, owner, run_id)

    def submit(self, owner, key, submission: Submission):
        """先持久受理，再快速派发；并发幂等由唯一约束裁决。"""
        request = submission.model_dump(mode="json")
        with self.repo.transaction() as conn:
            existing = conn.execute(
                "SELECT * FROM research_runs WHERE owner=%s AND idempotency_key=%s",
                (owner, key),
            ).fetchone()
            if existing:
                if existing["request"] != request:
                    raise ResearchError("idempotency_conflict")
                return existing, False
            if self.executor is None:
                raise ResearchError("executor_not_ready", 503)
            if submission.previous_run_id:
                previous = self.repo.run(conn, owner, submission.previous_run_id)
                if previous["status"] != "completed":
                    raise ResearchError("previous_result_not_ready")
            now, run_id = datetime.now(UTC), uuid4()
            inserted = conn.execute(
                "INSERT INTO research_runs "
                "(id,owner,idempotency_key,request,previous_run_id,cutoff,deadline,"
                "max_calls,status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'queued') "
                "ON CONFLICT (owner,idempotency_key) DO NOTHING RETURNING id",
                (
                    run_id,
                    owner,
                    key,
                    Jsonb(request),
                    submission.previous_run_id,
                    now,
                    now + timedelta(seconds=self.seconds),
                    self.max_calls,
                ),
            ).fetchone()
            if not inserted:
                existing = conn.execute(
                    "SELECT * FROM research_runs WHERE owner=%s AND idempotency_key=%s",
                    (owner, key),
                ).fetchone()
                if existing["request"] != request:
                    raise ResearchError("idempotency_conflict")
                return existing, False
        try:
            self.executor.submit(run_id)
        except Exception:
            # 派发失败可查询；执行器不得在 submit 内做长时间研究。
            self.fail(owner, run_id, "dispatch_failed")
        return self.get(owner, run_id), True

    def claim(self, owner, run_id):
        """只认领一次；重复回调不能重新运行已有任务。"""
        with self.repo.transaction() as conn:
            run = self.repo.run(conn, owner, run_id, lock=True)
            if run["status"] != "queued":
                return False
            if run["deadline"] <= datetime.now(UTC):
                self.repo.update_state(
                    conn, run_id, "failed", "ended", "deadline_exceeded"
                )
                return False
            self.repo.update_state(conn, run_id, "running", "researching")
            return True

    def cancel(self, owner, run_id):
        """取消只记录事实；实际停止须执行器确认，不伪造取消成功。"""
        with self.repo.transaction() as conn:
            run = self.repo.run(conn, owner, run_id, lock=True)
            if run["status"] == "queued":
                self.repo.update_state(conn, run_id, "cancelled", "ended")
            elif run["status"] == "running":
                self.repo.update_state(conn, run_id, "cancelling", "cancelling")
        return self.get(owner, run_id)

    def acknowledge_cancel(self, owner, run_id):
        with self.repo.transaction() as conn:
            run = self.repo.run(conn, owner, run_id, lock=True)
            if run["status"] == "cancelling":
                self.repo.update_state(conn, run_id, "cancelled", "ended")

    def fail(self, owner, run_id, code="executor_failed"):
        """仅保留允许的错误分类，不接收沙箱日志或任意错误正文。"""
        if code not in {"executor_failed", "dispatch_failed", "deadline_exceeded"}:
            raise ValueError("失败分类无效")
        with self.repo.transaction() as conn:
            run = self.repo.run(conn, owner, run_id, lock=True)
            if run["status"] not in TERMINAL and run["status"] != "cancelling":
                self.repo.update_state(conn, run_id, "failed", "ended", code)

    def progress(self, owner, run_id, stage):
        """阶段由受信适配器报告；不编造无法衡量的百分比。"""
        if stage not in {"researching", "collecting", "computing", "validating"}:
            raise ValueError("阶段无效")
        with self.repo.transaction() as conn:
            run = self.repo.run(conn, owner, run_id, lock=True)
            if run["status"] == "running":
                self.repo.update_state(conn, run_id, "running", stage)

    def reserve_call(self, owner, run_id):
        """先持锁扣预算再调用外部服务；失败也计费，重启不能重置额度。"""
        with self.repo.transaction() as conn:
            run = self.repo.run(conn, owner, run_id, lock=True)
            self.require_running(run)
            if run["used_calls"] >= run["max_calls"]:
                raise ResearchError("budget_exceeded")
            conn.execute(
                "UPDATE research_runs SET used_calls=used_calls+1 WHERE id=%s",
                (run_id,),
            )
            return run

    @staticmethod
    def require_running(run):
        """取消或超时后不再开始采集或发布；已有归档仍可读取。"""
        if run["status"] != "running":
            raise ResearchError("run_not_running")
        if run["deadline"] <= datetime.now(UTC):
            raise ResearchError("deadline_exceeded")

    def store_evidence(self, owner, run_id, kind, document, metadata):
        """服务端采集完成后归档；上传时不持数据库锁，入库前再次检查状态。"""
        self.require_running(self.get(owner, run_id))
        ref = self.archive.put(run_id, document)
        evidence_id = uuid4()
        with self.repo.transaction() as conn:
            run = self.repo.run(conn, owner, run_id, lock=True)
            self.require_running(run)
            conn.execute(
                "INSERT INTO research_evidence "
                "(id,run_id,kind,object_key,sha256,size,metadata) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (
                    evidence_id,
                    run_id,
                    kind,
                    ref["object_key"],
                    ref["sha256"],
                    ref["size"],
                    Jsonb(metadata),
                ),
            )
        return {
            "evidence_id": str(evidence_id),
            "run_id": str(run_id),
            "sha256": ref["sha256"],
            "kind": kind,
        }

    def read_evidence(self, owner, run_id, evidence_id):
        """固定输入重放入口：先查归属，再取对象并重新校验哈希。"""
        with self.repo.transaction() as conn:
            run = self.repo.run(conn, owner, run_id)
            ref = self.repo.evidence(conn, run, evidence_id)
        return ref, self.archive.read(ref)

    def collect_source(self, owner, run_id, url):
        from backend.research.fetch_client import fetch_source

        self.reserve_call(owner, run_id)
        document = fetch_source(url)
        metadata = {
            k: v for k, v in document.items() if k not in {"raw_base64", "blocks"}
        }
        return self.store_evidence(owner, run_id, "source", document, metadata)

    async def collect_dataset(self, owner, run_id, name, params, fields=""):
        """真实工具响应整体冻结，保留空数据、权限不足及截断状态。"""
        import asyncio

        from backend.research.validation import dataset_times, required_time_fields
        from backend.tushare import execute_query
        from sandbox.cli.catalog import validate

        validate(name, params, fields)
        requested_fields = fields
        if fields:
            fields = ",".join(
                dict.fromkeys([*fields.split(","), *required_time_fields(name)])
            )
        run = await asyncio.to_thread(self.reserve_call, owner, run_id)
        for key in ("trade_date", "start_date", "end_date", "ann_date"):
            if params.get(key) and params[key] > run["cutoff"].strftime("%Y%m%d"):
                raise ResearchError("future_query", 422)
        response = await execute_query(name, params, fields)
        document = {
            "api_name": name,
            "params": params,
            "fields": fields,
            "requested_fields": requested_fields,
            "response": response,
        }
        metadata = dataset_times(document, run["cutoff"])
        return await asyncio.to_thread(
            self.store_evidence, owner, run_id, "dataset", document, metadata
        )

    def record_execution(self, owner, run_id, code_id, input_ids, output_id, exit_code):
        """仅受信适配器调用，保存实际执行对应的代码、固定输入和输出摘要。"""
        items = {}
        for evidence_id in [code_id, *input_ids, output_id]:
            ref, _ = self.read_evidence(owner, run_id, evidence_id)
            items[str(evidence_id)] = {"sha256": ref["sha256"], "kind": ref["kind"]}
        if (
            items[str(code_id)]["kind"] != "code"
            or items[str(output_id)]["kind"] != "output"
        ):
            raise ResearchError("execution_kind_mismatch")
        document = {
            "code_id": str(code_id),
            "input_ids": [str(i) for i in input_ids],
            "output_id": str(output_id),
            "exit_code": exit_code,
            "items": items,
        }
        return self.store_evidence(owner, run_id, "execution", document, {})

    def expire(self, owner, run_id):
        """可信任务监管方收尾失联执行，取消中的执行须等待停止确认。"""
        with self.repo.transaction() as conn:
            run = self.repo.run(conn, owner, run_id, lock=True)
            if run["deadline"] <= datetime.now(UTC) and run["status"] in {
                "queued",
                "running",
            }:
                self.repo.update_state(
                    conn, run_id, "failed", "ended", "deadline_exceeded"
                )

    def check_draft(self, owner, run_id, draft):
        """只读检查与正式发布使用同一规则，允许 Agent 在截止前修正草稿。"""
        from pydantic import ValidationError

        from backend.research.models import ResultBundle
        from backend.research.validation import validate_bundle

        run = self.get(owner, run_id)
        self.require_running(run)
        bundle, errors = None, []
        try:
            bundle = ResultBundle.model_validate(draft)
            with self.repo.transaction() as conn:
                previous_hops = {
                    r["hop_id"]
                    for r in conn.execute(
                        "SELECT hop_id FROM research_hops WHERE run_id=%s",
                        (run["previous_run_id"],),
                    )
                }
            errors = validate_bundle(
                bundle,
                run,
                lambda eid: self.read_evidence(owner, run_id, eid),
                previous_hops,
            )
        except ValidationError:
            errors = ["invalid_result_schema"]
        return bundle, errors

    def publish(self, owner, run_id, draft):
        """先保存草稿并校验，再持锁发布；取消先到时不改变取消状态。"""
        run = self.get(owner, run_id)
        if run["status"] == "completed":
            current = self.result(owner, run_id)
            if current["result"] != draft:
                raise ResearchError("immutable_result")
            return current
        self.require_running(run)
        ref = self.archive.put(run_id, draft)
        bundle, errors = self.check_draft(owner, run_id, draft)
        result_id = uuid4()
        with self.repo.transaction() as conn:
            run = self.repo.run(conn, owner, run_id, lock=True)
            self.require_running(run)
            conn.execute(
                "INSERT INTO research_results "
                "(id,run_id,object_key,sha256,size,valid,errors,conclusion) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    result_id,
                    run_id,
                    ref["object_key"],
                    ref["sha256"],
                    ref["size"],
                    not errors,
                    Jsonb(errors),
                    bundle.conclusion if bundle and not errors else None,
                ),
            )
            if errors:
                self.repo.update_state(
                    conn, run_id, "failed", "ended", "validation_failed"
                )
            else:
                for hop in bundle.hops:
                    conn.execute(
                        "INSERT INTO research_hops VALUES (%s,%s,%s)",
                        (run_id, hop.id, Jsonb(hop.model_dump(mode="json"))),
                    )
                self.repo.update_state(conn, run_id, "completed", "ended")
        if errors:
            raise ResearchError("validation_failed")
        return self.result(owner, run_id)

    def result(self, owner, run_id):
        """结果固定为 v1；新证据必须新建执行，读取也检查所有已用引用。"""
        from backend.research.models import ResultBundle
        from backend.research.validation import validate_bundle

        with self.repo.transaction() as conn:
            run = self.repo.run(conn, owner, run_id)
            if run["status"] != "completed":
                raise ResearchError(f"result_unavailable:{run['status']}")
            ref = conn.execute(
                "SELECT * FROM research_results WHERE run_id=%s AND valid", (run_id,)
            ).fetchone()
            previous_hops = {
                r["hop_id"]
                for r in conn.execute(
                    "SELECT hop_id FROM research_hops WHERE run_id=%s",
                    (run["previous_run_id"],),
                )
            }
        document = self.archive.read(ref)
        errors = validate_bundle(
            ResultBundle.model_validate(document),
            run,
            lambda eid: self.read_evidence(owner, run_id, eid),
            previous_hops,
        )
        if errors:
            raise ResearchError("result_integrity_failed")
        return {
            "run_id": str(run_id),
            "result_id": str(ref["id"]),
            "version": 1,
            "sha256": ref["sha256"],
            "result": document,
        }
