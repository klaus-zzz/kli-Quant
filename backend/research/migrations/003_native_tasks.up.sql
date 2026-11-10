-- 仅保存上游任务快照及业务关联，不维护另一套执行队列。
CREATE TABLE agent_tasks (
    task_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES agent_sessions(id),
    run_id UUID UNIQUE REFERENCES research_runs(id),
    payload JSONB NOT NULL
);

-- 升级前须停止旧执行器；旧研究不转成共享沙箱任务或自动重跑。
UPDATE research_runs SET status='failed',stage='ended',error='executor_failed'
WHERE status IN ('queued','running','cancelling');
UPDATE agent_deliveries SET state='failed'
WHERE kind IN ('research','notification') AND state IN ('pending','sending','uncertain');
