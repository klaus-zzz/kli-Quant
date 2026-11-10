import { useEffect, useRef, useState, type FormEvent } from "react";
import { label, request, runLink, type Access } from "./api";
import ResearchPanel from "./ResearchPanel";
import { useSession } from "./useSession";

// 地址只保存会话与研究标识，凭据不进入 URL 或浏览器持久存储。
export default function App() {
  const [hash, setHash] = useState(location.hash);
  const [token, setToken] = useState("");
  const [accessToken, setAccessToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [health, setHealth] = useState("正在检查后端…");
  const params = new URLSearchParams(hash.slice(1));
  const session =
    params.get("session") ?? localStorage.getItem("kli-quant-session") ?? "";
  useEffect(() => {
    const changed = () => setHash(location.hash);
    addEventListener("hashchange", changed);
    return () => removeEventListener("hashchange", changed);
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/health", {
      signal: AbortSignal.any([controller.signal, AbortSignal.timeout(5000)]),
    })
      .then(async (response) => {
        if (!response.ok || (await response.json())?.status !== "ok")
          throw new Error();
        if (!controller.signal.aborted) setHealth("后端进程正常");
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setHealth("后端暂不可用，请稍后刷新页面。");
      });
    return () => controller.abort();
  }, []);
  async function connect(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (session)
        await request(
          { token: token.trim(), session },
          `/chat/sessions/${session}`,
        );
      else {
        const data = await request<{ session_id: string }>(
          { token: token.trim(), session: "" },
          "/chat/sessions",
          { method: "POST" },
        );
        localStorage.setItem("kli-quant-session", data.session_id);
        location.hash = runLink(data.session_id);
      }
      setAccessToken(token.trim());
      setToken("");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main>
      <header className="app-header">
        <a
          className="brand"
          href={session ? runLink(session) : "#"}
          aria-label="kli-Quant 首页"
        >
          <svg width="26" height="26" viewBox="0 0 26 26" aria-hidden="true">
            <path
              d="M5 3v20M20 3 8 13l12 10M8 13h14"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            />
          </svg>
          kli-Quant
        </a>
        <span className="muted">事件研究 · 开发环境</span>
        {accessToken && (
          <button onClick={() => setAccessToken("")}>断开连接</button>
        )}
      </header>
      {!accessToken ? (
        <div className="connect-layout">
          <section className="connect-panel">
            <h1>对话与研究</h1>
            <p>从一个问题开始，沿着证据深入。</p>
            <p className="muted">
              可以直接聊天，也可以发送事件或原文链接。后台研究的进度、依据和版本会单独保留。
            </p>
            <form onSubmit={(event) => void connect(event)}>
              <label htmlFor="chat-token">开发聊天凭据</label>
              <input
                id="chat-token"
                type="password"
                autoComplete="off"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                required
              />
              <p className="muted">凭据仅保留在本页内存，刷新后需重新输入。</p>
              <button className="primary" disabled={busy || !token.trim()}>
                {busy ? "正在连接…" : session ? "恢复对话" : "开始对话"}
              </button>
            </form>
            {error && <p role="alert">{error}</p>}
            {session && (
              <p className="muted identifier">
                将恢复：{session}{" "}
                <button
                  onClick={() => {
                    localStorage.removeItem("kli-quant-session");
                    location.hash = "";
                    setHash("");
                  }}
                >
                  切换为新会话
                </button>
              </p>
            )}
            <p role="status" className="health">
              {health}
            </p>
          </section>
          <aside className="intro">
            <h2>每个判断，都有来处。</h2>
            <dl>
              <dt>持续对话</dt>
              <dd>研究在后台进行，你可以继续提问。</dd>
              <dt>固定证据</dt>
              <dd>原文、数据和计算记录可以逐项核对。</dd>
              <dt>版本复核</dt>
              <dd>新证据触发新研究，旧结论仍可查看。</dd>
            </dl>
          </aside>
        </div>
      ) : (
        <Workspace
          key={session}
          access={{ token: accessToken, session }}
          selected={params.get("run") ?? ""}
        />
      )}
    </main>
  );
}

// 会话组件按 session 重建，旧请求不能把回复写进新会话。
function Workspace({ access, selected }: { access: Access; selected: string }) {
  const { snapshot, error, updated, refresh } = useSession(access);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState("");
  const [pending, setPending] = useState<{
    message_id: string;
    text: string;
  }>();
  const [previous, setPrevious] = useState("");
  const [mobile, setMobile] = useState("chat");
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
    if (selected) setMobile("research");
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
    setSending(true);
    setSendError("");
    const message = pending ?? {
      message_id: crypto.randomUUID(),
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
  return (
    <div className="workspace" data-mobile={mobile}>
      <nav className="mobile-tabs" aria-label="工作区视图">
        <button
          aria-pressed={mobile === "chat"}
          onClick={() => setMobile("chat")}
        >
          对话
        </button>
        <button
          aria-pressed={mobile === "research"}
          onClick={() => setMobile("research")}
        >
          研究 · {snapshot?.research.length ?? 0}
        </button>
      </nav>
      <section className="chat-pane" aria-label="持续对话">
        <div className="section-heading">
          <h1>对话</h1>
          <button
            disabled={sending || !!pending}
            onClick={() => void newSession()}
          >
            新建会话
          </button>
        </div>
        <div className="connection" role="status">
          {error
            ? "状态更新中断"
            : !snapshot
              ? "正在恢复会话…"
              : snapshot.connected
                ? "对话服务已连接"
                : "Agent 连接中断"}
          {updated && <span className="muted"> · 最后更新 {updated}</span>}
          <button onClick={refresh}>刷新状态</button>
        </div>
        {error && (
          <p role="alert">
            {error} 当前显示最后一次查询的内容，后台研究状态可能已变化。
          </p>
        )}
        {snapshot && !snapshot.connected && (
          <p className="notice">仍可查询归档；连接恢复前暂不能发送消息。</p>
        )}
        <div
          className="messages"
          aria-label="消息记录"
          ref={messages}
          onScroll={(event) => {
            const element = event.currentTarget;
            followReplies.current =
              element.scrollHeight - element.scrollTop - element.clientHeight <
              80;
          }}
        >
          {!snapshot?.deliveries.length && (
            <div className="empty-chat">
              <h2>你想核对什么？</h2>
              <p>发送一个问题、事件或原文链接。</p>
              <p className="muted">需要深入查证时，Agent 会启动后台研究。</p>
            </div>
          )}
          {snapshot?.deliveries.map((delivery) => (
            <article className="turn" key={delivery.id}>
              {delivery.question && (
                <div className="user-message">
                  <span className="speaker">你</span>
                  <p>{delivery.question}</p>
                </div>
              )}
              <div className="agent-message">
                <span className="speaker">
                  {delivery.kind === "notification" ? "研究完成回复" : "Agent"}
                </span>
                <p>{delivery.answer || label(delivery.state)}</p>
                <small>
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
        <form className="composer" onSubmit={(event) => void send(event)}>
          {previous && (
            <p>
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
          <label htmlFor="message">
            {previous ? "新证据或原文链接" : "消息"}
          </label>
          <textarea
            id="message"
            ref={input}
            rows={3}
            maxLength={previous ? 11500 : 12000}
            value={text}
            readOnly={sending || !!pending}
            onChange={(e) => setText(e.target.value)}
            placeholder="输入问题、事件或原文链接…"
            required
          />
          <div className="composer-actions">
            <span className="muted">研究期间可以继续聊天</span>
            <button
              className="primary"
              disabled={sending || !snapshot?.connected || !text.trim()}
            >
              {sending ? "正在发送…" : pending ? "重试同一消息" : "发送消息"}
            </button>
          </div>
          {sendError && (
            <p role="alert">
              {sendError} {pending && "尚未确认送达；重试会沿用同一消息标识。"}
            </p>
          )}
        </form>
      </section>
      <aside className="research-pane" aria-label="后台研究">
        {run ? (
          <ResearchPanel
            key={run.run_id}
            access={access}
            run={run}
            refresh={refresh}
            supplement={(id) => {
              setPrevious(id);
              setMobile("chat");
              input.current?.focus();
            }}
          />
        ) : (
          <>
            <div className="section-heading">
              <h2>研究记录</h2>
              <span className="muted">{snapshot?.research.length ?? 0} 项</span>
            </div>
            {selected && snapshot && (
              <p role="alert">
                该研究不在当前会话中。
                <a href={runLink(access.session)}>返回列表</a>
              </p>
            )}
            {!snapshot?.research.length && (
              <div className="empty-research">
                <h3>证据从这里展开</h3>
                <p>启动研究后，这里会显示真实进度、判断依据和固定结果。</p>
                <p className="muted">当前还没有研究记录。</p>
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
                    {label(item.status)} · {label(item.stage)}
                  </span>
                  <h3>{item.question}</h3>
                  <span className="muted">
                    {item.previous_run_id ? "补充复核" : "首次研究"} ·{" "}
                    {item.used_calls} / {item.max_calls} 次调用
                  </span>
                  {item.error && <p className="notice">{label(item.error)}</p>}
                </a>
              ))}
          </>
        )}
      </aside>
    </div>
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
