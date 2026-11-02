// 最小 API 类型只覆盖界面展示的数据；完整审计字段以 JSON 详情显示。
export type Research = { id: string; title: string };
export type Application = { id: string; label: string; version: string; missing_services: string[] };
export type RunSummary = { id: string; status: string; as_of: string };
export type SavedRecord = { id: string; kind: string; data: Record<string, unknown> };
export type Run = RunSummary & {
  research_id: string;
  input: { application?: string };
  stop_reason: string | null;
  cleanup_pending: boolean;
  records: SavedRecord[];
  calls: { id: string; name: string; step: number; status: string; result: unknown }[];
};

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch('/api' + path, options);
  const body = await response.json();
  if (!response.ok) {
    const detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
    throw new Error(detail || `请求失败 (${response.status})`);
  }
  return body as T;
}

export const statusLabels: Record<string, string> = {
  submitting: '正在提交', queued: '等待 Worker', running: '正在执行', completed: '任务完成',
  inconclusive: '证据不足', limited: '达到限制', failed: '执行失败', cancelled: '已取消',
};

// 对话轮次和后台研究各自更新，失败消息不会隐藏已创建的任务。
export type Turn = {
  id: string; kind: string; content: string; response: string; status: string; error: string | null;
  created_at: string; context_start: string | null;
  calls: { name: string; arguments: unknown; result: unknown }[];
};
export type Job = {
  id: string; research_id: string; status: string; event: string; as_of: string;
  parent_run_id: string | null; stop_reason: string | null; last_tool: string | null;
  judgment: Record<string, unknown> | null;
};
export type Conversation = { id: string; title: string; turns: Turn[]; jobs: Job[]; tasks: RemoteTask[] };

// 通用远程收据不包含服务连接配置；金融结果从只读详情读取。
export type RemoteTask = {
  id: string; status: string; input: Record<string, unknown>; parent_task_id: string | null;
  cancel_requested: boolean; sync_error: string | null;
  snapshot: { revision?: string; summary?: string };
};
