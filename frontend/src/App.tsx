import { useEffect, useRef, useState } from 'react';
import { api } from './api';
import type { Conversation } from './api';
import ResearchCard from './ResearchCard';
import LegacyResearch from './LegacyResearch';
import RemoteResearchCard from './RemoteResearchCard';
import { useGateway } from './gateway';

export default function App() {
  const [list, setList] = useState<{ id: string; title: string }[]>([]);
  const [id, setId] = useState(() => localStorage.getItem('kli-conversation') || '');
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const pending = useRef<{ id: string; content: string; request_id: string } | null>(null);
  const currentId = useRef(id);
  currentId.current = id;

  useEffect(() => {
    const controller = new AbortController();
    void api<{ id: string; title: string }[]>('/conversations', { signal: controller.signal })
      .then(setList).catch(() => {
        if (!controller.signal.aborted) setError('无法读取会话，请检查数据库迁移和 Agent 服务');
      });
    return () => controller.abort();
  }, []);

  const gateway = useGateway(id, detail => {
    setConversation(detail);
    setList(previous => [{ id: detail.id, title: detail.title }, ...previous.filter(item => item.id !== detail.id)]);
  });
  useEffect(() => {
    setConversation(null);
    localStorage.setItem('kli-conversation', id);
  }, [id]);

  async function newConversation() {
    setBusy(true); setError('');
    try {
      const created = await api<{ id: string }>('/conversations', { method: 'POST' });
      setId(created.id); setDraft(''); pending.current = null;
    } catch (err) { setError(err instanceof Error ? err.message : '创建失败'); }
    finally { setBusy(false); }
  }

  async function send() {
    setBusy(true); setError('');
    const content = draft.trim();
    try {
      let target = id;
      if (!target) {
        target = (await api<{ id: string }>('/conversations', { method: 'POST' })).id;
        currentId.current = target; setId(target);
      }
      // 网络失败后原内容复用编号；已经提交的研究不会被重试重复创建。
      if (pending.current?.id !== target || pending.current.content !== content) {
        pending.current = { id: target, content, request_id: crypto.randomUUID() };
      }
      await gateway.command('message', target, pending.current.request_id, { content });
      if (currentId.current !== target) return;
      setDraft(''); pending.current = null;

    } catch (err) { setError(err instanceof Error ? err.message : '发送失败，可用原内容重试'); }
    finally { setBusy(false); }
  }

  const replying = conversation?.turns.some(turn => ['queued', 'running'].includes(turn.status));
  const timeline = [
    ...(conversation?.turns || []).map(turn => ({ key: turn.id, time: turn.created_at, turn, job: null })),
    ...(conversation?.jobs || []).map(job => ({ key: job.id, time: job.as_of, turn: null, job })),
  ].sort((a, b) => a.time.localeCompare(b.time));
  return <main>
    <header><a className="brand" href="/">kli<span>Quant</span></a><span>对话与研究</span></header>
    <section className="chat-intro"><h1>先聊问题，再深入研究。</h1>
      <p>可以讨论想法、解释概念，或让我查证新闻对 A 股的影响。研究在后台进行，你可以继续聊。</p></section>
    <div className="conversation-picker"><label htmlFor="conversation">会话</label>
      <select id="conversation" value={id} disabled={busy} onChange={e => { setId(e.target.value); setError(''); }}>
        <option value="">开始对话</option>{list.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}
        {id && !list.some(item => item.id === id) && <option value={id}>正在读取…</option>}
      </select><button disabled={busy} onClick={() => void newConversation()}>新对话</button>
    </div>
    <section className="conversation" aria-label="对话记录" aria-live="polite">
      {!timeline.length && <p>例如：“解释一下多跳研究”，或“请研究这条新闻可能影响哪些 A 股公司……”</p>}
      {timeline.map(item => item.job ? <ResearchCard key={item.key} job={item.job} conversationId={id} /> :
        item.turn && <article key={item.key} className="chat-turn">
          {item.turn.kind !== 'task_completion' && <p className="message user-message"><strong>你</strong><span className="message-text">{item.turn.content}</span></p>}
          {item.turn.kind === 'task_completion' && <small>研究完成 · Agent 主动回复</small>}
          <p className="message"><strong>Agent</strong><span className="message-text">{item.turn.response ||
            (['queued', 'running'].includes(item.turn.status) ? '正在回复…' : `本轮未完成：${item.turn.error || '未知错误'}`)}</span></p>
          {!!item.turn.calls.length && <details><summary>本轮工具调用</summary><pre>{JSON.stringify(item.turn.calls, null, 2)}</pre></details>}
        </article>)}
      {conversation?.tasks.map(task => <RemoteResearchCard key={task.id} task={task} conversationId={id}
        cancel={taskId => gateway.command('cancel', id, crypto.randomUUID(), { task_id: taskId })} />)}
    </section>
    <p role="status">{gateway.connected ? '网关已连接' : '网关重连中；后台研究继续运行'}</p>
    {error && <p role="alert" className="notice">{error}</p>}
    <form onSubmit={e => { e.preventDefault(); void send(); }}>
      <label htmlFor="message">消息</label><textarea id="message" maxLength={6000} value={draft}
        disabled={busy} onChange={e => setDraft(e.target.value)} placeholder="输入问题、事件或原文链接…" />
      <div className="actions"><button disabled={busy || replying || !gateway.connected || !draft.trim()}>{busy || replying ? '正在回复…' : '发送'}</button>
        <small>后台研究不会锁住聊天。对话带入最近最多 10 轮，完整记录保留。</small></div>
    </form>
    <LegacyResearch />
    <footer>kli-Quant · Fina-Agent 驱动 · 本机单用户开发环境</footer>
  </main>;
}
