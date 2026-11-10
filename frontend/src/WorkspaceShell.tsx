import { useEffect, useRef, useState, type ReactNode } from "react";
import { date, request, runLink, type Access } from "./api";
import Icon from "./Icon";

type Session = { id: string; title: string; updated_at: string };
// 导航从服务端恢复；窄屏抽屉与对话区互斥，避免遮挡后仍可误操作背景。
export default function WorkspaceShell({
  access,
  children,
  panel,
  panelOpen,
  setPanelOpen,
  newSession,
  busy,
  disconnect,
  revision,
}: {
  access: Access;
  children: ReactNode;
  panel: ReactNode;
  panelOpen: boolean;
  setPanelOpen: (open: boolean) => void;
  newSession: () => void;
  busy: boolean;
  disconnect: () => void;
  revision: number;
}) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  const [query, setQuery] = useState("");
  const [navOpen, setNavOpen] = useState(false);
  const [compact, setCompact] = useState(
    matchMedia("(max-width: 1050px)").matches,
  );
  const search = useRef<HTMLDialogElement>(null);
  const sidebar = useRef<HTMLElement>(null);
  const detail = useRef<HTMLElement>(null);
  const menu = useRef<HTMLButtonElement>(null);
  const panelButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const controller = new AbortController();
    request<{ sessions: Session[] }>(access, "/chat/sessions", {
      signal: controller.signal,
    })
      .then((data) => {
        if (!controller.signal.aborted) {
          setSessions(data.sessions);
          setError("");
        }
      })
      .catch((err) => {
        if (!controller.signal.aborted) setError(err.message);
      });
    return () => controller.abort();
  }, [access.token, access.session, revision, reload]);
  useEffect(() => {
    const media = matchMedia("(max-width: 1050px)");
    const changed = () => {
      setCompact(media.matches);
      setNavOpen(false);
      setPanelOpen(false);
    };
    media.addEventListener("change", changed);
    return () => media.removeEventListener("change", changed);
  }, [setPanelOpen]);
  useEffect(() => {
    if (panelOpen) {
      setNavOpen(false);
      // 等抽屉解除 visibility/inert 后再接管焦点，保留开场动画。
      if (compact) {
        const frame = requestAnimationFrame(() =>
          detail.current?.querySelector<HTMLButtonElement>("button")?.focus(),
        );
        return () => cancelAnimationFrame(frame);
      }
    }
  }, [panelOpen, compact]);
  function closePanel() {
    setPanelOpen(false);
    panelButton.current?.focus();
  }
  function closeNav() {
    setNavOpen(false);
    menu.current?.focus();
  }
  const title =
    sessions.find((item) => item.id === access.session)?.title ?? "新建对话";
  function choose(id: string) {
    location.hash = runLink(id);
    setNavOpen(false);
    search.current?.close();
  }
  return (
    <div
      className={`app-shell ${panelOpen ? "panel-mobile-open" : "panel-closed"} ${navOpen ? "nav-open" : ""}`}
      onKeyDown={(event) => {
        if (search.current?.open || document.querySelector(":popover-open"))
          return;
        if (event.key === "Escape") {
          if (navOpen) closeNav();
          else if (panelOpen) closePanel();
        }
        if (event.key !== "Tab" || !compact || (!navOpen && !panelOpen)) return;
        const root = navOpen ? sidebar.current : detail.current;
        const toggle = navOpen ? menu.current : panelButton.current;
        const items = [
          toggle,
          ...Array.from(
            root?.querySelectorAll<HTMLElement>(
              "button:not(:disabled), a[href], input, summary",
            ) ?? [],
          ),
        ].filter(
          (item): item is HTMLElement =>
            !!item && item.getClientRects().length > 0,
        );
        const current = items.indexOf(document.activeElement as HTMLElement);
        if (
          (event.shiftKey && current <= 0) ||
          (!event.shiftKey && current === items.length - 1)
        ) {
          event.preventDefault();
          items[event.shiftKey ? items.length - 1 : 0]?.focus();
        }
      }}
    >
      <button
        className="nav-backdrop"
        aria-label="收起会话导航"
        tabIndex={-1}
        onClick={closeNav}
      />
      <button
        className="panel-backdrop"
        aria-label="收起任务详情"
        tabIndex={-1}
        onClick={closePanel}
      />
      <aside
        ref={sidebar}
        className="sidebar"
        id="session-nav"
        aria-label="会话导航"
        inert={compact && !navOpen}
      >
        <a className="brand" href={runLink(access.session)}>
          <Icon name="brand" />
          <span>kli-Quant</span>
        </a>
        <button
          className="new-chat"
          disabled={busy}
          onClick={() => {
            newSession();
            closeNav();
          }}
        >
          <Icon name="plus" />
          新建对话
        </button>
        <nav className="nav-links">
          <button
            onClick={() => {
              setQuery("");
              search.current?.showModal();
            }}
          >
            <Icon name="search" />
            搜索对话
          </button>
          <button
            onClick={() => {
              setNavOpen(false);
              setPanelOpen(true);
            }}
          >
            <Icon name="layers" />
            当前对话任务
          </button>
        </nav>
        <div className="sidebar-heading">最近对话</div>
        {error && (
          <p role="alert">
            {error}
            <button onClick={() => setReload((n) => n + 1)}>重试列表</button>
          </p>
        )}
        <div className="sessions">
          {sessions.map((item) => (
            <button
              className={`session ${item.id === access.session ? "active" : ""}`}
              key={item.id}
              aria-current={item.id === access.session ? "page" : undefined}
              onClick={() => choose(item.id)}
              disabled={busy}
            >
              <span className="session-title">{item.title}</span>
              <small>{date(item.updated_at)}</small>
            </button>
          ))}
        </div>
        <div className="sidebar-bottom">
          <div className="workspace-name">
            <span className="avatar">K</span>
            <div>
              开发工作空间<small>对话与任务</small>
            </div>
          </div>
          <button className="design-note" onClick={disconnect}>
            <Icon name="logout" />
            断开连接
          </button>
        </div>
      </aside>
      <main className="workspace">
        <header className="workspace-header">
          <button
            ref={menu}
            className="icon-button menu-button"
            aria-label="切换会话导航"
            aria-controls="session-nav"
            aria-expanded={navOpen}
            onClick={() => {
              if (navOpen) closeNav();
              else {
                setPanelOpen(false);
                setNavOpen(true);
                requestAnimationFrame(() =>
                  sidebar.current
                    ?.querySelector<HTMLButtonElement>(".new-chat")
                    ?.focus(),
                );
              }
            }}
          >
            <Icon name="panelLeft" />
          </button>
          <div className="breadcrumb">
            <span>工作空间</span>
            <span>/</span>
            <span title={title}>{title}</span>
          </div>
          <div className="header-actions">
            <button
              ref={panelButton}
              className="icon-button"
              aria-label="切换任务侧栏"
              aria-controls="task-panel"
              aria-expanded={panelOpen}
              onClick={() => (panelOpen ? closePanel() : setPanelOpen(true))}
            >
              <Icon name="panelRight" />
            </button>
          </div>
        </header>
        <div className="workspace-body">
          <div
            className="conversation-host"
            inert={compact && (navOpen || panelOpen)}
          >
            {children}
          </div>
          <aside
            ref={detail}
            className="research-panel"
            id="task-panel"
            aria-label="任务详情"
            inert={!panelOpen}
            onTransitionEnd={(event) => {
              if (
                event.target === event.currentTarget &&
                event.propertyName === "transform" &&
                compact &&
                panelOpen
              )
                detail.current
                  ?.querySelector<HTMLButtonElement>("button")
                  ?.focus();
            }}
          >
            <div className="panel-heading">
              <span>任务详情</span>
              <button
                className="icon-button"
                aria-label="关闭任务侧栏"
                onClick={closePanel}
              >
                <Icon name="close" />
              </button>
            </div>
            <div className="panel-content">{panel}</div>
          </aside>
        </div>
      </main>
      <dialog ref={search} aria-label="搜索对话">
        <div className="dialog-title">
          <h2>搜索对话</h2>
          <button
            className="icon-button"
            aria-label="关闭搜索"
            onClick={() => search.current?.close()}
          >
            <Icon name="close" />
          </button>
        </div>
        <label className="sr-only" htmlFor="search">
          对话关键词
        </label>
        <input
          id="search"
          placeholder="搜索对话标题…"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <div id="search-results">
          {sessions
            .filter((item) =>
              item.title.toLowerCase().includes(query.toLowerCase()),
            )
            .map((item) => (
              <button
                disabled={busy}
                key={item.id}
                onClick={() => choose(item.id)}
              >
                {item.title}
              </button>
            ))}
          {!sessions.some((item) =>
            item.title.toLowerCase().includes(query.toLowerCase()),
          ) && <p>没有匹配的对话</p>}
        </div>
      </dialog>
    </div>
  );
}
