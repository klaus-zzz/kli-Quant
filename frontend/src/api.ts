// 浏览器仅持有用户输入的聊天凭据，所有业务请求都走同源后端。
export type Access = { token: string; session: string };
export type Delivery = {
  id: string;
  kind: string;
  question: string;
  answer: string;
  state: string;
};
export type Run = {
  run_id: string;
  question: string;
  previous_run_id: string | null;
  status: string;
  stage: string;
  error: string | null;
  cutoff: string;
  deadline: string;
  used_calls: number;
  max_calls: number;
};
export type Snapshot = {
  connected: boolean;
  deliveries: Delivery[];
  research: Run[];
};
export type Reference = { evidence_id: string; locator: string };
export type Hop = {
  id: string;
  parents: string[];
  question: string;
  finding: string;
  trigger: string;
  entities: string[];
  time_scope: string;
  supports: Reference[];
  counters: Reference[];
  gaps: string[];
  alternatives: string[];
  conditions: string;
  invalidation: string;
};
export type Report = {
  run_id: string;
  result_id: string;
  version: number;
  sha256: string;
  result: {
    conclusion: string;
    summary: string;
    valid_from: string;
    valid_until: string;
    conditions: string;
    invalidation: string;
    gaps: string[];
    hops: Hop[];
    revisions: { hop_id: string; change: string; reason: string }[];
    artifacts: {
      evidence_id: string;
      execution_id: string;
      inputs: string[];
      calendar_id: string;
      adjustment_factor_id: string | null;
      price_unit: string;
      return_unit: string;
      adjustment: string;
      return_basis: string;
      fee_bps: number;
      fee_basis: string;
    }[];
  };
};
export type Evidence = {
  evidence_id: string;
  run_id: string;
  kind: string;
  sha256: string;
  metadata: Record<string, unknown>;
  document: unknown;
};

const labels: Record<string, string> = {
  queued: "等待研究",
  running: "研究中",
  cancelling: "取消中",
  cancelled: "已取消",
  completed: "已完成",
  failed: "执行失败",
  researching: "查证中",
  collecting: "采集资料",
  computing: "计算中",
  validating: "校验中",
  ended: "已结束",
  pending: "等待回复",
  sending: "回复中",
  done: "回复完成",
  uncertain: "投递待核对",
  insufficient_evidence: "证据不足",
  conditional_observation: "条件性观察",
  no_opportunity: "没有机会",
  maintained: "维持",
  changed: "改变",
  withdrawn: "失效",
  source: "原文",
  dataset: "数据快照",
  code: "计算代码",
  output: "计算输出",
  execution: "执行记录",
  unauthorized: "聊天凭据不正确，请重新连接",
  agent_not_ready: "对话服务尚未就绪",
  executor_not_ready: "研究执行器尚未就绪",
  not_found: "会话或研究不存在，或无权访问",
  research_storage_unavailable: "研究存储暂不可用",
  deadline_exceeded: "研究时限已到",
  executor_failed: "研究执行失败，尚未发布有效结果",
  budget_exceeded: "调用预算已耗尽",
  validation_failed: "草稿未通过校验",
  result_integrity_failed: "结果完整性校验失败",
};
export const label = (value: string) => labels[value] ?? value;
export const date = (value: string) =>
  new Date(value).toLocaleString("zh-CN", { hour12: false });

// 不回显服务端任意错误正文，网络失败保留可重试入口。
export async function request<T>(
  access: Access,
  path: string,
  options: RequestInit = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      ...options,
      signal: options.signal
        ? AbortSignal.any([options.signal, AbortSignal.timeout(25000)])
        : AbortSignal.timeout(25000),
      headers: {
        Authorization: `Bearer ${access.token}`,
        "X-Session-ID": access.session,
        "Content-Type": "application/json",
        ...options.headers,
      },
    });
  } catch {
    throw new Error("连接中断或请求超时，请重试查询。");
  }
  const data = await response.json().catch(() => null);
  if (!response.ok)
    throw new Error(labels[data?.error] ?? `请求失败（${response.status}）`);
  if (!data || typeof data !== "object")
    throw new Error("服务响应无效，请重试查询。");
  return data as T;
}

// 固定版本放进页面地址；打开旧链接时不会自动选择最新研究。
export function runLink(session: string, run = "") {
  return `#${new URLSearchParams({ session, ...(run ? { run } : {}) })}`;
}

// 原文和模型文本不执行 HTML；外链只允许无内嵌凭据的 HTTP(S)。
export function safeUrl(value: unknown): string | undefined {
  if (typeof value !== "string") return;
  try {
    const url = new URL(value);
    if (
      ["http:", "https:"].includes(url.protocol) &&
      !url.username &&
      !url.password
    )
      return url.href;
  } catch {
    /* 无效链接保留为普通文字。 */
  }
}
