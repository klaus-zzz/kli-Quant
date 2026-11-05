-- 研究归属、幂等键和运行预算在数据库中统一约束。
CREATE TABLE research_runs (
    id UUID PRIMARY KEY,
    owner TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request JSONB NOT NULL,
    previous_run_id UUID REFERENCES research_runs(id),
    cutoff TIMESTAMPTZ NOT NULL,
    deadline TIMESTAMPTZ NOT NULL,
    max_calls INTEGER NOT NULL CHECK (max_calls > 0),
    used_calls INTEGER NOT NULL DEFAULT 0 CHECK (used_calls >= 0),
    status TEXT NOT NULL CHECK (status IN
        ('queued', 'running', 'cancelling', 'completed', 'failed', 'cancelled')),
    stage TEXT NOT NULL DEFAULT 'queued',
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (owner, idempotency_key)
);

-- 内容对象不可覆盖；元数据明确记录时间可用性和来源限制。
CREATE TABLE research_evidence (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES research_runs(id),
    kind TEXT NOT NULL CHECK (kind IN ('source', 'dataset', 'code', 'output', 'execution')),
    object_key TEXT NOT NULL UNIQUE,
    sha256 TEXT NOT NULL,
    size INTEGER NOT NULL CHECK (size >= 0),
    metadata JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX research_evidence_run ON research_evidence(run_id);

-- 草稿可追加，正式结果每个执行最多一个；判断只随正式发布保存。
CREATE TABLE research_results (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES research_runs(id),
    object_key TEXT NOT NULL UNIQUE,
    sha256 TEXT NOT NULL,
    size INTEGER NOT NULL,
    valid BOOLEAN NOT NULL,
    errors JSONB NOT NULL,
    conclusion TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX research_result_published ON research_results(run_id) WHERE valid;
CREATE TABLE research_hops (
    run_id UUID NOT NULL REFERENCES research_runs(id),
    hop_id TEXT NOT NULL,
    body JSONB NOT NULL,
    PRIMARY KEY (run_id, hop_id)
);
