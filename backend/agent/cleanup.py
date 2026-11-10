"""开发结束后显式回收本业务库登记的沙箱；运行中的调度者会阻止清理。"""

import psycopg

from backend.agent.config import configured_runtime
from backend.research.config import configured_service


def main():
    runtime = configured_runtime(configured_service())
    if runtime is None:
        raise RuntimeError("请显式配置 Agent 与研究存储")
    # 与调度器共用数据库租约，只允许在后端停止后清理。
    with psycopg.connect(runtime.repo.dsn, autocommit=True, connect_timeout=5) as lease:
        if not lease.execute("SELECT pg_try_advisory_lock(31704212)").fetchone()[0]:
            raise RuntimeError("请先停止开发后端和 Agent，再清理沙箱")
        runtime.recover()
        with runtime.repo.transaction() as conn:
            rows = conn.execute("SELECT thread_id FROM agent_sandboxes").fetchall()
        for row in rows:
            runtime.sandboxes.close(row["thread_id"])
        print(f"已回收本业务库登记的 {len(rows)} 个沙箱")


if __name__ == "__main__":
    main()
