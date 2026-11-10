import { date, label, type Reference, type Report } from "./api";

// 正式结果只来自校验后的结果接口；支持与反证始终分开列出。
export default function ReportView({
  report,
  openEvidence,
}: {
  report: Report;
  openEvidence: (id: string) => void;
}) {
  const result = report.result;
  function references(title: string, refs: Reference[]) {
    return (
      <div className="reference-list">
        <strong>{title}</strong>
        {refs.length ? (
          refs.map((ref, index) => (
            <button
              key={`${ref.evidence_id}-${index}`}
              onClick={() => openEvidence(ref.evidence_id)}
            >
              {ref.locator} · {ref.evidence_id.slice(0, 8)}
            </button>
          ))
        ) : (
          <span className="muted">未提供</span>
        )}
      </div>
    );
  }
  return (
    <div className="report">
      <p className="result-label">
        正式结果 · v{report.version} · {label(result.conclusion)}
      </p>
      <h3>{result.summary}</h3>
      <p className="muted">
        适用时间：{date(result.valid_from)} — {date(result.valid_until)}
      </p>
      <p>成立条件：{result.conditions}</p>
      <p>失效条件：{result.invalidation}</p>
      {result.gaps.length > 0 && (
        <p className="notice">资料缺口：{result.gaps.join("；")}</p>
      )}
      <h3>判断与证据</h3>
      {result.hops.map((hop) => (
        <article className="hop" key={hop.id}>
          <h4>
            {hop.id} · {hop.question}
          </h4>
          <p>{hop.finding}</p>
          {references("支持", hop.supports)}
          {references("反证", hop.counters)}
          <details>
            <summary>查看推导、替代解释与缺口</summary>
            <p>
              前驱判断：{hop.parents.join("、") || "起点"}；触发：{hop.trigger}
            </p>
            <p>
              对象：{hop.entities.join("、")}；时间：{hop.time_scope}
            </p>
            <p>替代解释：{hop.alternatives.join("；") || "未提供"}</p>
            <p>资料缺口：{hop.gaps.join("；") || "未记录"}</p>
            <p>成立条件：{hop.conditions}</p>
            <p>失效条件：{hop.invalidation}</p>
          </details>
        </article>
      ))}
      <h3>版本变化</h3>
      {result.revisions.length ? (
        result.revisions.map((revision) => (
          <p key={revision.hop_id}>
            {revision.hop_id} · {label(revision.change)} — {revision.reason}
          </p>
        ))
      ) : (
        <p className="muted">首次研究，没有前序判断对比。</p>
      )}
      <h3>计算产物</h3>
      {!result.artifacts.length && (
        <p className="muted">本结果没有通过校验的计算产物。</p>
      )}
      {result.artifacts.map((artifact) => (
        <article className="hop" key={artifact.evidence_id}>
          <p>
            价格 {artifact.price_unit} · 收益 {artifact.return_unit} · 复权{" "}
            {artifact.adjustment}
          </p>
          <p>
            收益口径 {artifact.return_basis}；费用 {artifact.fee_bps} bps ·{" "}
            {artifact.fee_basis}
          </p>
          <div className="reference-list">
            <button onClick={() => openEvidence(artifact.evidence_id)}>
              查看计算结果
            </button>
            <button onClick={() => openEvidence(artifact.execution_id)}>
              查看代码与执行
            </button>
            {artifact.inputs.map((id, i) => (
              <button key={id} onClick={() => openEvidence(id)}>
                输入快照 {i + 1}
              </button>
            ))}
            <button onClick={() => openEvidence(artifact.calendar_id)}>
              交易日历
            </button>
            {artifact.adjustment_factor_id && (
              <button
                onClick={() => openEvidence(artifact.adjustment_factor_id!)}
              >
                复权因子
              </button>
            )}
          </div>
        </article>
      ))}
      <details>
        <summary>结果标识与完整口径</summary>
        <pre>{JSON.stringify(report, null, 2)}</pre>
      </details>
    </div>
  );
}
