import { useEffect, useRef, useState, type FormEvent } from "react";
import { label, request, runLink, type Access } from "./api";
import ResearchPanel from "./ResearchPanel";
import { useSession } from "./useSession";
import WorkspaceShell from "./WorkspaceShell";
import EffortControl from "./EffortControl";
import Icon from "./Icon";

// 会话组件按 session 重建，旧请求不能把回复写进新会话。
export default function Workspace({
  access,
  selected,
  disconnect,
}: {
  access: Access;
  selected: string;
  disconnect: () => void;
}) {
  const { snapshot, error, updated, refresh } = useSession(access);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState("");
  const [pending, setPending] = useState<{
    message_id: string;
    text: string;
    effort?: string;
  }>();
  const [previous, setPrevious] = useState("");
  const [panelOpen, setPanelOpen] = useState(!!selected);
  const [effort, setEffort] = useState<string>();
  const input = useRef<HTMLTextAreaElement>(null);
  const messages = useRef<HTMLDivElement>(null);
  const followReplies = useRef(true);
  // 只在用户停留底部时跟随回复，翻阅历史时保留阅读位置。
  useEffect(() => {
    if (messages.current && followReplies.current) {
      messages.current.scrollTop = messages.current.scrollHeight;
    }
  }, [snapshot?.deliveries]);
  const run = snapshot?.research.find((item) => item.run_id === selected);
  useEffect(() => {
    if (selected) setPanelOpen(true);
  }, [selected]);
  useEffect(() => {
    if (
      pending &&
      snapshot?.deliveries.some((item) => item.id === pending.message_id)
    ) {
      setPending(undefined);
      setText("");
      setPrevious("");
      setSendError("");
    }
  }, [snapshot, pending]);
  async function send(event: FormEvent) {
    event.preventDefault();
    if (sending || !snapshot?.connected || !text.trim()) return;
    setSending(true);
    setSendError("");
    const message = pending ?? {
      message_id: crypto.randomUUID(),
      ...(effort ? { effort } : {}),
      text: previous
        ? `请基于研究 ${previous} 补充以下证据，创建 previous_run_id 为 ${previous} 的新研究并比较判断变化：\n${text.trim()}`
        : text.trim(),
    };
    setPending(message);
    try {
      await request(access, `/chat/sessions/${access.session}/messages`, {
        method: "POST",
        body: JSON.stringify(message),
      });
      setPending(undefined);
      setText("");
      setPrevious("");
      refresh();
    } catch (err) {
      setSendError((err as Error).message);
    } finally {
      setSending(false);
    }
  }
  async function newSession() {
    setSending(true);
    setSendError("");
    try {
      const data = await request<{ session_id: string }>(
        access,
        "/chat/sessions",
        { method: "POST" },
      );
      localStorage.setItem("kli-quant-session", data.session_id);
      location.hash = runLink(data.session_id);
    } catch (err) {
      setSendError((err as Error).message);
    } finally {
      setSending(false);
    }
  }
  const status = error
    ? "状态更新中断"
    : !snapshot
      ? "正在恢复会话…"
      : snapshot.connected
        ? "对话服务已连接"
        : "Agent 连接中断";
  return (
    <WorkspaceShell
      access={access}
      panelOpen={panelOpen}
      setPanelOpen={setPanelOpen}
      newSession={() => void newSession()}
      busy={sending || !!pending}
      disconnect={disconnect}
      revision={snapshot?.deliveries.length ?? 0}
      panel={
        <>
          {run ? (
            <ResearchPanel
              key={run.run_id}
              access={access}
              run={run}
              refresh={refresh}
              supplement={(id) => {
                setPrevious(id);
                setPanelOpen(false);
                // 窄屏关闭详情后先解除输入区 inert，再把焦点交还给编辑框。
                requestAnimationFrame(() => input.current?.focus());
              }}
            />
          ) : (
            <>
              {selected && snapshot && (
                <p role="alert">
                  该研究不在当前会话中。
                  <a href={runLink(access.session)}>返回列表</a>
                </p>
              )}
              {!snapshot?.research.length && !snapshot?.tasks?.length && (
                <div className="empty-panel">
                  <Icon name="layers" />
                  <h3>任务在这里展开</h3>
                  <p>开始任务后，可以查看进度、资料和产物。</p>
                </div>
              )}
              {snapshot?.research
                .slice()
                .reverse()
                .map((item) => (
                  <a
                    className="run-row"
                    href={runLink(access.session, item.run_id)}
                    key={item.run_id}
                  >
                    <span className="run-state">
                      深度研究 · {label(item.status)} · {label(item.stage)}
                    </span>
                    <h3>{item.question}</h3>
                    <span className="muted">
                      {item.previous_run_id ? "补充复核" : "首次研究"} ·{" "}
                      {item.used_calls} / {item.max_calls} 次调用
                    </span>
                    {item.error && (
                      <p className="notice">{label(item.error)}</p>
                    )}
                  </a>
                ))}
              {snapshot?.tasks
                ?.filter((task) => !task.run_id)
                .map((task) => (
                  <article className="run-row" key={task.task_id}>
                    <span className="run-state">
                      {task.status === "running"
                        ? "执行中"
                        : label(task.status)}
                    </span>
                    <h3>{task.brief || task.name}</h3>
                    {task.result && (
                      <p className="task-output">{task.result}</p>
                    )}
                    {task.error && <p className="notice">{task.error}</p>}
                  </article>
                ))}
            </>
          )}
        </>
      }
    >
      <section className="conversation" aria-label="持续对话">
        {error && (
          <p className="connection-notice" role="alert">
            {error} 当前显示最后一次查询的内容，后台任务状态可能已变化。
          </p>
        )}
        {snapshot && !snapshot.connected && (
          <p className="connection-notice">
            仍可查询归档；连接恢复前暂不能发送消息。
          </p>
        )}
        <div
          className="conversation-scroll messages"
          aria-label="消息记录"
          ref={messages}
          onScroll={(event) => {
            const element = event.currentTarget;
            followReplies.current =
              element.scrollHeight - element.scrollTop - element.clientHeight <
              80;
          }}
        >
          <div className="thread">
            {!snapshot?.deliveries.length && (
              <div className="empty-home">
                <Icon name="brand" />
                <h1>今天，想完成什么？</h1>
                <div className="prompt-list">
                  {(
                    [
                      ["file", "把会议记录整理成行动清单"],
                      ["code", "帮我读懂这个接口的调用流程"],
                      ["globe", "美联储降息如何传导至 A 股？"],
                    ] as const
                  ).map(([icon, prompt]) => (
                    <button
                      key={prompt}
                      disabled={sending || !!pending}
                      onClick={() => {
                        setText(prompt);
                        input.current?.focus();
                      }}
                    >
                      <Icon name={icon} />
                      {prompt}
                      <Icon name="arrowUpRight" />
                    </button>
                  ))}
                </div>
              </div>
            )}
            {snapshot?.deliveries.map((delivery) => (
              <article className="turn" key={delivery.id}>
                {delivery.question && (
                  <div className="user-message">
                    <span className="sr-only">你</span>
                    <p>{delivery.question}</p>
                  </div>
                )}
                <div className="agent-message">
                  <div className="agent-label">
                    <Icon name="brand" />
                    <span>
                      {delivery.kind === "notification" ? "任务通知" : "Agent"}
                    </span>
                  </div>
                  <p>{delivery.answer || label(delivery.state)}</p>
                  <small className="muted">
                    {label(delivery.state)}
                    {delivery.state === "uncertain"
                      ? " · 未确认完整送达，不会自动重发；可核对上游历史。"
                      : ""}
                  </small>
                  {delivery.state === "uncertain" && (
                    <HistoryCheck access={access} />
                  )}
                </div>
              </article>
            ))}
          </div>
        </div>
        <footer className="composer-area">
          <form className="composer" onSubmit={(event) => void send(event)}>
            {previous && (
              <p className="linked-run">
                补充到研究 {previous.slice(0, 8)}{" "}
                <button
                  type="button"
                  disabled={!!pending}
                  onClick={() => setPrevious("")}
                >
                  取消关联
                </button>
              </p>
            )}
            <label className="sr-only" htmlFor="message">
              {previous ? "新证据或原文链接" : "消息"}
            </label>
            <textarea
              id="message"
              ref={input}
              rows={2}
              maxLength={previous ? 11500 : 12000}
              value={text}
              readOnly={sending || !!pending}
              onChange={(e) => setText(e.target.value)}
              placeholder="描述你想完成的事…"
              required
              onKeyDown={(event) => {
                if (
                  event.key === "Enter" &&
                  !event.shiftKey &&
                  !event.nativeEvent.isComposing
                ) {
                  event.preventDefault();
                  event.currentTarget.form?.requestSubmit();
                }
              }}
            />
            <div className="composer-toolbar">
              <button
                type="button"
                className="icon-button"
                aria-label="补充资料链接"
                disabled={sending || !!pending}
                onClick={() => {
                  setText(
                    (current) => `${current}${current ? "\n" : ""}参考链接：`,
                  );
                  input.current?.focus();
                }}
              >
                <Icon name="plus" />
              </button>
              <EffortControl
                access={access}
                disabled={sending || !!pending}
                onChange={setEffort}
              />
              <span className="composer-hint">Enter 发送</span>
              <button
                className={`send ${pending ? "retry-send" : ""}`}
                aria-label={
                  sending ? "正在发送…" : pending ? "重试同一消息" : "发送消息"
                }
                disabled={sending || !snapshot?.connected || !text.trim()}
              >
                {pending && !sending ? "重试" : <Icon name="arrowUp" />}
              </button>
            </div>
            {sendError && (
              <p role="alert">
                {sendError}{" "}
                {pending && "尚未确认送达；重试会沿用同一消息标识。"}
              </p>
            )}
          </form>
          <div className="connection" role="status">
            <span title={updated ? `最后更新 ${updated}` : undefined}>
              {status}
            </span>
            <button onClick={refresh}>刷新状态</button>
          </div>
        </footer>
      </section>
    </WorkspaceShell>
  );
}
// 不把无终态确认的回复伪装为完成，历史仅供人工核对。
function HistoryCheck({ access }: { access: Access }) {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  async function load() {
    setBusy(true);
    try {
      const data = await request<{ history: unknown }>(
        access,
        `/chat/sessions/${access.session}/history`,
      );
      setValue(JSON.stringify(data.history, null, 2));
    } catch (err) {
      setValue((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div>
      <button disabled={busy} onClick={() => void load()}>
        {busy ? "正在读取历史…" : "核对上游历史"}
      </button>
      {value && <pre>{value}</pre>}
    </div>
  );
}
