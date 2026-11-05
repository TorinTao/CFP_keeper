/* CFP Keeper dashboard — vanilla JS, no dependencies. */
"use strict";

const state = {
  venues: [],
  allVenues: [],
  watched: [],
  counts: {},
  topics: [],
  candidates: [],
  filters: { area: "", topic: "", type: "", within: "", q: "", showPassed: false },
  view: "calendar",
  calScope: "all",
  calMode: "verified",
  year: null,
  selected: null,
  scraping: false,
  verifying: false,
  verifyingJournals: false,
};

const CAL_KIND_CLASS = {
  abstract: "k-abstract",
  full_paper: "k-full_paper",
  supplementary: "k-supplementary",
  rebuttal: "k-rebuttal",
  notification: "k-notification",
  camera_ready: "k-camera_ready",
  conference: "k-conference",
};
const MONTH_NAMES = ["1月","2月","3月","4月","5月","6月","7月","8月","9月","10月","11月","12月"];
const WEEKDAYS = ["一","二","三","四","五","六","日"];
const TRACK_KINDS = {
  main: "主会", workshop: "工作坊", challenge: "竞赛", journal: "期刊通道", dataset: "数据集",
  special: "专题", demo: "演示", findings: "Findings", abstract: "摘要", poster: "海报",
  short: "短篇", review: "综述", comment: "评论", industry: "工业界", srw: "学生",
  proceedings: "论文集", tutorial: "教程",
};

const $ = (sel) => document.querySelector(sel);
const esc = (v) =>
  String(v == null ? "" : v)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

async function api(path, options) {
  const res = await fetch(path, Object.assign({ headers: { "Content-Type": "application/json" } }, options));
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch (err) { throw new Error(`响应不是 JSON: ${text.slice(0, 120)}`); }
  if (!res.ok) {
    const message = data && data.error ? data.error.message || data.error.code : `HTTP ${res.status}`;
    throw new Error(message);
  }
  return data;
}

function toast(message) {
  let node = document.querySelector(".toastmsg");
  if (!node) { node = document.createElement("div"); node.className = "toastmsg"; document.body.appendChild(node); }
  node.textContent = message;
  node.classList.add("show");
  clearTimeout(node._timer);
  node._timer = setTimeout(() => node.classList.remove("show"), 2600);
}

/* ------------------------------------------------------------------ loading */
async function loadAll() {
  const params = new URLSearchParams();
  if (state.filters.area) params.set("area", state.filters.area);
  if (state.filters.topic) params.set("topic", state.filters.topic);
  if (state.filters.type) params.set("type", state.filters.type);
  if (state.filters.within) params.set("within", state.filters.within);
  if (state.filters.q) params.set("q", state.filters.q);
  if (state.filters.showPassed) params.set("include_passed", "1");

  const [allRes, filteredRes, watchedRes, candidatesRes] = await Promise.all([
    api("/api/venues"),
    api(`/api/venues?${params.toString()}`),
    api("/api/venues?watching=1"),
    api("/api/candidates"),
  ]);
  state.allVenues = allRes.venues || [];
  state.venues = filteredRes.venues || [];
  state.watched = watchedRes.venues || [];
  state.counts = allRes.counts || {};
  state.topics = allRes.topics || [];
  state.candidates = (candidatesRes.candidates || []).filter((c) => c.status === "candidate");

  renderTopicOptions();
  renderBothTables();
  renderCountdown();
  renderCalendar();
}

function renderBothTables() {
  renderRows($("#rows"), state.venues, $("#empty"));
  renderRows($("#rows-home"), state.watched, $("#empty-home"));
  $("#watch-count").textContent = state.watched.length ? `共 ${state.watched.length} 个` : "";
  const filtered = state.venues.length !== state.allVenues.length;
  $("#all-count").textContent = filtered
    ? `筛选后 ${state.venues.length} 个 / 共 ${state.allVenues.length} 个`
    : `共 ${state.allVenues.length} 个`;
}

const VIEWS = ["calendar", "all", "watch"];

function switchView(view, silent) {
  if (!VIEWS.includes(view)) view = "calendar";
  state.view = view;
  document.querySelectorAll(".nav-tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.view === view);
  });
  VIEWS.forEach((name) => {
    const section = document.getElementById(`view-${name}`);
    if (section) section.hidden = name !== view;
  });
  if (!silent && location.hash !== `#${view}`) history.replaceState(null, "", `#${view}`);
  if (view === "calendar") renderCalendar();
}

function renderTopicOptions() {
  const select = $("#topic-select");
  const current = state.filters.topic;
  select.innerHTML = ['<option value="">全部主题</option>'].concat(
    state.topics.map((t) => `<option value="${esc(t.name)}"${t.name === current ? " selected" : ""}>${esc(t.name)} (${t.count})</option>`)
  ).join("");
}

function formatShort(ts) {
  return String(ts || "").replace("T", " ").slice(5, 16);
}

function renderJournalInfo(venue) {
  const box = $("#d-journal");
  if (!box) return;
  const id = venue.identity || {};
  const met = venue.metrics || {};
  if (!id.title && !met.impact_factor) { box.hidden = true; return; }
  box.hidden = false;
  const rows = [];
  if (id.title) {
    rows.push(`<dt>全称</dt><dd>${esc(id.title)}</dd>`);
    if (id.publisher) rows.push(`<dt>出版社</dt><dd>${esc(id.publisher)}</dd>`);
    if ((id.issn || []).length) rows.push(`<dt>ISSN</dt><dd class="mono">${esc(id.issn.join(" / "))}</dd>`);
    rows.push(`<dt>身份来源</dt><dd><a href="${esc(id.url || "#")}" target="_blank" rel="noopener">Crossref</a> · 核验于 ${esc(formatShort(id.checked_at))}</dd>`);
  }
  if (met.impact_factor) rows.push(`<dt>影响因子</dt><dd>${esc(met.impact_factor)}</dd>`);
  if (met.review_cycle) rows.push(`<dt>审稿周期</dt><dd>${esc(met.review_cycle)}</dd>`);
  if (met.acceptance) rows.push(`<dt>录用比例</dt><dd>${esc(met.acceptance)}</dd>`);
  if (met.open_access) rows.push(`<dt>是否 OA</dt><dd>${esc(met.open_access)}${met.gold_oa_share ? "（Gold OA " + esc(met.gold_oa_share) + "）" : ""}</dd>`);
  if (met.submission_url) rows.push(`<dt>投稿入口</dt><dd><a href="${esc(met.submission_url)}" target="_blank" rel="noopener">打开</a></dd>`);
  if (met.source) rows.push(`<dt>指标来源</dt><dd><a href="${esc(met.url || "#")}" target="_blank" rel="noopener">LetPub</a>（第三方·网友分享）· ${esc(formatShort(met.checked_at))}</dd>`);
  box.innerHTML = `<h3>期刊信息 <span class="h3-note">Crossref 核验身份 · LetPub 提供指标</span></h3><dl class="d-meta">${rows.join("")}</dl>`;
}

function statusMeta(status) {
  if (status === "confirmed") return { text: "人工核验", cls: "confirmed" };
  if (status === "verified") return { text: "自动核验", cls: "verified" };
  if (status === "scraped") return { text: "自动抓取", cls: "scraped" };
  if (status === "unpublished") return { text: "官网未公布", cls: "unpublished" };
  if (status === "blocked") return { text: "官网不可达", cls: "blocked" };
  if (status === "aggregator") return { text: "第三方来源", cls: "aggregator" };
  if (status === "manual") return { text: "待人工核验", cls: "manual" };
  if (status === "scheduled") return { text: "会期（未核验）", cls: "unpublished" };
  return { text: "待核验", cls: "predicted" };
}

function urgencyClass(days) {
  if (days <= 0) return "today";
  if (days <= 7) return "week";
  if (days <= 30) return "month";
  return "later";
}

function renderCountdown() {
  // Only the nav shows the global countdown now; the big card was removed.
  const el = $("#nav-countdown");
  if (!el) return;
  const next = state.allVenues.find((v) => v.next);
  if (!next) {
    el.textContent = "暂无即将到来的截稿";
    return;
  }
  const dl = next.next;
  const days = dl.days_left >= 0 ? dl.days_left : 0;
  el.textContent = `下一场 ${days} 天 · ${next.abbr} ${dl.label}`;
  el.title = `原始 ${dl.date} ${dl.time} ${dl.tz} → 北京 ${dl.beijing}`;
}

/* --------------------------------------------------------------- jump links */
function dblpUrl(venue) {
  return `https://dblp.org/search?q=${encodeURIComponent(venue.abbr || venue.name || "")}`;
}

function jumpLink(url, label, title) {
  if (!url) return "";
  return `<a class="jump" href="${esc(url)}" target="_blank" rel="noopener" title="${esc(title || label)}">${esc(label)}</a>`;
}

function jumpLinks(venue, compact) {
  const parts = [jumpLink(venue.official_url, compact ? "官网↗" : "官网 ↗", "打开官网")];
  if (venue.cfp_url && venue.cfp_url !== venue.official_url) {
    parts.push(jumpLink(venue.cfp_url, compact ? "CFP↗" : "CFP 页 ↗", "打开 CFP 征稿页"));
  }
  if (!compact) parts.push(jumpLink(dblpUrl(venue), "DBLP 往届 ↗", "在 DBLP 查往届日期"));
  return parts.filter(Boolean).join("");
}

/* ------------------------------------------------------------------ table */
function renderRows(tbody, venues, emptyEl) {
  if (!tbody) return;
  tbody.innerHTML = "";
  if (emptyEl) emptyEl.hidden = venues.length > 0;

  for (const venue of venues) {
    const tr = document.createElement("tr");
    tr.className = "row";
    tr.addEventListener("click", (event) => {
      if (event.target.closest(".star") || event.target.closest(".jump")) return;
      openDrawer(venue);
    });

    const dl = venue.next;
    const watchBtn = `<button class="star ${venue.watching ? "on" : ""}" title="关注">${venue.watching ? "★" : "☆"}</button>`;

    let ddlCells;
    let badgeCell = "";
    if (venue.rolling) {
      const ident = venue.identity || {};
      const met = venue.metrics || {};
      // Same status vocabulary as conferences; source decides which one applies.
      let jStatus;
      if (met.source || met.impact_factor) {
        jStatus = { text: "第三方来源", cls: "aggregator", title: "指标来自 LetPub（第三方）" };
      } else if (ident.title) {
        jStatus = { text: "自动核验", cls: "verified", title: "全称/出版社/ISSN 由 Crossref 核验" };
      } else {
        jStatus = { text: "待核验", cls: "predicted", title: "尚未核验" };
      }
      badgeCell = `<span class="badge-line"><span class="badge ${jStatus.cls}" title="${esc(jStatus.title)}">${jStatus.text}</span></span>` +
        (venue.verified_at ? `<span class="checked-at">核验于 ${esc(formatShort(venue.verified_at))}</span>` : "");
      const bits = [];
      let usedEstimate = false;
      if (met.impact_factor) bits.push(`IF ${met.impact_factor}`);
      if (met.review_cycle) bits.push(`审稿 ${met.review_cycle}`);
      else if (venue.review_cycle_weeks) { bits.push(`预计审稿 ${venue.review_cycle_weeks} 周`); usedEstimate = true; }
      if (met.acceptance) bits.push(`录用 ${met.acceptance}`);
      const jText = bits.length ? bits.join(" · ") : "滚动投稿 · 数据待核验";
      const jNote = met.source
        ? `<span class="checked-at">来源 LetPub${usedEstimate ? "（审稿周期为本站经验值）" : ""} · ${esc(formatShort(met.checked_at))}</span>`
        : `<span class="checked-at">经验值，未经核验</span>`;
      ddlCells = `<td colspan="4" class="muted">${esc(jText)}${jNote}</td>`;
    } else if (!dl) {
      ddlCells = `<td colspan="4" class="muted">暂无未过期的截止</td>`;
    } else {
      const sm = dl.kind === "conference"
        ? { text: "会期（未核验）", cls: "unpublished" }
        : statusMeta(dl.source_status);
      const badges = [`<span class="badge ${sm.cls}">${sm.text}</span>`];
      if (dl.disputed) badges.push(`<span class="badge disputed" title="官网写 ${esc(dl.disputed.page_date)}（${esc((dl.disputed.checked_at || "").slice(0, 10))}），与库中相差 ${esc(dl.disputed.shift_days)} 天">数据不一致</span>`);
      if (dl.freshness === "stale") badges.push(`<span class="badge stale">数据陈旧</span>`);
      if (dl.state === "passed") badges.push(`<span class="badge passed">已截止</span>`);
      ddlCells = `
        <td><span class="kind">${esc(dl.label)}</span></td>
        <td class="mono raw-tz ${dl.approximate ? "approx" : ""}" title="${esc(dl.approximate ? "官网未公布，按往年规律推测：" + dl.date : dl.date)}">${dl.approximate ? esc(dl.fuzzy || "待定") : esc(dl.date) + " " + esc(dl.time) + " " + esc(dl.tz)}</td>
        <td class="mono bj-time ${dl.approximate ? "approx" : ""}">${dl.approximate ? "—" : esc(dl.beijing)}</td>
        <td class="num"><span class="days ${dl.approximate || dl.source_status === "aggregator" ? "approx" : "exact"}">${dl.days_left}</span></td>`;
      const checked = venue.last_checked ? `<span class="checked-at">核验于 ${esc(formatShort(venue.last_checked))}</span>` : "";
      badgeCell = `<span class="badge-line">${badges.join(" ")}</span>${checked}`;
    }

    const topics = venue.topics || [];
    const active = state.filters.topic;
    const ordered = active && topics.includes(active) ? [active, ...topics.filter((t) => t !== active)] : topics;
    const chips = ordered.slice(0, 3).map((t) => `<span class="topic${t === active ? " active" : ""}">${esc(t)}</span>`).join("");
    const more = ordered.length > 3 ? `<span class="topic more">+${ordered.length - 3}</span>` : "";
    const rate = venue.acceptance && venue.acceptance.display
      ? `<span class="rate" title="${esc(venue.acceptance.note || "近年统计值")}">${esc(venue.acceptance.display)}</span>` : "";

    tr.innerHTML = `
      <td class="col-watch">${watchBtn}</td>
      <td>
        <span class="abbr">${esc(venue.abbr)}</span>
        ${venue.edition ? `<span class="edition">${esc(venue.edition)}</span>` : ""}
        ${rate}
        ${venue.type === "journal" ? `<span class="badge type">期刊</span>` : ""}
        <span class="venue-name">${esc(venue.name)}</span>
        ${topics.length ? `<span class="venue-topics">${chips}${more}</span>` : ""}
      </td>
      ${ddlCells}
      <td>${badgeCell}</td>
      <td class="col-link">${jumpLinks(venue, false)}</td>`;

    tr.querySelector(".star").addEventListener("click", (event) => {
      event.stopPropagation();
      toggleWatch(venue);
    });
    tbody.appendChild(tr);
  }
}

/* ------------------------------------------------------------------ calendar */
function calendarVenues() {
  return state.calScope === "watch" ? state.watched : state.allVenues;
}

function collectEvents() {
  const byDay = new Map();
  for (const venue of calendarVenues()) {
    for (const dl of venue.deadlines || []) {
      if (dl.state === "invalid") continue;
      // "已核验" mode hides guessed dates: their exact day is not trustworthy.
      if (state.calMode === "verified" && dl.approximate) continue;
      const day = String(dl.beijing || "").slice(0, 10);
      if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) continue;
      if (!byDay.has(day)) byDay.set(day, []);
      byDay.get(day).push({ venue, dl, day });
    }
  }
  return byDay;
}

function renderCalendar() {
  const byDay = collectEvents();
  state.eventsByDay = byDay;

  const years = [...new Set([...byDay.keys()].map((d) => Number(d.slice(0, 4))))].sort();
  const currentYear = new Date().getFullYear();
  const yearCount = {};
  for (const day of byDay.keys()) {
    const y = Number(day.slice(0, 4));
    yearCount[y] = (yearCount[y] || 0) + byDay.get(day).length;
  }
  if (!state.year) {
    // Default to the year of the nearest upcoming verified deadline: that is
    // what the user is actually planning around.
    const upcoming = state.allVenues
      .map((v) => v.next)
      .filter((n) => n && n.days_left >= 0)
      .sort((a, b) => a.days_left - b.days_left)[0];
    if (upcoming) state.year = Number(String(upcoming.beijing || "").slice(0, 4));
    if (!state.year) {
      const busiest = Object.entries(yearCount).sort((a, b) => b[1] - a[1] || a[0] - b[0])[0];
      state.year = busiest ? Number(busiest[0]) : currentYear;
    }
  }
  const allYears = years.length ? years : [currentYear];
  if (!allYears.includes(state.year)) state.year = allYears.includes(2026) ? 2026 : allYears[0];
  $("#year-select").innerHTML = allYears
    .map((y) => `<option value="${y}"${y === state.year ? " selected" : ""}>${y} 年（${yearCount[y] || 0} 个截止）</option>`)
    .join("");

  const todayStr = new Date().toLocaleDateString("sv-SE");
  const months = [];
  for (let m = 0; m < 12; m += 1) {
    const first = new Date(state.year, m, 1);
    const daysInMonth = new Date(state.year, m + 1, 0).getDate();
    const offset = (first.getDay() + 6) % 7;
    const cells = [];
    for (let i = 0; i < offset; i += 1) cells.push('<div class="cal-day cal-blank"></div>');
    for (let d = 1; d <= daysInMonth; d += 1) {
      const iso = `${state.year}-${String(m + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
      const events = byDay.get(iso) || [];
      const dots = events.slice(0, 4).map(({ dl }) => {
        const kind = CAL_KIND_CLASS[dl.kind] || "k-other";
        // solid = has a source (verified/confirmed/third-party); hollow = guessed
        const conf = dl.approximate ? (dl.source_status === "aggregator" ? "third" : "pred") : "conf";
        return `<i class="dot ${kind} ${conf}"></i>`;
      }).join("");
      const more = events.length > 4 ? `<i class="dot-more">+${events.length - 4}</i>` : "";
      const classes = ["cal-day"];
      if (events.length) classes.push("has-events");
      if (iso === todayStr) classes.push("today");
      const tip = events.length ? `${iso} · ` + events.map((e) => `${e.venue.abbr} ${e.dl.label}${e.dl.approximate ? "（约）" : ""}`).join("；") : "";
      cells.push(`<div class="${classes.join(" ")}" data-day="${iso}" title="${esc(tip)}">
        <span class="cal-num">${d}</span><span class="cal-dots">${dots}${more}</span></div>`);
    }
    months.push(`<div class="cal-month">
      <div class="cal-month-head">${MONTH_NAMES[m]}<span class="cal-year">${state.year}</span></div>
      <div class="cal-week">${WEEKDAYS.map((w) => `<span>${w}</span>`).join("")}</div>
      <div class="cal-grid">${cells.join("")}</div></div>`);
  }
  $("#year-calendar").innerHTML = months.join("");
}

function showDayPopover(day, anchor) {
  const events = (state.eventsByDay || new Map()).get(day) || [];
  if (!events.length) return;
  const pop = $("#day-popover");
  pop.innerHTML = `
    <div class="pop-head"><strong class="mono">${esc(day)}</strong><span class="muted">${events.length} 个截止</span></div>
    <ul>${events.map(({ venue, dl }) => {
      const sm = statusMeta(dl.source_status);
      const timeText = dl.approximate ? "约" : String(dl.beijing || "").slice(11, 16) || "—";
      return `<li data-venue="${esc(venue.id)}">
        <span class="pop-time mono ${dl.approximate ? "approx" : ""}">${esc(timeText)}</span>
        <span class="pop-venue">${esc(venue.abbr)}</span>
        <span class="pop-label ${dl.approximate ? "approx" : ""}">${esc(dl.label)}</span>
        ${dl.track ? `<span class="track-tag">${esc(dl.track)}</span>` : ""}
        <span class="badge ${sm.cls}">${sm.text}</span></li>`;
    }).join("")}</ul>
    <div class="pop-foot">原始时区：${esc(events.map((e) => e.dl.approximate ? (e.dl.fuzzy || e.dl.date) + "（推测）" : `${e.dl.date} ${e.dl.time} ${e.dl.tz}`).join(" / "))}</div>`;

  pop.hidden = false;
  const rect = anchor.getBoundingClientRect();
  const width = pop.offsetWidth;
  const height = pop.offsetHeight;
  let left = rect.left + window.scrollX;
  let top = rect.bottom + window.scrollY + 6;
  if (left + width > window.scrollX + document.documentElement.clientWidth - 8) {
    left = window.scrollX + document.documentElement.clientWidth - width - 8;
  }
  if (top + height > window.scrollY + document.documentElement.clientHeight - 8) {
    top = rect.top + window.scrollY - height - 6;
  }
  pop.style.left = `${Math.max(8, left)}px`;
  pop.style.top = `${Math.max(8, top)}px`;
}

function hideDayPopover() {
  const pop = $("#day-popover");
  if (pop) pop.hidden = true;
}

/* --------------------------------------------------------------- submission */
function renderSubmission(sub, acceptance) {
  const PREPRINT = { allowed: ["允许", "ok"], conditional: ["受限", "warn"], restricted: ["禁止", "bad"], unknown: ["未知", ""] };
  const CODE = { required: ["必需", "bad"], encouraged: ["鼓励", "ok"], optional: ["可选", ""], unknown: ["未知", ""] };
  const ACCESS = { open: "开放获取", subscription: "订阅制", hybrid: "混合模式", registration: "注册费", unknown: "未知" };
  const ATTEND = { "in-person": "现场", hybrid: "现场+线上", virtual: "线上", "n/a": "不适用", unknown: "未知" };

  const rows = [];
  const add = (label, valueHtml, note) =>
    rows.push(`<dt>${label}</dt><dd>${valueHtml}${note ? `<span class="sub-note">${esc(note)}</span>` : ""}</dd>`);

  if (sub.system) add("提交系统", esc(sub.system));
  if (acceptance && acceptance.display) {
    const scope = [acceptance.year, acceptance.scope].filter(Boolean).join(" ");
    add("录用率", `<span class="rate rate-lg">${esc(acceptance.display)}</span>`,
        [scope, acceptance.note].filter(Boolean).join(" · "));
  }
  if (sub.preprint) {
    const [text, tone] = PREPRINT[sub.preprint] || ["未知", ""];
    add("预印本", `<span class="sub-badge ${tone}">${text}</span>`, sub.preprint_note);
  }
  if (sub.code) {
    const [text, tone] = CODE[sub.code] || ["未知", ""];
    add("代码/数据", `<span class="sub-badge ${tone}">${text}</span>`, sub.code_note);
  }
  if (sub.access) add("获取方式", esc(ACCESS[sub.access] || sub.access), sub.apc_note);
  if (sub.attendance) add("参会形式", esc(ATTEND[sub.attendance] || sub.attendance));
  if (sub.rounds) add("审稿轮次", esc(sub.rounds));
  if (sub.acceptance_note && !(acceptance && acceptance.display)) add("录用参考", esc(sub.acceptance_note));

  $("#d-submission").innerHTML = rows.join("") || `<dt>—</dt><dd class="muted">未登记投稿须知</dd>`;
}

/* ------------------------------------------------------------------- drawer */
function openDrawer(venue) {
  state.selected = venue;
  $("#d-title").textContent = `${venue.abbr} ${venue.edition || ""}`.trim();
  $("#d-sub").textContent = venue.name;
  $("#d-watch").textContent = venue.watching ? "取消关注" : "加入关注";
  $("#d-status").value = venue.submit_status || "";
  $("#d-links").innerHTML = jumpLinks(venue, false);

  // manual verification form: kinds this venue has, prefilled with current values
  const kinds = (venue.deadlines || []).map((dl) => dl.kind);
  const uniq = [...new Set(kinds)];
  $("#mv-kind").innerHTML = (uniq.length ? uniq : ["full_paper", "abstract"])
    .map((k) => {
      const dl = (venue.deadlines || []).find((d) => d.kind === k) || {};
      return `<option value="${esc(k)}">${esc(dl.label || k)}（现 ${esc(dl.date || "—")}）</option>`;
    }).join("");
  const first = (venue.deadlines || [])[0] || {};
  $("#mv-date").value = first.date || "";
  $("#mv-url").value = (first.source && first.source.url) || venue.cfp_url || "";
  $("#mv-hint").textContent = uniq.length
    ? "填完会标记为「人工核验」并记录来源；之后自动核验不会覆盖它。"
    : "这个会议目前没有任何截止日期记录。";

  $("#d-deadlines").innerHTML = venue.deadlines.map((dl) => {
    const sm = statusMeta(dl.source_status);
    const when = dl.source_status === "scraped" ? "抓取于" : (dl.source_status === "unpublished" ? "查于" : "核验于");
    const src = dl.source && dl.source.checked_at ? `${when} ${dl.source.checked_at}` : "无来源记录";
    const stateLabel = dl.state === "passed" ? "已过" : `剩 ${dl.days_left} 天`;
    const whenCell = dl.approximate
      ? `<span class="approx">${esc(dl.fuzzy || "待定")}</span><span class="muted"> · 推测 ${esc(dl.date)}</span>`
      : `${esc(dl.date)} ${esc(dl.time)} ${esc(dl.tz)} → 北京 ${esc(dl.beijing || "—")}`;
    return `<li>
      <span class="kind">${esc(dl.label)}${dl.track ? ` <span class="track-tag">${esc(dl.track)}</span>` : ""}</span>
      <span class="when ${dl.approximate ? "approx" : ""}">${whenCell}</span>
      <span class="${dl.approximate ? "approx" : ""}">${stateLabel}</span>
      <span class="src"><span class="badge ${sm.cls}">${sm.text}</span> ${esc(src)}${dl.note ? " · " + esc(dl.note) : ""}</span>
    </li>`;
  }).join("") || `<li class="muted">无截止时间（滚动投稿）</li>`;

  $("#d-tracks").innerHTML = (venue.tracks || []).map((track) => {
    const kind = TRACK_KINDS[track.kind] || track.kind || "";
    return `<li><span class="track-kind ${esc(track.kind || "")}">${esc(kind)}</span>
      <span class="track-name">${esc(track.name)}</span>
      ${track.note ? `<span class="track-note">${esc(track.note)}</span>` : ""}</li>`;
  }).join("") || `<li class="muted">未登记赛道</li>`;

  $("#d-topics").innerHTML = (venue.topics || []).map((t) => `<span class="topic">${esc(t)}</span>`).join("")
    || `<span class="muted">未登记主题</span>`;

  renderSubmission(venue.submission || {}, venue.acceptance || {});

  $("#d-materials").innerHTML = (venue.materials || []).map((m) => `<li>${esc(m)}</li>`).join("")
    || `<li class="muted">未登记</li>`;

  const tier = venue.tier || {};
  $("#d-meta").innerHTML = [
    ["类型", venue.type === "journal" ? "期刊（滚动）" : "会议"],
    ["领域", (venue.areas || []).join(", ")],
    ["CCF", tier.ccf || "—"],
    ["中科院", tier.cas || "—"],
    ["页数", venue.page_limit || "—"],
    ["审稿", venue.blind === "double" ? "双盲" : venue.blind ? "单盲" : "—"],
    ["备注", venue.notes || "—"],
  ].map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("");

  const related = state.candidates.filter((c) => c.venue_id === venue.id);
  renderJournalInfo(venue);
  $("#d-candidates").hidden = related.length === 0;
  $("#d-candidate-list").innerHTML = related.map((c, i) => `<li>
      <strong>${esc(c.kind)}</strong> ${esc(c.date)} ${esc(c.time)} ${esc(c.tz)}
      <div class="snip">${esc(c.snippet || "")}</div>
      <div class="cand-actions"><button class="ghost" data-confirm="${i}">确认写入</button></div>
    </li>`).join("");
  $("#d-candidate-list").querySelectorAll("[data-confirm]").forEach((btn) => {
    btn.addEventListener("click", () => confirmCandidate(venue, related[Number(btn.dataset.confirm)]));
  });

  $("#drawer").hidden = false;
  $("#overlay").hidden = false;
}

function closeDrawer() {
  $("#drawer").hidden = true;
  if ($("#settings").hidden) $("#overlay").hidden = true;
  state.selected = null;
}

async function toggleWatch(venue) {
  const next = !venue.watching;
  await api(`/api/venues/${encodeURIComponent(venue.id)}/state`, {
    method: "PATCH", body: JSON.stringify({ watching: next }),
  });
  toast(next ? `已关注 ${venue.abbr}` : `已取消关注 ${venue.abbr}`);
  await loadAll();
  if (state.selected && state.selected.id === venue.id) {
    const fresh = state.allVenues.find((v) => v.id === venue.id);
    if (fresh) openDrawer(fresh);
  }
}

async function setSubmitStatus(venueId, value) {
  await api(`/api/venues/${encodeURIComponent(venueId)}/state`, {
    method: "PATCH", body: JSON.stringify({ submit_status: value }),
  });
  toast("状态已更新");
  await loadAll();
}

async function confirmCandidate(venue, cand) {
  await api(`/api/venues/${encodeURIComponent(venue.id)}/deadlines/${encodeURIComponent(cand.kind)}/confirm`, {
    method: "POST",
    body: JSON.stringify({ date: cand.date, time: cand.time, tz: cand.tz,
      source_url: cand.source_url, snippet: cand.snippet, note: "由抓取候选确认" }),
  });
  toast(`已确认 ${venue.abbr} ${cand.kind} ${cand.date}`);
  await loadAll();
  const fresh = state.allVenues.find((v) => v.id === venue.id);
  if (fresh) openDrawer(fresh);
}

/* ------------------------------------------------------------------- verify */
async function startVerify(venueIds) {
  if (state.verifying) return;
  try {
    await api("/api/verify", {
      method: "POST",
      body: JSON.stringify(venueIds ? { venue_ids: venueIds } : {}),
    });
    state.verifying = true;
    const btn = $("#btn-verify");
    if (btn) { btn.disabled = true; btn.textContent = "核验中…"; }
    toast(venueIds ? "正在核验该会议…" : "正在核验待复核条目…");
    pollVerify();
  } catch (err) {
    toast(`核验未启动：${err.message}`);
  }
}

async function pollVerify() {
  const btn = $("#btn-verify");
  try {
    const status = await api("/api/verify/status");
    if (status.running) {
      const p = status.progress || {};
      if (btn && p.total) btn.textContent = `核验中 ${p.done}/${p.total}`;
      setTimeout(pollVerify, 3000);
      return;
    }
    state.verifying = false;
    if (btn) { btn.disabled = false; btn.textContent = "核验"; }
    await loadAll();
    await loadRuns();
    await refreshSettings(true);
    toast("核验完成");
    await loadVerifyRun();
  } catch (err) {
    state.verifying = false;
    if (btn) { btn.disabled = false; btn.textContent = "核验"; }
  }
}

async function startJournalVerify() {
  const btn = $("#s-journal-verify");
  if (state.verifyingJournals) return;
  try {
    await api("/api/journals/verify", { method: "POST", body: "{}" });
    state.verifyingJournals = true;
    btn.disabled = true;
    btn.textContent = "核验中…";
    toast("期刊核验已开始（约 2-3 分钟）");
    pollJournalVerify();
  } catch (err) {
    toast(`期刊核验未启动：${err.message}`);
  }
}

async function pollJournalVerify() {
  const btn = $("#s-journal-verify");
  try {
    const status = await api("/api/journals/verify/status");
    if (status.running) {
      const p = status.progress || {};
      if (btn && p.total) btn.textContent = `核验中 ${p.done}/${p.total}`;
      setTimeout(pollJournalVerify, 2500);
      return;
    }
    state.verifyingJournals = false;
    btn.disabled = false;
    btn.textContent = "立即核验期刊";
    await loadAll();
    await refreshSettings(true);
    toast("期刊核验完成");
    const info = await api("/api/scrape/runs?limit=1&kind=journal-verify");
    const run = (info.runs || [])[0];
    if (run) {
      const s = run.summary || {};
      $("#s-journal-info").textContent = `身份 ${s.identity_verified || 0}/${s.targets || 0} · 指标 ${s.metrics_found || 0} · ${formatShort(run.started_at)}`;
    }
  } catch (err) {
    state.verifyingJournals = false;
    if (btn) { btn.disabled = false; btn.textContent = "立即核验期刊"; }
  }
}

async function loadVerifyRun() {
  try {
    const res = await api("/api/scrape/runs?limit=1&kind=verify");
    const run = (res.runs || [])[0];
    if (!run) return;
    const s = run.summary || {};
    const el = $("#verify-status");
    if (el) el.textContent = `最近核验 ${run.started_at} · 核对 ${s.verified || 0} · 更新 ${s.updated || 0} · 不一致 ${s.mismatch || 0}`;
  } catch (err) { /* optional */ }
}

/* -------------------------------------------------------------------- scrape */
async function startScrape() {
  if (state.scraping) return;
  try {
    await api("/api/scrape/run", { method: "POST", body: JSON.stringify({}) });
    state.scraping = true;
    const btn = $("#s-run-now");
    if (btn) { btn.disabled = true; btn.textContent = "抓取中…"; }
    toast("抓取已在后台开始");
    pollScrape();
  } catch (err) {
    toast(`抓取未启动：${err.message}`);
  }
}

async function pollScrape() {
  const btn = $("#s-run-now");
  try {
    const status = await api("/api/scrape/status");
    if (status.running) { setTimeout(pollScrape, 3000); return; }
    state.scraping = false;
    if (btn) { btn.disabled = false; btn.textContent = "立即抓取一次"; }
    await loadAll();
    await loadRuns();
    await refreshSettings(true);
    toast("抓取完成");
  } catch (err) {
    state.scraping = false;
    if (btn) { btn.disabled = false; btn.textContent = "立即抓取一次"; }
  }
}

function renderRuns(run) {
  if (!run) {
    $("#scrape-status").textContent = "尚无抓取记录 · 默认每天 09:00 自动抓取（可在设置里改）";
    return;
  }
  const s = run.summary || {};
  const codes = (s.error_codes || []).length ? ` · 失败码：${s.error_codes.join(", ")}` : "";
  const applied = s.auto_applied ? ` · 自动写入 ${s.auto_applied}` : "";
  const waiting = s.candidates_added ? ` · 待人工 ${s.candidates_added}` : "";
  $("#scrape-status").textContent =
    `最近抓取 ${run.started_at} · 目标 ${s.targets} · 成功 ${s.succeeded} · 失败 ${s.failed} · 候选 ${s.candidates}${applied}${waiting}${codes}`;
}

async function loadRuns() {
  try {
    const res = await api("/api/scrape/runs?limit=1&kind=scrape");
    renderRuns((res.runs || [])[0]);
  } catch (err) {
    $("#scrape-status").textContent = "抓取记录读取失败";
  }
}

async function loadChrome() {
  try {
    const health = await api("/api/health");
    $("#health-dot").className = "dot " + (health.ok ? "ok" : "bad");
    $("#health-dot").title = `服务正常 · ${health.venues} 条 · v${health.version}`;
    $("#meta-version").textContent = `v${health.version} · 端口 ${location.port}`;
    const rem = health.reminders || {};
    $("#reminder-status").textContent = rem.running
      ? `提醒已启用（${(rem.thresholds || []).join("/")} 天）` : "提醒未运行";
    const vs = health.verify_schedule || {};
    if (vs.enabled && vs.next_run && !state.verifying) {
      $("#verify-status").textContent = `自动核验：${vs.next_run}`;
    }
  } catch (err) {
    $("#health-dot").className = "dot bad";
  }
  await loadRuns();
}

/* ------------------------------------------------------------------ settings */
function fillSettings(s) {
  $("#s-auto").checked = !!s.scrape.auto;
  $("#s-time").value = s.scrape.daily_time || "09:00";
  $("#s-auto-apply").checked = !!s.scrape.auto_apply;
  $("#s-guard").value = s.scrape.auto_apply_guard_days;
  $("#s-protect").checked = !!s.scrape.protect_confirmed;
  $("#s-browser-fallback").checked = !!s.scrape.browser_fallback;
  $("#s-thresholds").value = (s.reminders.thresholds || []).join(",");
  $("#s-digest").value = s.reminders.digest_hour;
  $("#s-toast").checked = !!s.reminders.toast;

  const verify = s.verify || {};
  $("#s-verify").checked = !!verify.enabled;
  $("#s-verify-time").value = verify.daily_time || "10:00";
  $("#s-verify-shift").value = verify.max_shift_days ?? 30;
  $("#s-verify-pending").checked = !!verify.pending_only;

  const shortTs = (v) => (v || "").replace("T", " ").slice(0, 16);
  const sch = s.schedule || {};
  const info = [];
  if (sch.auto) info.push(`下次：${sch.next_run || "—"}`);
  else info.push("已关闭");
  if (sch.last_auto_at) info.push(`上次：${shortTs(sch.last_auto_at)}`);
  $("#s-schedule-info").textContent = info.join(" · ");

  const vs = s.verify_schedule || {};
  const vinfo = [];
  if (vs.enabled) vinfo.push(`下次：${vs.next_run || "—"}`);
  else vinfo.push("已关闭");
  if (vs.last_auto_at) vinfo.push(`上次：${(vs.last_auto_at || "").replace("T", " ").slice(0, 16)}`);
  $("#s-verify-info").textContent = vinfo.join(" · ");

  updateIcsLink();
}

function updateIcsLink() {
  const range = $("#s-ics-range").value || "365";
  $("#s-ics").href = `/api/ics?within=${encodeURIComponent(range)}`;
}

async function refreshSettings(silent) {
  try {
    const s = await api("/api/settings");
    fillSettings(s);
    return s;
  } catch (err) {
    if (!silent) toast(`设置读取失败：${err.message}`);
    return null;
  }
}

async function saveSettings() {
  const payload = {
    scrape: {
      auto: $("#s-auto").checked,
      daily_time: $("#s-time").value || "09:00",
      auto_apply: $("#s-auto-apply").checked,
      auto_apply_guard_days: Number($("#s-guard").value || 90),
      protect_confirmed: $("#s-protect").checked,
      browser_fallback: $("#s-browser-fallback").checked,
    },
    reminders: {
      thresholds: String($("#s-thresholds").value || "").split(/[,，\s]+/).filter(Boolean).map(Number),
      digest_hour: Number($("#s-digest").value || 9),
      toast: $("#s-toast").checked,
    },
    verify: {
      enabled: $("#s-verify").checked,
      daily_time: $("#s-verify-time").value || "10:00",
      max_shift_days: Number($("#s-verify-shift").value || 30),
      pending_only: $("#s-verify-pending").checked,
    },
  };
  try {
    const res = await api("/api/settings", { method: "PATCH", body: JSON.stringify(payload) });
    fillSettings(res.settings);
    $("#s-save-info").textContent = "已保存";
    toast("设置已保存");
  } catch (err) {
    $("#s-save-info").textContent = err.message;
    toast(`保存失败：${err.message}`);
  }
}

function openSettings() {
  $("#settings").hidden = false;
  $("#overlay").hidden = false;
  refreshSettings();
}

function closeSettings() {
  $("#settings").hidden = true;
  if ($("#drawer").hidden) $("#overlay").hidden = true;
}

/* -------------------------------------------------------------------- events */
function bindEvents() {
  document.querySelectorAll(".nav-tab").forEach((btn) => {
    btn.addEventListener("click", () => switchView(btn.dataset.view));
  });
  window.addEventListener("hashchange", () => switchView(location.hash.replace("#", ""), true));

  $("#btn-verify").addEventListener("click", () => startVerify());
  $("#s-journal-verify").addEventListener("click", () => startJournalVerify());
  $("#mv-submit").addEventListener("click", async () => {
    if (!state.selected) return;
    const kind = $("#mv-kind").value;
    const date = $("#mv-date").value;
    const url = $("#mv-url").value.trim();
    if (!date) { toast("请先选日期"); return; }
    try {
      await api(`/api/venues/${encodeURIComponent(state.selected.id)}/deadlines/${encodeURIComponent(kind)}/confirm`, {
        method: "POST",
        body: JSON.stringify({
          date, time: "23:59", tz: "AoE", source_url: url,
          note: "人工核验（用户在官网确认后录入）",
          snippet: "manual entry",
        }),
      });
      toast("已保存为人工核验");
      await loadAll();
      const fresh = state.allVenues.find((v) => v.id === state.selected.id);
      if (fresh) openDrawer(fresh);
    } catch (err) {
      toast(`保存失败：${err.message}`);
    }
  });
  $("#d-verify").addEventListener("click", () => {
    if (state.selected) startVerify([state.selected.id]);
  });

  $("#cal-mode").addEventListener("click", (event) => {
    const btn = event.target.closest(".scope-tab");
    if (!btn) return;
    document.querySelectorAll("#cal-mode .scope-tab").forEach((b) => b.classList.toggle("active", b === btn));
    state.calMode = btn.dataset.mode;
    renderCalendar();
  });

  $("#cal-scope").addEventListener("click", (event) => {
    const btn = event.target.closest(".scope-tab");
    if (!btn) return;
    state.calScope = btn.dataset.scope;
    document.querySelectorAll(".scope-tab").forEach((b) => b.classList.toggle("active", b === btn));
    renderCalendar();
  });

  document.querySelectorAll("#area-chips .chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      document.querySelectorAll("#area-chips .chip").forEach((c) => c.classList.remove("active"));
      chip.classList.add("active");
      state.filters.area = chip.dataset.area || "";
      loadAll().catch((err) => toast(err.message));
    });
  });

  $("#type-select").addEventListener("change", (e) => { state.filters.type = e.target.value; loadAll().catch((err) => toast(err.message)); });
  $("#within-select").addEventListener("change", (e) => { state.filters.within = e.target.value; loadAll().catch((err) => toast(err.message)); });
  $("#topic-select").addEventListener("change", (e) => { state.filters.topic = e.target.value; loadAll().catch((err) => toast(err.message)); });
  $("#show-passed").addEventListener("change", (e) => { state.filters.showPassed = e.target.checked; loadAll().catch((err) => toast(err.message)); });

  let timer = null;
  $("#search").addEventListener("input", (e) => {
    clearTimeout(timer);
    timer = setTimeout(() => { state.filters.q = e.target.value.trim(); loadAll().catch((err) => toast(err.message)); }, 220);
  });

  $("#btn-settings").addEventListener("click", openSettings);
  $("#s-close").addEventListener("click", closeSettings);
  $("#s-save").addEventListener("click", saveSettings);
  $("#s-run-now").addEventListener("click", startScrape);
  $("#s-ics-range").addEventListener("change", updateIcsLink);

  $("#d-close").addEventListener("click", closeDrawer);
  $("#overlay").addEventListener("click", () => { closeDrawer(); closeSettings(); });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { closeDrawer(); closeSettings(); hideDayPopover(); }
  });

  $("#year-select").addEventListener("change", (e) => { state.year = Number(e.target.value); renderCalendar(); });

  $("#year-calendar").addEventListener("click", (e) => {
    const cell = e.target.closest(".cal-day.has-events");
    if (!cell) return;
    showDayPopover(cell.dataset.day, cell);
  });

  $("#day-popover").addEventListener("click", (e) => {
    const item = e.target.closest("li[data-venue]");
    if (!item) return;
    const venue = state.allVenues.find((v) => v.id === item.dataset.venue);
    hideDayPopover();
    if (venue) openDrawer(venue);
  });

  document.addEventListener("click", (e) => {
    if (e.target.closest("#day-popover") || e.target.closest("#year-calendar")) return;
    hideDayPopover();
  });

  $("#d-watch").addEventListener("click", () => { if (state.selected) toggleWatch(state.selected); });
  $("#d-status").addEventListener("change", (e) => { if (state.selected) setSubmitStatus(state.selected.id, e.target.value); });
}

/* ---------------------------------------------------------------------- boot */
(async function boot() {
  bindEvents();
  try { await loadAll(); } catch (err) { toast(`加载失败：${err.message}`); }
  switchView(location.hash.replace("#", ""), true);
  await loadChrome();
  setInterval(loadChrome, 60000);
})();
