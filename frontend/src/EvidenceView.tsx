import { useEffect, useState } from "react";
import { label, request, safeUrl, type Access, type Evidence } from "./api";

// 按需读取固定资料；切换证据时取消旧请求，防止迟到响应覆盖当前选择。
export default function EvidenceView({
  access,
  run,
  id,
  close,
}: {
  access: Access;
  run: string;
  id: string;
  close: () => void;
}) {
  const [evidence, setEvidence] = useState<Evidence>();
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setEvidence(undefined);
    setError("");
    request<Evidence>(access, `/research/runs/${run}/evidence/${id}`, {
      signal: controller.signal,
    })
      .then((data) => {
        if (!controller.signal.aborted) setEvidence(data);
      })
      .catch((err) => {
        if (!controller.signal.aborted) setError(err.message);
      });
    return () => controller.abort();
  }, [access.token, access.session, run, id, retry]);
  const document = evidence?.document;
  // 探索代码可返回数组或标量，只有对象才读取来源及执行引用字段。
  const fields = (
    document && typeof document === "object" && !Array.isArray(document)
      ? document
      : {}
  ) as Record<string, unknown>;
  const source = safeUrl(fields.final_url ?? fields.url);
  return (
    <section className="evidence-view" aria-label="固定证据内容">
      <div className="section-heading">
        <h3>{evidence ? label(evidence.kind) : "读取证据"}</h3>
        <button onClick={close}>关闭证据</button>
      </div>
      {error && (
        <p role="alert">
          {error} <button onClick={() => setRetry(retry + 1)}>重试读取</button>
        </p>
      )}
      {!evidence && !error && <p role="status">正在校验并读取归档…</p>}
      {evidence && (
        <>
          <p className="identifier">{id}</p>
          {source && (
            <a href={source} target="_blank" rel="noopener noreferrer">
              打开原始来源 ↗
            </a>
          )}
          <details>
            <summary>归档摘要与时间信息</summary>
            <pre>
              {JSON.stringify(
                { sha256: evidence.sha256, ...evidence.metadata },
                null,
                2,
              )}
            </pre>
          </details>
          <pre className="document">{JSON.stringify(document, null, 2)}</pre>
          {evidence.kind === "execution" && (
            <div className="reference-list">
              {(["code_id", "output_id"] as const).map(
                (field) =>
                  typeof fields[field] === "string" && (
                    <EvidenceInline
                      key={field}
                      access={access}
                      run={run}
                      id={fields[field] as string}
                      title={
                        field === "code_id" ? "查看本次代码" : "查看本次输出"
                      }
                    />
                  ),
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}

// 执行记录中的代码和输出继续按同一研究身份读取。
function EvidenceInline({
  access,
  run,
  id,
  title,
}: {
  access: Access;
  run: string;
  id: string;
  title: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button onClick={() => setOpen(!open)}>{title}</button>
      {open && (
        <EvidenceView
          access={access}
          run={run}
          id={id}
          close={() => setOpen(false)}
        />
      )}
    </div>
  );
}
