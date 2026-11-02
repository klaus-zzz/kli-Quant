import { useEffect, useState } from 'react';
import { api, statusLabels } from './api';
import type { Job, Run } from './api';
import RunView from './RunView';

// 卡片直接显示后台记录，展开后继续复用固定证据和产物详情。
export default function ResearchCard({ job, conversationId }: { job: Job; conversationId: string }) {
  const [open, setOpen] = useState(false);
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState('');
  const [cancelling, setCancelling] = useState(false);
  const active = ['queued', 'running'].includes(job.status);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const refresh = async () => {
      try {
        const current = await api<Run>(`/runs/${job.id}`, { signal: controller.signal });
        if (controller.signal.aborted) return;
        setRun(current); setError('');
        if (['queued', 'running'].includes(current.status) || current.cleanup_pending) {
          timer = setTimeout(() => void refresh(), 2000);
        }
      } catch { if (!controller.signal.aborted) setError('无法读取研究详情，请收起后重试'); }
    };
    void refresh();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [job.id, job.status, open]);

  async function cancel() {
    setCancelling(true);
    try { await api(`/conversations/${conversationId}/runs/${job.id}/cancel`, { method: 'POST' }); }
    catch { setError('取消失败，请重试'); }
    finally { setCancelling(false); }
  }
  return <article className="research-card" aria-label="后台研究">
    <h2>{statusLabels[job.status] || job.status} · 后台研究</h2>
    <p>{job.event || '原文研究'}</p>
    <small>执行 {job.id}{job.parent_run_id ? ' · 新证据复核版本' : ''}</small>
    {job.last_tool && <p>最近工具：{job.last_tool}</p>}
    {job.judgment && <p className="message-text">{String(job.judgment.conclusion || '')}</p>}
    {job.stop_reason && <small>结束原因：{job.stop_reason}</small>}
    <div className="actions">
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open}>
        {open ? '收起证据与执行记录' : '查看证据与执行记录'}</button>
      {active && <button type="button" disabled={cancelling} onClick={() => void cancel()}>取消研究</button>}
    </div>
    {error && <p role="alert">{error}</p>}
    {open && (run ? <RunView run={run} /> : <p>读取详情中…</p>)}
  </article>;
}
