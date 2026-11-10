import { useCallback, useEffect, useState } from "react";
import { request, type Access, type Snapshot } from "./api";

// 串行轮询持久快照；整批替换消息，重连或重复通知不会追加同一份报告。
export function useSession(access: Access) {
  const [snapshot, setSnapshot] = useState<Snapshot>();
  const [error, setError] = useState("");
  const [updated, setUpdated] = useState("");
  const [revision, setRevision] = useState(0);
  const refresh = useCallback(() => setRevision((n) => n + 1), []);
  useEffect(() => {
    if (!access.session) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const data = await request<Snapshot>(
          access,
          `/chat/sessions/${access.session}`,
          { signal: controller.signal },
        );
        if (
          !Array.isArray(data.deliveries) ||
          !Array.isArray(data.research) ||
          typeof data.connected !== "boolean"
        ) {
          throw new Error("会话响应无效，请重试查询。");
        }
        if (!controller.signal.aborted) {
          setSnapshot(data);
          setUpdated(new Date().toLocaleTimeString("zh-CN", { hour12: false }));
          setError("");
        }
      } catch (err) {
        if (!controller.signal.aborted) setError((err as Error).message);
      }
      if (!controller.signal.aborted) timer = setTimeout(poll, 2000);
    }
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [access.session, access.token, revision]);
  return { snapshot, error, updated, refresh };
}
