const $ = (id) => document.getElementById(id);

const state = {
  sessionId: null,
  dataset: "izakaya",
  datasets: [],
  months: [],
  stores: [],
  selectedMonths: new Set(),
  selectedStoreIds: new Set(),
  catalog: { metrics: [], dimensions: [] },
  history: [],
};

const els = {
  apiStatus: $("api-status"),
  sessionStatus: $("session-status"),
  datasetSelect: $("dataset-select"),
  monthChips: $("month-chips"),
  storeSearch: $("store-search"),
  storeList: $("store-list"),
  demoBtn: $("demo-btn"),
  loadBtn: $("load-btn"),
  progress: $("load-progress"),
  progressBar: $("progress-bar"),
  progressText: $("progress-text"),
  kpiGrid: $("kpi-grid"),
  dashboardGrid: $("dashboard-grid"),
  refreshDashboardBtn: $("refresh-dashboard-btn"),
  askInput: $("ask-input"),
  askSendBtn: $("ask-send-btn"),
  askNewBtn: $("ask-new-btn"),
  askResults: $("ask-results"),
  assistantLog: $("assistant-log"),
  clearHistoryBtn: $("clear-history-btn"),
  metricSelect: $("metric-select"),
  dim1Select: $("dim1-select"),
  dim2Select: $("dim2-select"),
  chartSelect: $("chart-select"),
  runQueryBtn: $("run-query-btn"),
  exploreResult: $("explore-result"),
  metricCatalog: $("metric-catalog"),
  dimensionCatalog: $("dimension-catalog"),
  toast: $("toast"),
};

init().catch((e) => showError(e));

async function init() {
  bindEvents();
  await checkHealth();
  await Promise.all([loadDatasets(), loadCatalog()]);
  await loadDatasetMeta();
}

function bindEvents() {
  document.querySelectorAll(".nav").forEach((btn) => {
    btn.addEventListener("click", () => showPage(btn.dataset.page));
  });
  els.datasetSelect.addEventListener("change", async () => {
    state.dataset = els.datasetSelect.value;
    state.selectedMonths.clear();
    state.selectedStoreIds.clear();
    await loadDatasetMeta();
  });
  els.storeSearch.addEventListener("input", renderStores);
  els.demoBtn.addEventListener("click", startDemo);
  els.loadBtn.addEventListener("click", loadFromSupabase);
  els.refreshDashboardBtn.addEventListener("click", renderDashboard);
  els.askSendBtn.addEventListener("click", () => ask(false));
  els.askNewBtn.addEventListener("click", () => ask(true));
  els.clearHistoryBtn.addEventListener("click", clearHistory);
  els.runQueryBtn.addEventListener("click", runExplore);
}

function showPage(page) {
  document.querySelectorAll(".nav").forEach((b) => b.classList.toggle("active", b.dataset.page === page));
  document.querySelectorAll(".page").forEach((p) => p.classList.toggle("active", p.id === `page-${page}`));
}

async function checkHealth() {
  const json = await apiGet("/api/health");
  els.apiStatus.textContent = `API ${json.version}`;
}

async function loadDatasets() {
  const json = await apiGet("/api/datasets");
  state.datasets = json.datasets || [];
  els.datasetSelect.innerHTML = state.datasets.map((d) => `<option value="${esc(d.id)}">${esc(d.label)}</option>`).join("");
  els.datasetSelect.value = state.dataset;
}

async function loadCatalog() {
  state.catalog = await apiGet("/api/catalog");
  renderCatalog();
  fillExploreSelects();
}

async function loadDatasetMeta() {
  renderMonthsLoading();
  renderStoresLoading();
  const [monthsRes, storesRes] = await Promise.allSettled([
    apiGet(`/api/months?dataset=${encodeURIComponent(state.dataset)}`),
    apiGet(`/api/stores?dataset=${encodeURIComponent(state.dataset)}`),
  ]);

  if (monthsRes.status === "fulfilled") {
    state.months = monthsRes.value.months || [];
    state.months.slice(-2).forEach((m) => state.selectedMonths.add(m));
  } else {
    state.months = [];
    els.monthChips.textContent = `月一覧エラー: ${cleanError(monthsRes.reason)}`;
  }

  if (storesRes.status === "fulfilled") {
    state.stores = storesRes.value.stores || [];
  } else {
    state.stores = [];
    els.storeList.textContent = `店舗一覧エラー: ${cleanError(storesRes.reason)}`;
  }
  renderMonths();
  renderStores();
}

function renderMonthsLoading() {
  els.monthChips.innerHTML = `<span class="muted-box">月一覧を読み込み中</span>`;
}

function renderStoresLoading() {
  els.storeList.innerHTML = `<span class="muted-box">店舗一覧を読み込み中</span>`;
}

function renderMonths() {
  if (!state.months.length) {
    els.monthChips.innerHTML = `<span class="muted-box">月が見つかりません。デモデータは月選択不要です。</span>`;
    return;
  }
  els.monthChips.innerHTML = state.months.map((m) => (
    `<button class="chip ${state.selectedMonths.has(m) ? "active" : ""}" data-month="${esc(m)}">${esc(m)}</button>`
  )).join("");
  els.monthChips.querySelectorAll(".chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const month = chip.dataset.month;
      state.selectedMonths.has(month) ? state.selectedMonths.delete(month) : state.selectedMonths.add(month);
      renderMonths();
    });
  });
}

function renderStores() {
  const q = els.storeSearch.value.trim().toLowerCase();
  const filtered = state.stores.filter((s) => String(s.store_name || "").toLowerCase().includes(q)).slice(0, 80);
  if (!filtered.length) {
    els.storeList.innerHTML = `<span class="muted-box">店舗が見つかりません</span>`;
    return;
  }
  els.storeList.innerHTML = filtered.map((s) => {
    const id = Number(s.store_id);
    return `<label class="store-check"><input type="checkbox" value="${id}" ${state.selectedStoreIds.has(id) ? "checked" : ""}>${esc(s.store_name || id)}</label>`;
  }).join("");
  els.storeList.querySelectorAll("input").forEach((input) => {
    input.addEventListener("change", () => {
      const id = Number(input.value);
      input.checked ? state.selectedStoreIds.add(id) : state.selectedStoreIds.delete(id);
    });
  });
}

async function startDemo() {
  setBusy(true, "デモデータを生成中…", 20);
  try {
    const json = await apiPost("/api/sessions/demo", { dataset: state.dataset });
    state.sessionId = json.session_id;
    els.sessionStatus.textContent = `Demo ${json.meta.order_rows.toLocaleString()}伝票`;
    setBusy(false);
    toast("デモデータを読み込みました");
    await renderDashboard();
  } catch (e) {
    setBusy(false);
    showError(e);
  }
}

async function loadFromSupabase() {
  if (!state.selectedMonths.size) {
    toast("Supabase読込では月を1つ以上選択してください");
    return;
  }
  setBusy(true, "セッション作成中…", 5);
  try {
    const session = await apiPost("/api/sessions", { dataset: state.dataset });
    state.sessionId = session.session_id;
    await streamLoad();
    const meta = await apiGet(`/api/sessions/${state.sessionId}/meta`);
    els.sessionStatus.textContent = `${meta.meta.order_rows.toLocaleString()}伝票 / ${meta.meta.item_rows.toLocaleString()}明細`;
    setBusy(false);
    await renderDashboard();
  } catch (e) {
    setBusy(false);
    showError(e);
  }
}

async function streamLoad() {
  const body = {
    session_id: state.sessionId,
    dataset: state.dataset,
    months: [...state.selectedMonths],
    store_ids: [...state.selectedStoreIds],
  };
  const res = await fetch("/api/load", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop();
    for (const part of parts) {
      const line = part.replace(/^data:\s*/, "").trim();
      if (!line) continue;
      const ev = JSON.parse(line);
      if (ev.type === "progress") setBusy(true, `${ev.done}/${ev.total} 取得中: ${ev.rows.toLocaleString()}行`, ev.pct);
      if (ev.type === "processing") setBusy(true, ev.message, 100);
      if (ev.type === "error") throw new Error(ev.message);
    }
  }
}

async function renderDashboard() {
  if (!state.sessionId) {
    toast("先にデータを読み込んでください");
    return;
  }
  els.kpiGrid.innerHTML = skeleton(6);
  els.dashboardGrid.innerHTML = skeleton(4);
  try {
    const json = await apiPost(`/api/sessions/${state.sessionId}/dashboard`, { global_filters: globalFilters() });
    els.kpiGrid.innerHTML = (json.kpis || []).map(renderKpi).join("");
    els.dashboardGrid.innerHTML = (json.tiles || []).map(renderChartCard).join("");
    showPage("home");
  } catch (e) {
    showError(e);
  }
}

async function ask(newChat) {
  const message = els.askInput.value.trim();
  if (!message) return;
  if (!state.sessionId) {
    toast("先にデータを読み込んでください");
    return;
  }
  if (newChat) state.history = [];
  addLog("user", newChat ? `【新規】${message}` : message);
  els.askInput.value = "";
  showPage("ask");
  els.askResults.querySelector(".empty")?.remove();
  const loading = appendResult(`<div class="chart-card"><div class="chart-body">AIが分析仕様を作成中…</div></div>`);
  try {
    const json = await apiPost(`/api/sessions/${state.sessionId}/ask`, {
      message,
      global_filters: globalFilters(),
      history: state.history,
    });
    loading.remove();
    state.history.push({ role: "user", content: message });
    state.history.push({ role: "assistant", content: json.message || "" });
    addLog("assistant", json.message || json.action);
    if (json.action !== "query") {
      appendResult(messageCard(json.action, json.message));
      return;
    }
    appendResult(messageCard("answer", json.message));
    appendResult(renderChartCard(json.result, true));
  } catch (e) {
    loading.remove();
    showError(e);
  }
}

async function runExplore() {
  if (!state.sessionId) {
    toast("先にデータを読み込んでください");
    return;
  }
  const dimensions = [els.dim1Select.value, els.dim2Select.value].filter(Boolean);
  const spec = {
    metric: els.metricSelect.value,
    dimensions,
    filters: {},
    chart_type: els.chartSelect.value,
    sort: dimensions.includes("month") || dimensions.includes("hour") || dimensions.includes("dow") ? "dim_asc" : "value_desc",
    limit: 20,
  };
  els.exploreResult.innerHTML = skeleton(1);
  try {
    const json = await apiPost(`/api/sessions/${state.sessionId}/query`, { spec, global_filters: globalFilters() });
    els.exploreResult.innerHTML = renderChartCard(json, true);
    showPage("explore");
  } catch (e) {
    showError(e);
  }
}

function globalFilters() {
  const selectedStoreNames = state.stores
    .filter((s) => state.selectedStoreIds.has(Number(s.store_id)))
    .map((s) => s.store_name);
  return {
    months: [...state.selectedMonths],
    stores: selectedStoreNames,
    categories: [],
    customer_layers: [],
    weather: [],
    dow: [],
    hour_min: null,
    hour_max: null,
  };
}

function renderKpi(result) {
  const row = result.rows?.[0];
  const value = row ? formatValue(row.value, result.metric) : "-";
  return `<div class="kpi"><div class="kpi-label">${esc(result.metric.label)}</div><div class="kpi-value">${esc(value)}</div></div>`;
}

function renderChartCard(result, includeDetails = false) {
  if (!result) return "";
  const rows = result.rows || [];
  const chart = result.spec?.chart_type || "bar";
  const chartHtml = chart === "table"
    ? renderTable(result)
    : `<svg class="chart-svg" viewBox="0 0 760 260" role="img">${renderSvg(result)}</svg>${renderTable(result)}`;
  const details = includeDetails ? `<div class="details"><strong>Generated SQL</strong><pre>${esc(result.sql || "")}</pre></div>` : "";
  return `<article class="chart-card">
    <div class="chart-head">
      <h3 class="chart-title">${esc(result.title || result.metric?.label || "分析結果")}</h3>
      <span class="chart-meta">${rows.length} rows</span>
    </div>
    <div class="chart-body">${chartHtml}</div>
    ${details}
  </article>`;
}

function renderSvg(result) {
  const rows = (result.rows || []).slice(0, 24);
  if (!rows.length) return `<text x="24" y="132" fill="#91899d">データがありません</text>`;
  const values = rows.map((r) => Number(r.value || 0));
  const max = Math.max(...values, 1);
  const labels = rows.map((r) => r.dim0 ?? result.metric.label);
  const chart = result.spec?.chart_type || "bar";
  if (chart === "line" || chart === "area") return svgLine(rows, values, labels, max, result.metric);
  return svgBar(rows, values, labels, max, result.metric);
}

function svgBar(rows, values, labels, max, metric) {
  const w = 700, h = 190, x0 = 42, y0 = 210;
  const gap = 6;
  const bw = Math.max(8, (w - gap * (rows.length - 1)) / rows.length);
  return [
    `<line x1="${x0}" y1="18" x2="${x0}" y2="${y0}" stroke="#e4ded2"/>`,
    `<line x1="${x0}" y1="${y0}" x2="742" y2="${y0}" stroke="#e4ded2"/>`,
    ...rows.map((r, i) => {
      const bh = (values[i] / max) * h;
      const x = x0 + i * (bw + gap);
      const y = y0 - bh;
      return `<rect x="${x}" y="${y}" width="${bw}" height="${bh}" rx="5" fill="#5b4be7"/>
        <text x="${x + bw / 2}" y="238" text-anchor="middle" font-size="10" fill="#5a526b">${esc(short(labels[i]))}</text>
        <text x="${x + bw / 2}" y="${Math.max(14, y - 6)}" text-anchor="middle" font-size="10" fill="#5a526b">${esc(formatValue(values[i], metric, true))}</text>`;
    }),
  ].join("");
}

function svgLine(rows, values, labels, max, metric) {
  const x0 = 44, y0 = 210, w = 680, h = 184;
  const pts = values.map((v, i) => {
    const x = x0 + (rows.length === 1 ? w / 2 : (i / (rows.length - 1)) * w);
    const y = y0 - (v / max) * h;
    return [x, y];
  });
  const path = pts.map((p, i) => `${i ? "L" : "M"}${p[0]},${p[1]}`).join(" ");
  return [
    `<line x1="${x0}" y1="18" x2="${x0}" y2="${y0}" stroke="#e4ded2"/>`,
    `<line x1="${x0}" y1="${y0}" x2="742" y2="${y0}" stroke="#e4ded2"/>`,
    `<path d="${path}" fill="none" stroke="#1476b8" stroke-width="3"/>`,
    ...pts.map((p, i) => `<circle cx="${p[0]}" cy="${p[1]}" r="4" fill="#1476b8"/>
      <text x="${p[0]}" y="${Math.max(14, p[1] - 8)}" text-anchor="middle" font-size="10" fill="#5a526b">${esc(formatValue(values[i], metric, true))}</text>
      <text x="${p[0]}" y="238" text-anchor="middle" font-size="10" fill="#5a526b">${esc(short(labels[i]))}</text>`),
  ].join("");
}

function renderTable(result) {
  const rows = result.rows || [];
  if (!rows.length) return "";
  const dims = result.dimensions || [];
  const headers = [...dims.map((d) => d.label), result.metric?.label || "値"];
  const body = rows.map((r) => `<tr>${dims.map((_, i) => `<td>${esc(r[`dim${i}`])}</td>`).join("")}<td>${esc(formatValue(r.value, result.metric))}</td></tr>`).join("");
  return `<div class="table-wrap"><table><thead><tr>${headers.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>${body}</tbody></table></div>`;
}

function renderCatalog() {
  els.metricCatalog.innerHTML = (state.catalog.metrics || []).map((m) => (
    `<div class="catalog-item"><strong>${esc(m.label)} <code>${esc(m.id)}</code></strong><span>${esc(m.description || "")}</span></div>`
  )).join("");
  els.dimensionCatalog.innerHTML = (state.catalog.dimensions || []).map((d) => (
    `<div class="catalog-item"><strong>${esc(d.label)} <code>${esc(d.id)}</code></strong><span>${esc((d.views || []).join(" / "))}</span></div>`
  )).join("");
}

function fillExploreSelects() {
  els.metricSelect.innerHTML = (state.catalog.metrics || []).map((m) => `<option value="${esc(m.id)}">${esc(m.label)}</option>`).join("");
  const dimOptions = [`<option value="">なし</option>`].concat((state.catalog.dimensions || []).map((d) => `<option value="${esc(d.id)}">${esc(d.label)}</option>`));
  els.dim1Select.innerHTML = dimOptions.join("");
  els.dim2Select.innerHTML = dimOptions.join("");
  els.metricSelect.value = "revenue";
  els.dim1Select.value = "store";
}

function messageCard(type, message) {
  const label = type === "clarify" ? "確認が必要" : type === "impossible" ? "実行不可" : "AI回答";
  return `<article class="chart-card"><div class="chart-head"><h3 class="chart-title">${label}</h3></div><div class="chart-body">${esc(message || "").replace(/\n/g, "<br>")}</div></article>`;
}

function appendResult(html) {
  const wrap = document.createElement("div");
  wrap.innerHTML = html;
  const node = wrap.firstElementChild;
  els.askResults.prepend(node);
  return node;
}

function addLog(role, text) {
  const div = document.createElement("div");
  div.className = `log-item ${role}`;
  div.innerHTML = `<strong>${role === "user" ? "User" : "Assistant"}</strong>${esc(text).replace(/\n/g, "<br>")}`;
  els.assistantLog.prepend(div);
}

function clearHistory() {
  state.history = [];
  els.assistantLog.innerHTML = "";
  els.askResults.innerHTML = `<div class="empty"><strong>履歴をクリアしました。</strong><span>次の質問は新しい文脈で開始できます。</span></div>`;
  toast("チャット履歴をクリアしました");
}

async function apiGet(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function apiPost(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function setBusy(on, text = "", pct = 0) {
  els.demoBtn.disabled = on;
  els.loadBtn.disabled = on;
  els.progress.classList.toggle("hidden", !on);
  els.progressBar.style.width = `${Math.max(0, Math.min(100, pct))}%`;
  els.progressText.textContent = text;
}

function skeleton(n) {
  return Array.from({ length: n }, () => `<div class="chart-card"><div class="chart-body">読み込み中…</div></div>`).join("");
}

function formatValue(value, metric = {}, compact = false) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  const num = Number(value);
  if (metric.fmt === "pct") return `${(num * 100).toFixed(1)}%`;
  if (metric.fmt === "yen") return compact ? `${Math.round(num / 1000).toLocaleString()}千` : `${Math.round(num).toLocaleString()}円`;
  if (metric.fmt === "float1") return `${num.toFixed(1)}${metric.unit || ""}`;
  return `${Math.round(num).toLocaleString()}${metric.unit || ""}`;
}

function short(v) {
  const s = String(v ?? "");
  return s.length > 8 ? `${s.slice(0, 8)}…` : s;
}

function toast(message) {
  els.toast.textContent = message;
  els.toast.classList.remove("hidden");
  setTimeout(() => els.toast.classList.add("hidden"), 2600);
}

function showError(e) {
  const msg = cleanError(e);
  console.error(e);
  toast(msg);
}

function cleanError(e) {
  return String(e?.message || e).replace(/^Error:\s*/, "").slice(0, 220);
}

function esc(v) {
  return String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
