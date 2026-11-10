// 同一套细线图标用于导航与操作，品牌标识取自字母 K。
const paths = {
  brand: '<path d="M5 3v18M19 3 8 12l11 9M8 12h12"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4.5 4.5"/>',
  layers: '<path d="m3 7 9-4 9 4-9 4-9-4Zm0 5 9 4 9-4M3 17l9 4 9-4"/>',
  panelLeft:
    '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16"/>',
  panelRight:
    '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M15 4v16"/>',
  book: '<path d="M12 5C8 3 5 3 3 4v15c3-1 6 0 9 2 3-2 6-3 9-2V4c-2-1-5-1-9 1Zm0 0v16"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v1"/>',
  arrowUpRight: '<path d="M6 18 18 6M7 6h11v11"/>',
  arrowUp: '<path d="M12 19V5m-6 6 6-6 6 6"/>',
  arrowRight: '<path d="M5 12h14m-6-6 6 6-6 6"/>',
  chevronDown: '<path d="m6 9 6 6 6-6"/>',
  close: '<path d="m6 6 12 12M6 18 18 6"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  research:
    '<circle cx="10" cy="10" r="6"/><path d="m15 15 5 5M7 10h6m-3-3v6"/>',
  file: '<path d="M14 3H5v18h14V8l-5-5Zm0 0v5h5M8 12h8m-8 4h6"/>',
  globe:
    '<circle cx="12" cy="12" r="9"/><ellipse cx="12" cy="12" rx="4" ry="9"/><path d="M3 12h18"/>',
  grid: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M9 4v16"/>',
  code: '<path d="m8 6-6 6 6 6m8-12 6 6-6 6m-3-14-2 16"/>',
  lock: '<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 5v2"/>',
  copy: '<rect x="8" y="8" width="12" height="13" rx="2"/><path d="M16 8V3H3v13h5"/>',
  refresh:
    '<path d="M20 7v5h-5M4 17v-5h5M5 8a8 8 0 0 1 13-3l2 3M4 16l2 3a8 8 0 0 0 13-3"/>',
  sliders:
    '<path d="M4 7h9m4 0h3M4 17h3m4 0h9"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="17" r="2"/>',
};
const icon = (name) =>
  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.file}</svg>`;
const $ = (selector) => document.querySelector(selector);
const escape = (value) =>
  String(value).replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const paintIcons = () =>
  document.querySelectorAll("[data-icon]").forEach((el) => {
    el.innerHTML = icon(el.dataset.icon);
  });

// 所有内容都是设计示例；列表计数和报告引用由同一份数据生成。
const sources = [
  {
    title: "Federal Reserve issues FOMC statement",
    origin: "federalreserve.gov",
    kind: "globe",
    meta: "官方原文 · 政策声明",
    detail: "核对政策方向、声明中的条件与风险，不从标题直接推导资产价格。",
    excerpt: "示例摘录位置：在这里阅读原文对应段落，并核对发布时间与研究时点。",
    url: "https://www.federalreserve.gov/newsevents/pressreleases.htm",
  },
  {
    title: "Summary of Economic Projections",
    origin: "federalreserve.gov",
    kind: "globe",
    meta: "官方原文 · 经济预测",
    detail: "将利率决策与经济预期分开，保留不同情景下的解释。",
    excerpt: "示例摘录位置：展示预测范围、假设条件及页码，支持返回原始文件。",
    url: "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
  },
  {
    title: "A 股交易日与行情快照",
    origin: "Tushare 数据归档",
    kind: "grid",
    meta: "数据快照 · 待进一步核对",
    detail: "对齐交易日、价格口径与事件窗口，核查比较是否成立。",
    excerpt: "这是数据归档的设计占位，未装载真实行情或计算收益率。",
    url: "https://tushare.pro/",
  },
  {
    title: "事件窗口检验",
    origin: "Python 执行记录",
    kind: "code",
    meta: "计算产物 · 演示",
    detail: "保留输入、代码与输出，让每一步判断都可以追溯。",
    excerpt:
      "这是执行记录的设计占位，未运行真实回测。正式界面将展示固定代码和可信执行结果。",
  },
];
const sessions = [
  {
    title: "美联储降息如何传导至 A 股？",
    short: "美联储降息与 A 股传导",
    kind: "research",
    label: "深度研究",
    icon: "globe",
    steps: [
      "明确研究问题与时点",
      "整理来源，检查支持与反证",
      "记录缺口，保留固定版本",
    ],
    question:
      "美联储降息可能如何影响 A 股？请从原文出发，梳理传导路径，也说清楚哪些地方还不能下结论。",
    date: "今天",
    summary: "先看传导路径，再判断交易条件。",
    body: "这次研究把问题拆成了政策信号、资金定价和行业反应。现有资料适合建立观察框架，但还不足以把政策方向直接转化为买卖判断。",
    points: [
      "政策信号与经济预期需要分开阅读，避免把不同原因的降息视为同一种事件。",
      "从美元利率到人民币资产之间，仍要核对汇率、资金流和国内基本面。",
    ],
    gap: "事件窗口和定价反应尚未核对完整，因此保留“证据不足”的结论。",
    report: "美联储降息：A 股传导路径",
    followups: ["哪些证据可能推翻这个判断？", "补充一条原文，重新复核"],
  },
  {
    title: "把会议记录整理成行动清单",
    short: "本周产品会议 · 行动清单",
    kind: "organize",
    label: "内容整理",
    icon: "file",
    steps: ["阅读会议记录", "提取决定与待办事项", "整理负责人和待确认时间"],
    question:
      "整理这段会议记录：小林负责梳理登录流程，小周周五前给出页面初稿。下次评审时间还没定。请列出行动清单。",
    date: "今天",
    summary: "两项待办，一项待确认。",
    body: "我把讨论内容整理成了可以继续跟进的清单。记录中没有提到的截止时间，保留为待确认。",
    points: [
      "小林：梳理登录流程，截止时间待确认。",
      "小周：完成页面初稿，截止时间为周五。",
    ],
    gap: "下次评审时间尚未确定，需要再约。",
    report: "本周产品会议 · 行动清单",
    followups: ["帮我拟一段跟进消息", "把待确认的问题单独列出来"],
    material: "会议记录 · 对话输入",
    excerpt:
      "小林负责梳理登录流程，小周周五前给出页面初稿。下次评审时间还没定。",
  },
  {
    title: "帮我读懂这个接口的调用流程",
    short: "接口代码 · 调用流程",
    kind: "code",
    label: "代码理解",
    icon: "code",
    steps: ["阅读示例代码", "梳理请求与返回路径", "标注当前片段的范围"],
    question:
      "解释这段示例代码的调用流程：async function loadTasks() { const response = await fetch('/api/tasks'); return response.json(); }",
    date: "昨天",
    summary: "发起请求，等待响应，再解析返回值。",
    body: "调用 loadTasks() 后，浏览器向 /api/tasks 发起请求。函数等待响应，再把响应正文解析为 JSON，交给调用它的页面使用。",
    points: [
      "fetch 发出请求，await 让后续步骤等待响应。",
      "response.json() 解析正文，函数返回解析结果的 Promise。",
    ],
    gap: "这段示例没有说明后端如何生成数据，也没有处理 HTTP 错误状态。",
    report: "loadTasks · 调用流程说明",
    followups: ["解释一下 Promise 和 await", "这段代码如何处理请求失败？"],
    material: "loadTasks.js · 对话输入",
    excerpt:
      "async function loadTasks() { const response = await fetch('/api/tasks'); return response.json(); }",
  },
];
// 普通任务在前，研究作为同级示例；首页不预设用户的任务类型。
const sessionOrder = [1, 2, 0];
const state = {
  session: 0,
  tab: "sources",
  source: -1,
  version: 2,
  view: "new",
  messages: [],
};
let toastTimer;
// 导航作为窄屏抽屉出现；遮挡的正文不能接收点击或键盘焦点。
const compactScreen = matchMedia("(max-width: 1050px)");
function setNav(open, restoreFocus = false) {
  const active = compactScreen.matches && open;
  $("#shell").classList.toggle("nav-open", active);
  $(".sidebar").inert = compactScreen.matches && !active;
  $(".workspace-body").inert = active;
  $(".header-actions").inert = active;
  const trigger = $('[data-action="menu"]');
  trigger.setAttribute("aria-expanded", String(active));
  trigger.setAttribute("aria-label", active ? "收起会话导航" : "打开会话导航");
  if (active) {
    setPanel(false);
    $("#effort-popover").hidePopover();
    $('.sidebar [data-action="new"]').focus();
  } else if (restoreFocus) trigger.focus();
}
compactScreen.addEventListener("change", () => {
  setNav(false);
  setPanel(false);
});
// 资料栏在桌面展开布局，在窄屏作为独立抽屉出现；两侧抽屉互斥。
function setPanel(open, restoreFocus = false) {
  if (open) setNav(false);
  $("#shell").classList.toggle("panel-closed", !open);
  $("#shell").classList.toggle(
    "panel-mobile-open",
    compactScreen.matches && open,
  );
  $(".research-panel").inert = !open;
  $(".conversation").inert = compactScreen.matches && open;
  $('.header-actions [data-action="panel"]').setAttribute(
    "aria-expanded",
    String(open),
  );
  if (open && compactScreen.matches) {
    $("#effort-popover").hidePopover();
    $('.research-panel [data-action="panel"]').focus();
  } else if (!open && restoreFocus)
    $('.header-actions [data-action="panel"]').focus();
}

// 档位仅用于设计演示，后续由实际模型支持的 effort 配置提供。
const effortLevels = [
  ["低", "更快响应，适合简单问题"],
  ["中", "平衡速度与思考深度"],
  ["高", "投入更多思考，可能需要更长时间"],
  ["极高", "用于复杂问题，预留更多等待时间"],
];
function updateEffort(value) {
  const [label, description] = effortLevels[Math.round(value)];
  $("#effort-range").value = value;
  $("#effort-range").setAttribute("aria-valuetext", label);
  $("#effort-value").textContent = label;
  $("#effort-level").textContent = label;
  $("#effort-description").textContent = description;
  $("#effort-trigger").setAttribute("aria-label", `思考链：${label}`);
  $(".effort-slider").style.setProperty(
    "--effort-progress",
    value / (effortLevels.length - 1),
  );
}
// 拖动时连续跟手，松开后只提交最近的档位；过渡只用于吸附，不拖慢手势。
function snapEffort(value = Number($("#effort-range").value)) {
  $(".effort-slider").classList.add("is-snapping");
  updateEffort(Math.round(value));
}
$("#effort-range").addEventListener("pointerdown", () => {
  $(".effort-slider").classList.remove("is-snapping");
});
$("#effort-range").addEventListener("input", (event) =>
  updateEffort(Number(event.target.value)),
);
for (const event of ["change", "pointercancel", "blur"]) {
  $("#effort-range").addEventListener(event, () => snapEffort());
}
// 连续滑杆的键盘操作仍按四个档位前进，避免方向键变成微小的百分比调整。
$("#effort-range").addEventListener("keydown", (event) => {
  const value = Math.round(Number(event.target.value));
  const last = effortLevels.length - 1;
  const targets = {
    ArrowLeft: Math.max(0, value - 1),
    ArrowDown: Math.max(0, value - 1),
    ArrowRight: Math.min(last, value + 1),
    ArrowUp: Math.min(last, value + 1),
    Home: 0,
    End: last,
  };
  if (event.key in targets) {
    event.preventDefault();
    snapEffort(targets[event.key]);
  }
});
// 弹层贴近触发按钮并限制在视口内，避免手机上被输入框边界裁切。
$("#effort-popover").addEventListener("beforetoggle", (event) => {
  $("#effort-trigger").setAttribute(
    "aria-expanded",
    String(event.newState === "open"),
  );
  if (event.newState !== "open") return;
  const rect = $("#effort-trigger").getBoundingClientRect();
  const width = Math.min(264, innerWidth - 32);
  event.target.style.left = `${Math.max(16, Math.min(rect.right - width, innerWidth - width - 16))}px`;
  event.target.style.bottom = `${innerHeight - rect.top + 10}px`;
});
window.addEventListener("resize", () => $("#effort-popover").hidePopover());
function toast(text) {
  $("#toast").textContent = text;
  $("#toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    $("#toast").hidden = true;
  }, 2400);
}
function openPanel(tab = state.tab) {
  state.tab = tab;
  renderPanel();
  setPanel(true);
}
function renderSessions() {
  $("#sessions").innerHTML = sessionOrder
    .map(
      (i) =>
        `<button class="session ${state.session === i && state.view === "chat" ? "active" : ""}" data-session="${i}"><span class="session-title">${sessions[i].short}</span><small><span class="dot"></span>${sessions[i].label} · ${sessions[i].date}</small></button>`,
    )
    .join("");
}
function selectSession(index) {
  state.session = index;
  state.view = "chat";
  state.version = 2;
  state.source = -1;
  state.messages = [];
  setNav(false);
  setPanel(false);
  render();
}
function renderThread() {
  const s = sessions[state.session];
  $("#breadcrumb").textContent =
    state.view === "library"
      ? "全部任务"
      : state.view === "new"
        ? "新建对话"
        : s.label;
  if (state.view === "library") {
    $("#thread").innerHTML =
      `<h1>全部任务</h1><p class="thread-date">${sessions.length} 个示例任务 · 继续上次的对话</p>${sessionOrder
        .map((i) => {
          const s = sessions[i];
          return `<button class="library-row" data-session="${i}"><h3>${s.title}</h3><small>${s.date} · ${s.label} · 查看对话与产物 →</small></button>`;
        })
        .join("")}`;
    $("#suggestions").innerHTML = "";
    return;
  }
  const content =
    state.view === "new"
      ? state.messages.length
        ? ""
        : `<div class="empty-home"><span data-icon="brand"></span><h1>今天，想完成什么？</h1><div class="prompt-list">${sessionOrder.map((i) => `<button data-session="${i}"><span data-icon="${sessions[i].icon}"></span>${sessions[i].title}<span data-icon="arrowUpRight"></span></button>`).join("")}</div></div>`
      : `<h1>${s.title}</h1><p class="thread-date">${s.label} · 示例对话</p><div class="user-message">${s.question}</div><div class="agent-label">${icon("brand")}<span>kli-Quant</span><small>Agent</small></div><details class="process"><summary><span data-icon="check"></span>示例任务已完成<span>·</span>${s.steps.length} 个步骤<span data-icon="chevronDown"></span></summary><ol>${s.steps.map((step, i) => `<li>0${i + 1} &nbsp; ${step}</li>`).join("")}</ol></details><div class="answer"><h2>${s.summary}</h2><p>${s.body}${state.session === 0 ? '<button class="citation" data-source="0" aria-label="查看引用 1">1</button><button class="citation" data-source="1" aria-label="查看引用 2">2</button>' : ""}</p><ul>${s.points.map((p) => `<li>${p}</li>`).join("")}</ul><div class="${s.kind === "research" ? "evidence-gap" : "task-note"}">${s.gap}</div></div><button class="document-card" data-action="report"><span data-icon="file"></span><span><strong>${s.report}</strong><small>${s.kind === "research" ? "研究报告 · 固定版本 v2" : "任务产物 · 点击展开"} · 示例</small></span><span data-icon="arrowUpRight"></span></button><div class="answer-actions"><button class="icon-button" data-action="copy" aria-label="复制示例回答"><span data-icon="copy"></span></button><button class="icon-button" data-action="versions" aria-label="查看任务过程"><span data-icon="refresh"></span></button><small>${s.kind === "research" ? "引用与版本随研究保留" : "沿着对话继续完善"}</small></div>`;
  $("#thread").innerHTML =
    content +
    state.messages
      .map(
        (m) =>
          `<div class="user-message">${escape(m)}</div><div class="demo-response"><div class="agent-label">${icon("brand")}kli-Quant</div><p>已加入演示对话。这版 Demo 仅展示交互，没有调用真实 Agent 或执行任务。</p></div>`,
      )
      .join("");
  $("#suggestions").innerHTML =
    state.view === "new"
      ? ""
      : s.followups
          .map(
            (text) =>
              `<button data-prompt="${escape(text)}">${text} ↗</button>`,
          )
          .join("");
}
// 侧栏随任务展示资料、产物和过程；研究专属的引用与版本只在研究任务中出现。
function renderPanel() {
  const hasTask = state.view === "chat";
  $(".research-panel").classList.toggle("is-empty", !hasTask);
  const s = sessions[state.session];
  const hasResearch = hasTask && s.kind === "research";
  $("#source-count").textContent = hasTask
    ? hasResearch
      ? sources.length
      : 1
    : 0;
  document
    .querySelectorAll("[data-tab]")
    .forEach((button) =>
      button.setAttribute(
        "aria-selected",
        String(button.dataset.tab === state.tab),
      ),
    );
  if (!hasTask) {
    $("#panel-content").innerHTML =
      `<div class="empty-panel">${icon("file")}<h3>还没有任务资料</h3><p>对话中的资料、产物和处理过程，<br>会收纳在这里。</p></div>`;
    return;
  }
  if (!hasResearch) {
    if (state.tab === "sources") {
      $("#panel-content").innerHTML =
        `<p class="panel-intro">当前任务使用的输入资料 · 设计示例</p><div class="source-row"><div class="source-origin">${icon(s.icon)}对话输入</div><h3>${s.material}</h3></div><div class="source-detail"><blockquote>${escape(s.excerpt)}</blockquote></div>`;
    } else if (state.tab === "report") {
      $("#panel-content").innerHTML =
        `<div class="report-label">${icon("file")}任务产物 · 设计示例</div><h2 class="report-title">${s.report}</h2><div class="report-copy"><p>${s.body}</p><h3>${s.kind === "organize" ? "行动清单" : "调用流程"}</h3><ul>${s.points.map((p) => `<li>${p}</li>`).join("")}</ul><h3>${s.kind === "organize" ? "待确认" : "当前范围"}</h3><p>${s.gap}</p></div><button class="outline-button" data-action="supplement">继续完善 ${icon("arrowRight")}</button>`;
    } else {
      $("#panel-content").innerHTML =
        `<p class="panel-intro">任务如何完成，一步步展开。<br>以下为过程展示示例，未实际执行。</p>${s.steps.map((step, i) => `<div class="version"><time>步骤 0${i + 1}</time><h3>${step}</h3><p>${i === 2 ? "产物已整理，可在对话中继续修改。" : "已完成 · 示例"}</p></div>`).join("")}`;
    }
    paintIcons();
    return;
  }
  if (state.tab === "sources") {
    $("#panel-content").innerHTML =
      `<p class="panel-intro">${sources.length} 份示例资料。点击查看摘录，<br>沿着引用核对每一步判断。</p>${sources.map((source, i) => `<button class="source-row ${state.source === i ? "selected" : ""}" data-source="${i}" aria-expanded="${state.source === i}"><div class="source-origin">${icon(source.kind)}${source.origin}<span>${i + 1}</span></div><h3>${source.title}</h3><p>${source.meta}</p></button>${state.source === i ? `<div class="source-detail"><p>${source.detail}</p><blockquote>${source.excerpt}</blockquote>${source.url ? `<a href="${source.url}" target="_blank" rel="noopener noreferrer">打开官方网站 ${icon("arrowUpRight")}</a>` : ""}</div>` : ""}`).join("")}<h3 class="panel-section-title">需要继续核对</h3><div class="gap-note"><span>${icon("info")}证据仍有缺口</span>政策方向不等于资产价格方向。事件时点、行情口径和替代解释仍需核对。</div>`;
  } else if (state.tab === "report") {
    $("#panel-content").innerHTML =
      `<div class="report-label">${icon("file")}固定版本 v${state.version} · 设计示例</div><h2 class="report-title">${s.report}</h2><span class="report-conclusion">${state.version === 2 ? "证据不足" : "初步整理"}</span><div class="report-copy"><p>${s.body}</p><h3>研究路径</h3><ul>${s.points.map((p) => `<li>${p}</li>`).join("")}</ul><h3>${state.version === 2 ? "此次补充" : "初版范围"}</h3><p>${state.version === 2 ? "补充了替代解释与证据缺口。结论保持克制，初版内容仍可单独查看。" : "保留问题拆解与核对方向，尚未加入后续复核说明。"}</p><h3>结论边界</h3><p>${s.gap}</p></div><button class="outline-button" data-action="supplement">补充证据并复核 ${icon("arrowRight")}</button>`;
  } else {
    $("#panel-content").innerHTML =
      `<p class="panel-intro">新证据生成新版本，旧判断保留。<br>这里展示的是版本交互示例。</p><div class="version"><time>示例版本 · 今天</time><h3>v2 · 补充反证<span class="current">当前版本</span></h3><p>补充替代解释，明确尚未核对的条件。结论：证据不足。</p><button class="outline-button" data-version="2">查看 v2</button></div><div class="version"><time>示例版本 · 昨天</time><h3>v1 · 首次研究</h3><p>建立问题框架，整理需要进一步核对的证据。</p><button class="outline-button" data-version="1">查看 v1</button></div>`;
  }
  paintIcons();
}
function render() {
  renderSessions();
  renderThread();
  renderPanel();
  paintIcons();
  $("#conversation-scroll").scrollTop = 0;
}
function fillPrompt(text) {
  $("#message").value = text;
  $(".send").disabled = false;
  if (compactScreen.matches) setPanel(false);
  $("#message").focus();
}
function searchResults() {
  const query = $("#search").value.trim();
  const matches = sessions
    .map((s, index) => ({ ...s, index }))
    .filter((s) => s.title.includes(query));
  $("#search-results").innerHTML = matches.length
    ? matches
        .map((s) => `<button data-session="${s.index}">${s.title}</button>`)
        .join("")
    : "<p>没有找到相关对话，换个关键词试试。</p>";
}

// 事件委托覆盖动态内容；用户输入始终转义后显示，不执行 HTML。
document.addEventListener("click", async (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  if (button.dataset.session !== undefined) {
    selectSession(Number(button.dataset.session));
    $("#search-dialog").close();
  }
  if (button.dataset.source !== undefined) {
    const index = Number(button.dataset.source);
    state.source = state.source === index ? -1 : index;
    openPanel("sources");
  }
  if (button.dataset.tab) {
    state.tab = button.dataset.tab;
    renderPanel();
  }
  if (button.dataset.version) {
    state.version = Number(button.dataset.version);
    openPanel("report");
  }
  if (button.dataset.prompt) fillPrompt(button.dataset.prompt);
  switch (button.dataset.action) {
    case "new":
      state.view = "new";
      state.messages = [];
      $("#message").value = "";
      $(".send").disabled = true;
      setNav(false);
      setPanel(false);
      render();
      $("#message").focus();
      break;
    case "library":
      state.view = "library";
      setNav(false);
      setPanel(false);
      render();
      break;
    case "menu":
      setNav(!$("#shell").classList.contains("nav-open"), true);
      break;
    case "close-nav":
      setNav(false, true);
      break;
    case "panel":
      setPanel($("#shell").classList.contains("panel-closed"), true);
      break;
    case "close-panel":
      setPanel(false, true);
      break;
    case "report":
      state.version = 2;
      openPanel("report");
      break;
    case "versions":
      openPanel("versions");
      break;
    case "supplement":
      fillPrompt(
        `请基于「${sessions[state.session].report}」${sessions[state.session].kind === "research" ? "补充证据" : "继续完善"}：`,
      );
      break;
    case "link":
      fillPrompt($("#message").value || "补充一份参考资料：");
      break;
    case "search":
      $("#search-dialog").showModal();
      $("#search").value = "";
      searchResults();
      $("#search").focus();
      break;
    case "close-search":
      $("#search-dialog").close();
      break;
    case "about":
      $("#about-dialog").showModal();
      break;
    case "close-about":
      $("#about-dialog").close();
      break;
    case "copy":
      try {
        await navigator.clipboard.writeText(
          `${sessions[state.session].summary}\n${sessions[state.session].body}\n${sessions[state.session].gap}\n（设计示例）`,
        );
        toast("已复制示例回答");
      } catch {
        toast("浏览器未允许复制，请选中文字复制。");
      }
      break;
  }
});
$("#search").addEventListener("input", searchResults);
$("#message").addEventListener("input", () => {
  $(".send").disabled = !$("#message").value.trim();
});
$("#message").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    $("#composer").requestSubmit();
  }
});
$("#composer").addEventListener("submit", (event) => {
  event.preventDefault();
  const message = $("#message").value.trim();
  if (!message) return;
  if (state.view === "library") state.view = "new";
  state.messages.push(message);
  $("#message").value = "";
  $(".send").disabled = true;
  renderThread();
  paintIcons();
  $("#conversation-scroll").scrollTop = $("#conversation-scroll").scrollHeight;
});
document.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
    event.preventDefault();
    $('[data-action="new"]').click();
  }
  const navOpen = $("#shell").classList.contains("nav-open");
  if (
    event.key === "Escape" &&
    !document.querySelector("dialog[open]") &&
    !$("#effort-popover").matches(":popover-open")
  ) {
    if (navOpen) setNav(false, true);
    else if (!$("#shell").classList.contains("panel-closed"))
      setPanel(false, true);
  }
  // 抽屉打开时 Tab 只在导航与收起按钮间移动，弹出搜索框时交给原生 dialog。
  if (
    event.key === "Tab" &&
    (navOpen || $("#shell").classList.contains("panel-mobile-open")) &&
    !document.querySelector("dialog[open]")
  ) {
    const selector = navOpen
      ? '.sidebar a, .sidebar button, [data-action="menu"]'
      : '.research-panel button, .research-panel a, .header-actions [data-action="panel"]';
    const controls = [...document.querySelectorAll(selector)].filter(
      (el) => el.offsetParent !== null,
    );
    const current = controls.indexOf(document.activeElement);
    const next =
      (current + (event.shiftKey ? -1 : 1) + controls.length) % controls.length;
    event.preventDefault();
    controls[next].focus();
  }
});
// 数据与视图的基本约束可在浏览器控制台直接验证。
console.assert(
  sources.length === 4 && sessions.every((s) => s.points.length === 2),
  "演示内容与列表约束不一致",
);
setNav(false);
setPanel(false);
updateEffort(1);
render();
