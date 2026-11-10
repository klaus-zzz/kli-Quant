import { useEffect, useRef, useState, type CSSProperties } from "react";
import { request, type Access } from "./api";
import Icon from "./Icon";

type Thinking = {
  control: string;
  levels: string[];
  recommended_effort: string | null;
  current_effort: string | null;
};
const names: Record<string, string> = {
  minimal: "最少",
  low: "低",
  medium: "中",
  high: "高",
  xhigh: "极高",
  max: "最大",
  on: "开启",
  off: "关闭",
};
const title = (level?: string | null) =>
  level ? (names[level] ?? level) : "模型默认";

// 可选档位来自模型服务；连续拖动只更新位置，松手吸附后提交本轮消息设置。
export default function EffortControl({
  access,
  disabled,
  onChange,
}: {
  access: Access;
  disabled: boolean;
  onChange: (value: string) => void;
}) {
  const [info, setInfo] = useState<Thinking>();
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const [value, setValue] = useState(0);
  const [chosen, setChosen] = useState(false);
  const [snapping, setSnapping] = useState(false);
  const popover = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const range = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const controller = new AbortController();
    setError("");
    request<Thinking>(access, `/chat/sessions/${access.session}/thinking`, {
      signal: controller.signal,
    })
      .then((data) => {
        if (controller.signal.aborted) return;
        setInfo(data);
        const current = data.current_effort ?? data.recommended_effort;
        setValue(Math.max(0, data.levels.indexOf(current ?? "")));
        // 推荐值只用作滑杆起点，不能冒充上游已保存的当前选择。
        setChosen(
          data.current_effort !== null &&
            data.levels.includes(data.current_effort),
        );
      })
      .catch((err) => {
        if (!controller.signal.aborted) setError(err.message);
      });
    return () => controller.abort();
  }, [access.session, access.token, revision]);
  useEffect(() => {
    const close = () => popover.current?.hidePopover();
    addEventListener("resize", close);
    return () => removeEventListener("resize", close);
  }, []);
  const levels = info?.levels ?? [];
  const available = levels.length > 1 && info?.control !== "none";
  function snap(next = value) {
    const index = Math.round(next);
    setSnapping(true);
    setValue(index);
    setChosen(true);
    onChange(levels[index]);
  }
  return (
    <>
      <button
        type="button"
        ref={trigger}
        id="effort-trigger"
        className="effort-trigger"
        aria-label={
          error
            ? "重试读取思考档位"
            : `思考链：${chosen ? title(levels[Math.round(value)]) : "模型默认"}`
        }
        title={
          error ||
          (available ? "调整下一条消息的思考链" : "当前模型未提供可调档位")
        }
        disabled={disabled || (!available && !error)}
        popoverTarget={available ? "effort-popover" : undefined}
        onClick={() => {
          if (error) setRevision((n) => n + 1);
        }}
      >
        <Icon name="sliders" />
        思考 ·{" "}
        {error
          ? "重试"
          : !info
            ? "读取中"
            : chosen
              ? title(levels[Math.round(value)])
              : "模型默认"}
        {available && <Icon name="chevronDown" />}
      </button>
      <div
        ref={popover}
        id="effort-popover"
        className="effort-popover"
        popover="auto"
        aria-label="思考链设置"
        onBeforeToggle={(event) => {
          if (event.newState !== "open" || !trigger.current || !popover.current)
            return;
          const box = trigger.current.getBoundingClientRect();
          const width = Math.min(264, innerWidth - 32);
          popover.current.style.left = `${Math.max(16, Math.min(innerWidth - width - 16, box.right - width))}px`;
          popover.current.style.bottom = `${innerHeight - box.top + 10}px`;
        }}
        onToggle={(event) => {
          if (event.newState === "open") range.current?.focus();
        }}
      >
        <div className="effort-heading">
          <div>
            <output htmlFor="effort-range">
              {chosen ? title(levels[Math.round(value)]) : "默认"}
            </output>
            <span>思考链</span>
          </div>
        </div>
        <div
          className={`effort-slider ${snapping ? "is-snapping" : ""}`}
          style={
            {
              "--effort-progress": value / Math.max(1, levels.length - 1),
            } as CSSProperties
          }
        >
          <div className="effort-track" aria-hidden="true">
            <span id="effort-fill" />
          </div>
          <div className="effort-ticks" aria-hidden="true">
            {levels.map((level) => (
              <i key={level} />
            ))}
          </div>
          <span className="effort-thumb" aria-hidden="true" />
          <input
            ref={range}
            id="effort-range"
            type="range"
            min="0"
            max={Math.max(1, levels.length - 1)}
            step="any"
            value={value}
            aria-label="思考链"
            aria-valuetext={title(levels[Math.round(value)])}
            onPointerDown={() => setSnapping(false)}
            onChange={(event) => {
              setValue(Number(event.target.value));
              setChosen(true);
            }}
            onPointerUp={(event) => snap(Number(event.currentTarget.value))}
            onPointerCancel={() => snap()}
            onBlur={() => {
              if (chosen) snap();
            }}
            onKeyDown={(event) => {
              const targets: Record<string, number> = {
                ArrowLeft: value - 1,
                ArrowDown: value - 1,
                ArrowRight: value + 1,
                ArrowUp: value + 1,
                Home: 0,
                End: levels.length - 1,
              };
              if (event.key in targets) {
                event.preventDefault();
                snap(
                  Math.max(0, Math.min(levels.length - 1, targets[event.key])),
                );
              }
            }}
          />
        </div>
      </div>
    </>
  );
}
