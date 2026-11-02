import { useEffect, useState } from 'react';
import { api, statusLabels } from './api';
import type { Application, Research, Run, RunSummary } from './api';
import RunView from './RunView';

export default function App() {
  const [services, setServices] = useState<Record<string, boolean>>({});
  const [applications, setApplications] = useState<Application[]>([]);
  const [application, setApplication] = useState('assistant');
  const [researches, setResearches] = useState<Research[]>([]);
  const [researchId, setResearchId] = useState('');
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [runId, setRunId] = useState('');
  const [run, setRun] = useState<Run | null>(null);
  const [event, setEvent] = useState('');
  const [urls, setUrls] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    // 各依赖独立显示；配置齐全不冒充服务联通。
    const controller = new AbortController();
    void api<Application[]>('/applications', { signal: controller.signal }).then(data => {
      // 实例决定唯一应用，避免初始 assistant 状态误发给金融实例。
      setApplications(data);
      setApplication(data[0]?.id || '');
    })
      .catch(() => { if (!controller.signal.aborted) setError('无法读取已安装应用'); });
    void api<{ configured: Record<string, boolean> }>('/services', { signal: controller.signal })
      .then(data => setServices(data.configured)).catch(() => {
        if (!controller.signal.aborted) setError('无法读取服务配置状态');
      });
    void api<Research[]>('/researches', { signal: controller.signal }).then(setResearches)
      .catch(() => { if (!controller.signal.aborted) setError('无法读取研究列表，请检查数据库和迁移'); });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    // 切换主题时取消旧请求，避免迟到的响应覆盖当前历史列表。
    if (!researchId) return;
    const controller = new AbortController();
    void api<{ runs: RunSummary[] }>(`/researches/${researchId}`, { signal: controller.signal })
      .then(data => { setRuns(data.runs); setRunId(data.runs[0]?.id || ''); })
      .catch(() => { if (!controller.signal.aborted) setError('无法读取研究历史'); });
    return () => controller.abort();
  }, [researchId]);

  useEffect(() => {
    if (!runId) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    setRun(null);
    // 完成请求后再安排下一次刷新，慢网络不会累积重叠请求。
    const refresh = async () => {
      try {
        const current = await api<Run>(`/runs/${runId}`, { signal: controller.signal });
        if (controller.signal.aborted) return;
        setRun(current);
        setRuns(previous => previous.map(item => item.id === current.id ? current : item));
        if (['queued', 'running'].includes(current.status) || current.cleanup_pending) {
          timer = setTimeout(() => void refresh(), 2000);
        }
      } catch {
        if (!controller.signal.aborted) setError('进度读取失败，请重新选择执行刷新');
      }
    };
    void refresh();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [runId]);

  async function submit(review: boolean) {
    setBusy(true); setError('');
    try {
      const path = review ? `/researches/${researchId}/runs` : '/researches';
      const created = await api<{ research_id: string; run_id: string }>(path, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ request_id: crypto.randomUUID(), event,
          application: review ? run?.input.application || application : application,
          source_urls: urls.split('\n').map(value => value.trim()).filter(Boolean) }),
      });
      setResearchId(created.research_id); setRunId(created.run_id);
      setEvent(''); setUrls('');
      const [list, detail] = await Promise.all([
        api<Research[]>('/researches'),
        api<{ runs: RunSummary[] }>(`/researches/${created.research_id}`),
      ]);
      setResearches(list); setRuns(detail.runs);
    } catch (err) { setError(err instanceof Error ? err.message : '提交失败'); }
    finally { setBusy(false); }
  }

  async function cancel() {
    setBusy(true);
    try {
      await api(`/runs/${runId}/cancel`, { method: 'POST' });
      setRun(await api<Run>(`/runs/${runId}`));
    } catch { setError('取消失败，请稍后重试'); }
    finally { setBusy(false); }
  }

  const active = run && ['queued', 'running'].includes(run.status);
  const canSubmit = !busy && !!(event.trim() || urls.trim());
  return <main>
    <header><a className="brand" href="/">kli<span>Quant</span></a><span>金融研究工作台</span></header>
    <section className="intro"><p className="eyebrow">任务 → 工具 → 执行 → 检查 → 交付</p>
      <h1>让任务执行<br />有迹可循。</h1>
      <p>选择已安装的应用，查看真实工具调用、交付产物和历史版本。</p>
    </section>
    <section className="panel"><h2>服务配置</h2><dl>{Object.entries(services).map(([name, ready]) =>
      <div key={name}><dt>{name}</dt><dd>{ready ? '已配置（执行时验证）' : '尚未配置'}</dd></div>)}</dl></section>
    <form onSubmit={e => { e.preventDefault(); void submit(false); }}>
      <label htmlFor="application">应用</label>
      <select id="application" value={application} onChange={e => setApplication(e.target.value)}>
        {applications.map(item => <option key={item.id} value={item.id}>
          {item.label} · {item.version}{item.missing_services.length ? `（缺少 ${item.missing_services.join('、')}）` : ''}
        </option>)}
      </select>
      <label htmlFor="event">任务或待核实问题</label>
      <textarea id="event" value={event} maxLength={6000} onChange={e => setEvent(e.target.value)} />
      <label htmlFor="urls">原文链接（可选，每行一个，最多三个）</label>
      <textarea id="urls" value={urls} onChange={e => setUrls(e.target.value)} />
      <div className="actions"><button disabled={!canSubmit || !applications.length}>创建任务</button>
        <button type="button" disabled={!canSubmit || !researchId || !run || !!active}
          onClick={() => void submit(true)}>以新证据复核当前主题</button>
        {active && <button type="button" disabled={busy} onClick={() => void cancel()}>取消本轮</button>}
      </div>
    </form>
    {error && <p role="alert" className="notice">{error}</p>}
    <section className="history"><label>任务主题<select value={researchId}
      onChange={e => { setResearchId(e.target.value); setRunId(''); setRun(null); setRuns([]); }}>
      <option value="">选择主题</option>{researches.map(item =>
        <option key={item.id} value={item.id}>{item.title}</option>)}
    </select></label><label>执行版本<select value={runId} onChange={e => setRunId(e.target.value)}>
      <option value="">选择执行</option>{runs.map(item => <option key={item.id} value={item.id}>
        {new Date(item.as_of).toLocaleString()} · {statusLabels[item.status] || item.status}
      </option>)}
    </select></label></section>
    {run ? <RunView run={run} /> : <p>{runId ? '正在读取执行…' : '输入任务或链接开始执行。'}</p>}
    <footer>kli-Quant · Fina-Agent 驱动 · 本机单用户开发环境</footer>
  </main>;
}
