import { useEffect, useState } from 'react';
import { api, statusLabels } from './api';
import type { RemoteTask, Run } from './api';
import RunView from './RunView';

// 领域详情经底座代理读取；浏览器不持有金融服务地址或令牌。
export default function RemoteResearchCard({ task, conversationId, cancel }: {
  task: RemoteTask; conversationId: string; cancel: (taskId: string) => Promise<unknown>;
}) {
  const [open, setOpen] = useState(false);
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState('');
  const base = `/conversations/${conversationId}/tasks/${task.id}`;
  const active = ['submitting', 'queued', 'running'].includes(task.status);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    void api<Run>(`${base}/detail`, { signal: controller.signal }).then(value => {
      if (!controller.signal.aborted) { setRun(value); setError(''); }
    }).catch(() => { if (!controller.signal.aborted) setError('研究详情暂不可用，请稍后重试'); });
    return () => controller.abort();
  }, [open, base, task.snapshot.revision]);
  return <article className="research-card" aria-label="后台研究">
    <h2>{statusLabels[task.status] || task.status} · 后台研究</h2>
    <p>{String(task.input.event || '原文研究')}</p>
    <small>执行 {task.id}{task.parent_task_id ? ' · 新证据复核版本' : ''}</small>
    <p className="message-text">{task.snapshot.summary}</p>
    {task.sync_error && <p role="status">状态同步暂不可用：{task.sync_error}，保留最近已确认状态。</p>}
    {task.cancel_requested && active && <p>正在等待金融服务确认取消。</p>}
    <div className="actions">
      <button onClick={() => setOpen(!open)} aria-expanded={open}>{open ? '收起详情' : '查看证据与执行记录'}</button>
      {active && <button disabled={task.cancel_requested} onClick={() => void cancel(task.id).catch(() => setError('取消未确认，请重试'))}>取消研究</button>}
    </div>
    {error && <p role="alert">{error}</p>}
    {open && (run ? <RunView run={run} resultBase={`/api${base}/results`} /> : <p>读取详情中…</p>)}
  </article>;
}
