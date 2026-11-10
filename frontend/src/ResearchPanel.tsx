import { useEffect, useState } from "react";
import {
  date,
  label,
  request,
  runLink,
  type Access,
  type Evidence,
  type Report,
  type Run,
} from "./api";
import EvidenceView from "./EvidenceView";
import ReportView from "./ReportView";

// 详情固定绑定 run_id；新研究出现时不替换用户正在查看的旧结果。
export default function ResearchPanel({
  access,
  run,
  refresh,
  supplement,
}: {
  access: Access;
  run: Run;
  refresh: () => void;
  supplement: (run: string) => void;
}) {
  const [report, setReport] = useState<Report>();
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [selected, setSelected] = useState("");
  const [error, setError] = useState("");
  const [cancelError, setCancelError] = useState("");
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setError("");
    async function load() {
      try {
        const index = await request<{ evidence: Evidence[] }>(
          access,
          `/research/runs/${run.run_id}/evidence`,
          { signal: controller.signal },
        );
        if (!controller.signal.aborted) setEvidence(index.evidence);
        if (run.status === "completed") {
          const data = await request<Report>(
            access,
            `/research/runs/${run.run_id}/result`,
            { signal: controller.signal },
          );
          if (!controller.signal.aborted) setReport(data);
        }
      } catch (err) {
        if (!controller.signal.aborted) {
          setReport(undefined);
          setError((err as Error).message);
        }
      } finally {
        if (!controller.signal.aborted) setLoaded(true);
      }
    }
    void load();
    return () => controller.abort();
  }, [
    access.token,
    access.session,
    run.run_id,
    run.status,
    run.used_calls,
    revision,
  ]);

  async function cancel() {
    setBusy(true);
    setCancelError("");
    try {
      await request(access, `/research/runs/${run.run_id}/cancel`, {
        method: "POST",
      });
      refresh();
    } catch (err) {
      setCancelError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section aria-label="研究详情" className="research-detail">
      <div className="section-heading">
        <h2>研究详情</h2>
        <a href={runLink(access.session)}>返回研究列表</a>
      </div>
      <h3>
        {run.question.length > 96
          ? `${run.question.slice(0, 96)}…`
          : run.question}
      </h3>
      {run.question.length > 96 && (
        <details>
          <summary>完整研究问题</summary>
          <p>{run.question}</p>
        </details>
      )}
      <p>
        <strong>{label(run.status)}</strong> · {label(run.stage)}
      </p>
      <p className="muted">
        已使用 {run.used_calls} / {run.max_calls} 次调用 · 截止{" "}
        {date(run.deadline)}
      </p>
      <p className="identifier">执行 {run.run_id}</p>
      {run.previous_run_id && (
        <a href={runLink(access.session, run.previous_run_id)}>
          查看前序版本 →
        </a>
      )}
      {run.error && <p className="notice">{label(run.error)}</p>}
      <div className="actions">
        {["queued", "running"].includes(run.status) && (
          <button disabled={busy} onClick={() => void cancel()}>
            {busy ? "正在请求取消…" : "取消研究"}
          </button>
        )}
        {run.status === "completed" && (
          <button onClick={() => supplement(run.run_id)}>补充新证据</button>
        )}
        <button
          onClick={() => {
            refresh();
            setRevision(revision + 1);
          }}
        >
          重新查询研究
        </button>
      </div>
      {cancelError && (
        <p role="alert">{cancelError} 取消是否生效请重新查询。</p>
      )}
      {error && (
        <p role="alert">
          {error}{" "}
          <button onClick={() => setRevision(revision + 1)}>
            重试读取研究
          </button>
        </p>
      )}
      {!loaded && <p role="status">正在读取研究归档…</p>}
      {report && <ReportView report={report} openEvidence={setSelected} />}
      {!report && loaded && (
        <p className="notice">
          尚无通过校验的正式结果。对话中的分析和以下资料仅供探索。
        </p>
      )}
      <details className="archive" open={!report}>
        <summary>探索资料与固定归档（{evidence.length}）</summary>
        {!evidence.length && loaded && <p className="muted">尚未归档资料。</p>}
        {evidence.map((item) => (
          <button
            className="archive-row"
            key={item.evidence_id}
            onClick={() => setSelected(item.evidence_id)}
          >
            <span>{label(item.kind)}</span>
            <span className="identifier">{item.evidence_id.slice(0, 8)}</span>
          </button>
        ))}
      </details>
      {selected && (
        <EvidenceView
          access={access}
          run={run.run_id}
          id={selected}
          close={() => setSelected("")}
        />
      )}
    </section>
  );
}
