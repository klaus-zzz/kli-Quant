-- 会话归属由单用户开发认证绑定，客户端不能自报任意用户。
CREATE TABLE agent_sessions (
    id TEXT PRIMARY KEY,
    owner TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 发送前落账；发送后失联只核对，不盲目重复执行模型或研究。
CREATE TABLE agent_deliveries (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES agent_sessions(id),
    thread_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('chat', 'research', 'notification')),
    run_id UUID REFERENCES research_runs(id),
    question TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending'
        CHECK (state IN ('pending', 'sending', 'done', 'uncertain', 'failed')),
    last_seq INTEGER NOT NULL DEFAULT -1,
    answer TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (run_id, kind)
);
CREATE INDEX agent_delivery_pending ON agent_deliveries(state, created_at);

-- 业务身份只存哈希；私有访问令牌供可信控制端接回，不能投影给用户。
CREATE TABLE agent_sandboxes (
    thread_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES agent_sessions(id),
    run_id UUID REFERENCES research_runs(id),
    sandbox_id TEXT UNIQUE,
    identity_sha256 TEXT NOT NULL UNIQUE,
    traffic_token TEXT,
    cli_sha256 TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    active BOOLEAN NOT NULL DEFAULT false
);
