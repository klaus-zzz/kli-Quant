import { useEffect, useState, type FormEvent } from "react";
import { request, runLink } from "./api";
import Workspace from "./Workspace";
import Icon from "./Icon";

// 地址与浏览器只记住会话标识，聊天凭据始终留在本页内存。
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
    const changed = () => {
      setHash(location.hash);
      const id = new URLSearchParams(location.hash.slice(1)).get("session");
      if (id) localStorage.setItem("kli-quant-session", id);
    };
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
  if (accessToken)
    return (
      <Workspace
        key={session}
        access={{ token: accessToken, session }}
        selected={params.get("run") ?? ""}
        disconnect={() => setAccessToken("")}
      />
    );
  return (
    <main className="connect-page">
      <a className="brand" href="#" aria-label="kli-Quant 首页">
        <Icon name="brand" />
        kli-Quant
      </a>
      <section className="connect-panel">
        <Icon name="brand" />
        <h1>今天，想完成什么？</h1>
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
          <button
            className="text-button"
            onClick={() => {
              localStorage.removeItem("kli-quant-session");
              location.hash = "";
              setHash("");
            }}
          >
            切换为新会话
          </button>
        )}
        <p role="status" className="health muted">
          {health}
        </p>
      </section>
    </main>
  );
}
