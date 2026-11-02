import { useEffect, useState } from 'react';
import { api, statusLabels } from './api';
import type { Research, Run, RunSummary } from './api';
import RunView from './RunView';

// 保留迁移前的研究与版本入口，不要求用户重新创建旧研究。
export default function LegacyResearch() {
  const [open, setOpen] = useState(false);
  const [researches, setResearches] = useState<Research[]>([]);
  const [researchId, setResearchId] = useState('');
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [runId, setRunId] = useState('');
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    void api<Research[]>('/researches', { signal: controller.signal }).then(setResearches)
      .catch(() => { if (!controller.signal.aborted) setError('读取历史研究失败'); });
    return () => controller.abort();
  }, [open]);
  useEffect(() => {
    setRuns([]); setRunId(''); setRun(null);
    if (!researchId || !open) return;
    const controller = new AbortController();
    void api<{ runs: RunSummary[] }>(`/researches/${researchId}`, { signal: controller.signal })
      .then(data => { setRuns(data.runs); setRunId(data.runs[0]?.id || ''); })
      .catch(() => { if (!controller.signal.aborted) setError('读取版本失败'); });
    return () => controller.abort();
  }, [researchId, open]);
  useEffect(() => {
    setRun(null);
    if (!runId || !open) return;
    const controller = new AbortController();
    void api<Run>(`/runs/${runId}`, { signal: controller.signal }).then(setRun)
      .catch(() => { if (!controller.signal.aborted) setError('读取执行失败'); });
    return () => controller.abort();
  }, [runId, open]);
  return <details onToggle={e => setOpen(e.currentTarget.open)}><summary>全部历史研究与版本</summary>
    <label>研究主题<select value={researchId} onChange={e => setResearchId(e.target.value)}>
      <option value="">选择主题</option>{researches.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}
    </select></label><label>执行版本<select value={runId} onChange={e => setRunId(e.target.value)}>
      <option value="">选择执行</option>{runs.map(item => <option key={item.id} value={item.id}>
        {new Date(item.as_of).toLocaleString()} · {statusLabels[item.status] || item.status}
      </option>)}
    </select></label>{error && <p role="alert">{error}</p>}{run && <RunView run={run} />}
  </details>;
}
