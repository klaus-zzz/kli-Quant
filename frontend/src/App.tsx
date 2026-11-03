import { useEffect, useState } from "react";

export default function App() {
  const [status, setStatus] = useState("正在检查后端…");

  // 只依据真实响应展示状态，卸载时取消请求；超时不能误报为正常。
  useEffect(() => {
    const controller = new AbortController();
    async function checkHealth() {
      try {
        const response = await fetch("/api/health", {
          signal: AbortSignal.any([
            controller.signal,
            AbortSignal.timeout(5000),
          ]),
        });
        if (!response.ok) throw new Error("健康接口请求失败");
        const data: unknown = await response.json();
        if (
          typeof data !== "object" ||
          data === null ||
          !("status" in data) ||
          data.status !== "ok"
        ) {
          throw new Error("健康接口响应无效");
        }
        if (!controller.signal.aborted) setStatus("后端进程正常");
      } catch {
        if (!controller.signal.aborted)
          setStatus("后端暂不可用，请稍后刷新页面。");
      }
    }
    void checkHealth();
    return () => controller.abort();
  }, []);

  return (
    <main>
      <p className="project-name">kli-Quant</p>
      <h1>开发骨架</h1>
      <p role="status">{status}</p>
      <p className="scope">
        当前仅验证前后端连通。金融数据与对话能力尚未接入。
      </p>
    </main>
  );
}
