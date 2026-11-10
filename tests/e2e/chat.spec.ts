import { expect, test, type Page } from "@playwright/test";
import type { Run } from "../../frontend/src/api";

const session = "kq-browser-test";
const first = "11111111-1111-4111-8111-111111111111";
const second = "22222222-2222-4222-8222-222222222222";
const evidence = "33333333-3333-4333-8333-333333333333";
const baseRun = {
  run_id: first,
  question: "事件影响是否有证据支持？",
  previous_run_id: null,
  status: "running",
  stage: "collecting",
  error: null,
  cutoff: "2026-11-10T00:00:00Z",
  deadline: "2026-11-10T00:05:00Z",
  used_calls: 2,
  max_calls: 30,
};
const report = {
  run_id: first,
  result_id: "fixed-result",
  version: 1,
  sha256: "fixed-hash",
  result: {
    conclusion: "insufficient_evidence",
    summary: "尚不足以建立因果关系",
    valid_from: "2026-11-10T00:00:00Z",
    valid_until: "2026-11-11T00:00:00Z",
    conditions: "取得原始披露",
    invalidation: "原始披露撤回",
    gaps: ["原文时间未知"],
    artifacts: [],
    revisions: [],
    hops: [
      {
        id: "demand",
        question: "需求是否改善？",
        finding: "仍需查证",
        parents: [],
        trigger: "事件",
        entities: ["公司"],
        time_scope: "当日",
        supports: [{ evidence_id: evidence, locator: "p:1" }],
        counters: [],
        gaps: ["发布时间未知"],
        alternatives: ["价格变化或由其他因素导致"],
        conditions: "来源可核验",
        invalidation: "数据撤回",
      },
    ],
  },
};

// 受控响应只验证浏览器状态处理；真实模型链路另在隔离环境验收。
async function setup(page: Page) {
  const state = {
    connected: true,
    offline: false,
    loseReply: false,
    cancelling: false,
    messages: [] as { message_id: string; text: string; effort?: string }[],
    deliveries: [] as {
      id: string;
      question: string;
      answer: string;
      state: string;
      kind: string;
    }[],
    runs: [{ ...baseRun }] as Run[],
    tasks: [] as {
      task_id: string;
      run_id: null;
      name: string;
      brief: string;
      status: string;
      result: string;
    }[],
  };
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/health") return route.continue();
    if (state.offline) return route.abort();
    if (path.endsWith("/messages")) {
      const message = route.request().postDataJSON();
      state.messages.push(message);
      if (state.loseReply) return route.abort();
      state.deliveries.push({
        id: message.message_id,
        question: message.text,
        answer: "普通聊天回复",
        state: "done",
        kind: "chat",
      });
      return route.fulfill({ status: 202, json: { type: "accepted" } });
    }
    if (path.endsWith("/cancel")) {
      state.runs[0].status = "cancelling";
      state.cancelling = true;
      return route.fulfill({ json: state.runs[0] });
    }
    if (path.endsWith(`/evidence/${evidence}`))
      return route.fulfill({
        json: {
          evidence_id: evidence,
          run_id: first,
          kind: "source",
          sha256: "hash",
          metadata: { published_at: null },
          document: {
            url: "javascript:alert(1)",
            blocks: [
              { locator: "p:1", text: "<script>window.injected=true</script>" },
            ],
          },
        },
      });
    if (path.endsWith("/evidence"))
      return route.fulfill({
        json: { evidence: [{ evidence_id: evidence, kind: "source" }] },
      });
    if (path.endsWith("/result"))
      return route.fulfill({
        json: path.includes(second)
          ? {
              ...report,
              run_id: second,
              result: {
                ...report.result,
                summary: "新证据仍不足",
                revisions: [
                  {
                    hop_id: "demand",
                    change: "maintained",
                    reason: "仍缺原始披露",
                  },
                ],
              },
            }
          : report,
      });
    if (path.endsWith("/thinking"))
      return route.fulfill({
        json: {
          control: "effort",
          levels: ["low", "medium", "high", "xhigh"],
          current_effort: "medium",
          recommended_effort: "medium",
        },
      });
    if (path === "/api/chat/sessions")
      return route.fulfill({
        status: 200,
        json:
          route.request().method() === "POST"
            ? { session_id: session }
            : {
                sessions: [
                  {
                    id: session,
                    title: "测试对话",
                    updated_at: "2026-11-10T00:00:00Z",
                  },
                  {
                    id: "kq-older",
                    title: "历史里的会议记录",
                    updated_at: "2026-11-09T00:00:00Z",
                  },
                ],
              },
      });
    return route.fulfill({
      json: {
        connected: state.connected,
        deliveries: state.deliveries,
        research: state.runs,
        tasks: state.tasks,
      },
    });
  });
  await page.goto("/");
  await page.getByLabel("开发聊天凭据").fill("browser-only-test-token");
  await page.getByRole("button", { name: "开始对话" }).click();
  await expect(
    page.getByText("对话服务已连接", { exact: false }),
  ).toBeVisible();
  await page.getByRole("button", { name: "切换任务侧栏" }).click();
  return state;
}

test("研究期间聊天、刷新恢复、重复快照不重复回复", async ({ page }) => {
  const state = await setup(page);
  await page
    .getByLabel("消息", { exact: true })
    .fill("研究继续，17+25 是多少？");
  await page.getByRole("button", { name: "发送消息" }).click();
  await expect(page.getByText("普通聊天回复", { exact: true })).toBeVisible();
  expect(state.runs).toHaveLength(1);
  await page.getByRole("button", { name: "刷新状态" }).click();
  await expect(page.getByText("普通聊天回复", { exact: true })).toHaveCount(1);
  await page.reload();
  await expect(page.getByLabel("开发聊天凭据")).toHaveValue("");
  await page.getByLabel("开发聊天凭据").fill("browser-only-test-token");
  await page.getByRole("button", { name: "恢复对话" }).click();
  await expect(
    page.getByText("研究继续，17+25 是多少？", { exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(() =>
      JSON.stringify({ ...localStorage, ...sessionStorage }),
    ),
  ).not.toContain("browser-only-test-token");
  await expect(page.getByText("普通聊天回复", { exact: true })).toHaveCount(1);
});

test("发送响应丢失后沿用消息 ID，断线不伪造成功", async ({ page }) => {
  const state = await setup(page);
  state.loseReply = true;
  await page.getByLabel("消息", { exact: true }).fill("检查证据");
  await page.getByRole("button", { name: "发送消息" }).click();
  await expect(page.getByRole("alert")).toContainText("尚未确认送达");
  state.loseReply = false;
  await page.getByRole("button", { name: "重试同一消息" }).click();
  await expect(page.getByText("普通聊天回复", { exact: true })).toBeVisible();
  expect(state.messages[0]).toEqual(state.messages[1]);
  state.offline = true;
  await page.getByRole("button", { name: "刷新状态" }).click();
  await expect(page.getByRole("status")).toContainText("状态更新中断");
  await expect(page.getByText("普通聊天回复", { exact: true })).toBeVisible();
  state.offline = false;
  await page.getByRole("button", { name: "刷新状态" }).click();
  await expect(page.getByRole("status")).toContainText("对话服务已连接");
});

test("取消确认与终态分开，正式结果和危险内容正确展示", async ({ page }) => {
  const state = await setup(page);
  await page.getByRole("link", { name: /事件影响是否有证据支持/ }).click();
  await page.getByRole("button", { name: "取消研究", exact: true }).click();
  await expect(page.getByRole("region", { name: "研究详情" })).toContainText(
    "取消中",
  );
  state.runs[0].status = "cancelled";
  await page.getByRole("button", { name: "重新查询研究" }).click();
  await expect(page.getByRole("region", { name: "研究详情" })).toContainText(
    "已取消",
  );
  state.runs[0].status = "completed";
  await page.getByRole("button", { name: "重新查询研究" }).click();
  await page.getByRole("button", { name: "产物", exact: true }).click();
  await expect(page.getByText("正式结果 · v1 · 证据不足")).toBeVisible();
  await page.getByRole("button", { name: /p:1/ }).click();
  await expect(
    page.getByText("<script>window.injected=true</script>", { exact: false }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: "打开原始来源" })).toHaveCount(0);
  expect(await page.evaluate(() => "injected" in window)).toBe(false);
});

// 复核保留旧链接，补充证据通过对话交给 Agent 登记新执行。
test("新证据关联旧执行，固定版本链接与窄屏可用", async ({ page }) => {
  const state = await setup(page);
  state.runs[0].status = "completed";
  state.runs.push({
    ...baseRun,
    run_id: second,
    status: "completed",
    question: "补充复核",
    previous_run_id: first,
  });
  await page.getByRole("button", { name: "刷新状态" }).click();
  await page.getByRole("link", { name: /补充复核.*补充复核/ }).click();
  await expect(page.getByText("新证据仍不足", { exact: true })).toBeVisible();
  await expect(page.getByText("demand · 维持 — 仍缺原始披露")).toBeVisible();
  await page.getByRole("link", { name: "查看前序版本" }).click();
  await expect(
    page.getByText("尚不足以建立因果关系", { exact: true }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "切换任务侧栏" }).click();
  await page.getByRole("button", { name: "补充新证据" }).click();
  await expect(page.getByLabel("新证据或原文链接")).toBeFocused();
  await page.getByLabel("新证据或原文链接").fill("补充原始披露链接");
  await page.getByRole("button", { name: "发送消息" }).click();
  await expect.poll(() => state.messages.length).toBe(1);
  expect(state.messages[0].text).toContain(`previous_run_id 为 ${first}`);
  await expect(page).toHaveURL(new RegExp(first));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "切换任务侧栏", exact: true }).click();
  await expect(page.getByRole("region", { name: "研究详情" })).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("Agent 断线仍可读档但不能发送，错误响应不声称已恢复", async ({ page }) => {
  const state = await setup(page);
  state.connected = false;
  await page.getByRole("button", { name: "刷新状态" }).click();
  await expect(page.getByRole("status")).toContainText("Agent 连接中断");
  await page.getByLabel("消息", { exact: true }).fill("继续聊天");
  await expect(page.getByRole("button", { name: "发送消息" })).toBeDisabled();
  await page.route(`**/api/chat/sessions/${session}`, (route) =>
    route.fulfill({ json: {} }),
  );
  await page.getByRole("button", { name: "刷新状态" }).click();
  await expect(page.getByRole("alert")).toContainText("会话响应无效");
});

// 请求已入账但 HTTP 仍未返回时，新输入不能被迟到的成功响应清空。
test("发送响应延迟期间保持输入只读", async ({ page }) => {
  const state = await setup(page);
  let release!: () => void;
  const waiting = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/messages", async (route) => {
    const message = route.request().postDataJSON();
    state.deliveries.push({
      id: message.message_id,
      question: message.text,
      answer: "已收到",
      state: "done",
      kind: "chat",
    });
    await waiting;
    await route.fulfill({ status: 202, json: { type: "accepted" } });
  });
  await page.getByLabel("消息", { exact: true }).fill("慢请求");
  await page.getByRole("button", { name: "发送消息" }).click();
  await expect(page.getByText("已收到", { exact: true })).toBeVisible();
  await expect(page.getByLabel("消息", { exact: true })).toHaveAttribute(
    "readonly",
    "",
  );
  release();
});

test("固定结果重新校验失败后不继续展示正式结论", async ({ page }) => {
  const state = await setup(page);
  state.runs[0].status = "completed";
  await page.getByRole("button", { name: "刷新状态" }).click();
  await page.getByRole("link", { name: /事件影响是否有证据支持/ }).click();
  await expect(page.getByText("正式结果 · v1 · 证据不足")).toBeVisible();
  await page.route("**/result", (route) =>
    route.fulfill({ status: 409, json: { error: "result_integrity_failed" } }),
  );
  await page.getByRole("button", { name: "重新查询研究" }).click();
  await expect(page.getByRole("alert")).toContainText("完整性校验失败");
  await expect(page.getByText("正式结果 · v1 · 证据不足")).toHaveCount(0);
});

// 新回复跟随对话底部；用户翻阅旧消息时不得抢走滚动位置。
test("新回复可见且不打断历史阅读", async ({ page }) => {
  const state = await setup(page);
  state.deliveries.push({
    id: "long",
    kind: "chat",
    question: "较长的研究回复",
    answer: "核对证据。\n".repeat(100),
    state: "done",
  });
  await page.getByRole("button", { name: "刷新状态" }).click();
  const messages = page.getByLabel("消息记录", { exact: true });
  await expect
    .poll(() =>
      messages.evaluate(
        (el) => el.scrollHeight - el.scrollTop - el.clientHeight,
      ),
    )
    .toBeLessThan(5);
  await messages.evaluate((el) => {
    el.scrollTop = 0;
  });
  await expect.poll(() => messages.evaluate((el) => el.scrollTop)).toBe(0);
  state.deliveries.push({
    id: "next",
    kind: "notification",
    question: "",
    answer: "新的主动回复",
    state: "done",
  });
  await page.getByRole("button", { name: "刷新状态" }).click();
  await expect(page.getByText("新的主动回复")).toBeAttached();
  expect(await messages.evaluate((el) => el.scrollTop)).toBe(0);
});

// 滑块可连续跟手；释放后固定档位，失败重试不能丢失原来的模型参数。
test("思考链平滑拖动、键盘选择与幂等重试", async ({ page }) => {
  const state = await setup(page);
  await page.getByRole("button", { name: "关闭任务侧栏" }).click();
  await page.getByRole("button", { name: "思考链：中", exact: true }).click();
  const range = page.getByRole("slider", { name: "思考链", exact: true });
  const box = (await range.boundingBox())!;
  await page.mouse.move(
    box.x + 18 + (box.width - 36) / 3,
    box.y + box.height / 2,
  );
  await page.mouse.down();
  await page.mouse.move(
    box.x + 18 + (box.width - 36) * 0.56,
    box.y + box.height / 2,
    { steps: 12 },
  );
  const during = Number(await range.inputValue());
  expect(during).toBeGreaterThan(1.5);
  expect(during).toBeLessThan(1.9);
  await page.mouse.up();
  await expect(range).toHaveValue("2");
  await range.press("End");
  await expect(range).toHaveValue("3");
  await range.press("ArrowLeft");
  await expect(range).toHaveAttribute("aria-valuetext", "高");
  await range.press("Escape");
  state.loseReply = true;
  await page.getByLabel("消息", { exact: true }).fill("带思考档位的消息");
  await page.getByRole("button", { name: "发送消息" }).click();
  await expect(page.getByRole("alert")).toContainText("尚未确认送达");
  await expect(
    page.getByRole("button", { name: "思考链：高", exact: true }),
  ).toBeDisabled();
  state.loseReply = false;
  await page.getByRole("button", { name: "重试同一消息" }).click();
  await expect.poll(() => state.messages.length).toBe(2);
  expect(state.messages[0].effort).toBe("high");
  expect(state.messages[1]).toEqual(state.messages[0]);
});

test("窄屏导航、搜索恢复与任务侧栏互斥", async ({ page }) => {
  await setup(page);
  await page.setViewportSize({ width: 789, height: 780 });
  const menu = page.getByRole("button", { name: "切换会话导航" });
  await menu.click();
  await expect(menu).toHaveAttribute("aria-expanded", "true");
  await expect(
    page.getByRole("button", { name: "新建对话", exact: true }),
  ).toBeFocused();
  await expect(page.getByText("Agent workspace")).toHaveCount(0);
  await page.getByRole("button", { name: "搜索对话", exact: true }).click();
  await page.getByLabel("对话关键词").fill("会议");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "历史里的会议记录" })
    .click();
  await expect(page).toHaveURL(/session=kq-older/);
  await expect(menu).toHaveAttribute("aria-expanded", "false");
  await menu.click();
  await page.getByRole("button", { name: "当前对话任务" }).click();
  await expect(menu).toHaveAttribute("aria-expanded", "false");
  await expect(
    page.getByRole("button", { name: "关闭任务侧栏" }),
  ).toBeFocused();
  await expect(page.locator(".conversation-host")).toHaveAttribute("inert", "");
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("button", { name: "切换任务侧栏" }),
  ).toBeFocused();
  await expect(page.locator(".conversation-host")).not.toHaveAttribute(
    "inert",
    "",
  );
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("模型没有档位能力时如实使用默认值", async ({ page }) => {
  await setup(page);
  await page.route("**/thinking", (route) =>
    route.fulfill({
      json: {
        control: "none",
        levels: [],
        current_effort: null,
        recommended_effort: null,
      },
    }),
  );
  await page.reload();
  await page.getByLabel("开发聊天凭据").fill("browser-only-test-token");
  await page.getByRole("button", { name: "恢复对话" }).click();
  await expect(
    page.getByRole("button", { name: "思考链：模型默认" }),
  ).toBeDisabled();
});

test("普通后台任务直接显示真实结果，不冒充研究报告", async ({ page }) => {
  const state = await setup(page);
  state.runs = [];
  state.tasks.push({
    task_id: "meeting-1",
    run_id: null,
    name: "agent",
    brief: "整理会议记录",
    status: "completed",
    result: "负责人：张三；下周提交接口文档。",
  });
  await page.getByRole("button", { name: "刷新状态" }).click();
  await expect(
    page.getByRole("heading", { name: "整理会议记录" }),
  ).toBeVisible();
  await expect(
    page.getByText("负责人：张三；下周提交接口文档。"),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "取消研究", exact: true }),
  ).toHaveCount(0);
});

test("减少动态效果时抽屉仍正确接管和归还焦点", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await setup(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "切换会话导航" }).click();
  await expect(
    page.getByRole("button", { name: "新建对话", exact: true }),
  ).toBeFocused();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "切换任务侧栏" }).click();
  await expect(
    page.getByRole("button", { name: "关闭任务侧栏" }),
  ).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("button", { name: "切换任务侧栏" }),
  ).toBeFocused();
});

// 推荐档位不等于已保存的当前档位，浏览器不能替用户覆盖上游默认值。
test("尚无当前档位时保留模型默认，不自动发送推荐参数", async ({ page }) => {
  const state = await setup(page);
  await page.route("**/thinking", (route) =>
    route.fulfill({
      json: {
        control: "effort",
        levels: ["low", "medium", "high"],
        current_effort: null,
        recommended_effort: "high",
      },
    }),
  );
  await page.reload();
  await page.getByLabel("开发聊天凭据").fill("browser-only-test-token");
  await page.getByRole("button", { name: "恢复对话" }).click();
  await expect(
    page.getByRole("button", { name: "思考链：模型默认" }),
  ).toBeEnabled();
  await page.getByLabel("消息", { exact: true }).fill("沿用服务端设置");
  await page.getByRole("button", { name: "发送消息" }).click();
  await expect.poll(() => state.messages.length).toBe(1);
  expect(state.messages[0]).not.toHaveProperty("effort");
});
