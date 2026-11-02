import type { Run, SavedRecord } from './api';
import { statusLabels } from './api';

const kindLabels: Record<string, string> = {
  document: '原始材料', evidence: '原文证据', snapshot: '固定数据快照',
  execution: '代码执行', artifact: '归档产物', judgment: '研究结论',
  review: '待复核判断', code: '执行代码', input: '用户输入', file: '工作文件版本',
  environment: '沙箱环境', agent_state: 'Agent 过程归档',
};
const outcomes: Record<string, string> = {
  insufficient_evidence: '证据不足', completed: '任务完成',
};

function RecordView({ row, runId, resultBase }: { row: SavedRecord; runId: string; resultBase?: string }) {
  const data = row.data;
  const source = typeof data.source_url === 'string' ? data.source_url : '';
  // 原文和沙箱结果均按纯文本显示；不渲染来源 HTML。
  return <article className="saved-record" id={`record-${row.id}`}>
    <h3>{kindLabels[row.kind] || row.kind} <small>{row.id.slice(0, 8)}</small></h3>
    {row.kind === 'judgment' && <>
      <strong>{String(data.outcome_label || outcomes[String(data.outcome)] || data.outcome)}</strong>
      <p>{String(data.conclusion)}</p>
      <p>判断类型：{data.fact_type === 'conditional_inference' ? '条件性推断' : '研究结论'}</p>
      <p>发布时间：{String(data.published_at)}</p>
      {Array.isArray(data.conditions) && <ul>{data.conditions.map((item, i) =>
        <li key={i}>{String(item)}</li>)}</ul>}
      {(['support', 'contradict'] as const).map(role => <p key={role}>
        {role === 'support' ? '支持证据：' : '反证：'}
        {Array.isArray(data[role]) && data[role].length > 0
          ? data[role].map(id => <a key={String(id)} href={`#record-${id}`}>{String(id).slice(0, 8)} </a>)
          : '未取得（不代表不存在）'}
      </p>)}
    </>}
    {row.kind === 'evidence' && <>
      <blockquote>{String(data.excerpt)}</blockquote>
      <p>原文位置：{String(data.locator)} · 公开时间：{String(data.published_at || '未知')}</p>
      <p>首次获取：{String(data.first_seen_at)} · 查证方向：{String(data.search_stance)}</p>
    </>}
    {row.kind === 'artifact' && <p>用途：{String(data.purpose)} · 校验：{String(data.validation)}</p>}
    {Array.isArray(data.limitations) && <ul className="limitations">{data.limitations.map((item, i) =>
      <li key={i}>{String(item)}</li>)}</ul>}
    {source.startsWith('http') && <a href={source} target="_blank" rel="noreferrer">查看来源网页</a>}
    {row.kind === 'evidence' && <a href={resultBase ? `${resultBase}/${String(data.document_id)}` : `/api/runs/${runId}/records/${String(data.document_id)}/content`}>
      下载固定版本原文</a>}
    {!!data.object && <a href={resultBase ? `${resultBase}/${row.id}` : `/api/runs/${runId}/records/${row.id}/content`}> 下载归档文件</a>}
    <details><summary>引用、口径与审计详情</summary><pre>{JSON.stringify(data, null, 2)}</pre></details>
  </article>;
}

export default function RunView({ run, resultBase }: { run: Run; resultBase?: string }) {
  const judgments = run.records.filter(row => row.kind === 'judgment');
  return <section aria-live="polite" aria-label="研究执行详情">
    <h2>{statusLabels[run.status] || run.status}</h2>
    <p>截止时点：{new Date(run.as_of).toLocaleString()} · 执行 {run.id.slice(0, 8)}</p>
    {run.stop_reason && <p>停止原因：{run.stop_reason}</p>}
    {run.cleanup_pending && <p className="notice">沙箱尚待清理，Worker 会继续收尾。</p>}
    {judgments.length === 0 && <p>本轮尚无已保存结果，请查看执行状态和工具记录。</p>}
    {judgments.map(row => <RecordView key={row.id} row={row} runId={run.id} resultBase={resultBase} />)}
    <h3>工具进度</h3>
    {run.calls.length === 0 && <p>尚无工具调用；请确认独立 Worker 已启动。</p>}
    {run.calls.map(call => <details key={call.id}>
      <summary>{call.step + 1}. {call.name} · {call.status}</summary>
      <pre>{JSON.stringify(call.result, null, 2)}</pre>
    </details>)}
    <h3>证据与计算</h3>
    {run.records.filter(row => row.kind !== 'judgment').map(row =>
      <RecordView key={row.id} row={row} runId={run.id} resultBase={resultBase} />)}
  </section>;
}
