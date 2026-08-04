const $ = (id) => document.getElementById(id);

const els = {
  buildBtn: $("build-btn"),
  analyzeBtn: $("analyze-btn"),
  exportBtn: $("export-btn"),
  summary: $("summary"),
  funnel: $("funnel"),
  toast: $("toast"),
};

els.buildBtn.addEventListener("click", () => buildBase(false));
els.analyzeBtn.addEventListener("click", analyze);
els.exportBtn.addEventListener("click", () => { window.location.href = "/api/export"; });
document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t === tab));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === tab.dataset.target));
  });
});

checkHealth();

async function checkHealth() {
  try {
    const res = await fetch("/api/health");
    if (!res.ok) throw new Error(await res.text());
    toast("T1 API 起動中");
  } catch (e) {
    toast(`APIエラー: ${clean(e)}`);
  }
}

async function buildBase(force) {
  setBusy(true);
  try {
    const json = await postJson("/api/build", { force });
    renderFunnel(json.funnel || []);
    toast(`基礎テーブル作成: ${json.summary.rows.toLocaleString()}行`);
  } catch (e) {
    toast(`作成エラー: ${clean(e)}`);
  } finally {
    setBusy(false);
  }
}

async function analyze() {
  setBusy(true);
  try {
    const result = await getJson("/api/analyze");
    renderSummary(result.summary);
    renderAnalysis1(result.analysis1);
    renderTable("a2-table", result.analysis2.rows, "co_order_count");
    renderTable("a3-table", result.analysis3.rows, "sequence_count");
    renderTable("a4-ff", result.analysis4.food_food, "recommend_score");
    renderTable("a4-dd", result.analysis4.drink_drink, "recommend_score");
    renderTable("a4-fd", result.analysis4.food_drink, "recommend_score");
    renderTable("a4-cat", result.analysis4.category_top5, "recommend_score");
    toast("分析完了");
  } catch (e) {
    toast(`分析エラー: ${clean(e)}`);
  } finally {
    setBusy(false);
  }
}

function renderSummary(s) {
  const metrics = [
    ["明細行", s.rows],
    ["来店数", s.visits],
    ["オーダー数", s.orders],
    ["商品数", s.items],
    ["2名以上来店", s.party2_visits],
    ["高注文卓", s.high_order_visits],
  ];
  els.summary.innerHTML = metrics.map(([label, value]) => `
    <div class="metric"><span class="metric-label">${esc(label)}</span><span class="metric-value">${Number(value).toLocaleString()}</span></div>
  `).join("");
}

function renderFunnel(rows) {
  if (!rows.length) return;
  els.funnel.classList.remove("hidden");
  els.funnel.innerHTML = `<h2>基礎テーブル作成ファネル</h2>${tableHtml(rows)}`;
}

function renderAnalysis1(a1) {
  renderTable("a1-overall", a1.overall, "total_qty");
  renderTable("a1-drink", a1.drink, "total_qty");
  renderTable("a1-food", a1.food, "total_qty");
}

function renderTable(id, rows, barKey) {
  $(id).innerHTML = tableHtml(rows || [], barKey);
}

function tableHtml(rows, barKey) {
  if (!rows || !rows.length) return `<p class="note">該当データがありません。</p>`;
  const headers = Object.keys(rows[0]);
  const max = barKey ? Math.max(...rows.map((r) => Number(r[barKey] || 0)), 1) : 0;
  return `<div class="table-wrap"><table>
    <thead><tr>${headers.map((h) => `<th>${esc(label(h))}</th>`).join("")}${barKey ? "<th>比較</th>" : ""}</tr></thead>
    <tbody>${rows.map((row) => `<tr>${headers.map((h) => `<td>${format(row[h])}</td>`).join("")}${barKey ? bar(row[barKey], max) : ""}</tr>`).join("")}</tbody>
  </table></div>`;
}

function bar(value, max) {
  const pct = Math.max(2, Number(value || 0) / max * 100);
  return `<td><div class="bar"><span style="width:${pct}%"></span></div></td>`;
}

async function getJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function postJson(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function setBusy(on) {
  els.buildBtn.disabled = on;
  els.analyzeBtn.disabled = on;
  els.exportBtn.disabled = on;
}

function toast(message) {
  els.toast.textContent = message;
  els.toast.classList.remove("hidden");
  setTimeout(() => els.toast.classList.add("hidden"), 2600);
}

function format(value) {
  if (value === null || value === undefined) return "";
  if (typeof value === "number") return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(2);
  return esc(String(value));
}

function label(key) {
  const labels = {
    item_name: "商品名",
    fd: "FD",
    category: "カテゴリ",
    total_qty: "数量",
    table_count: "卓数",
    order_count: "注文数",
    sales: "売上",
    qty_per_table: "卓あたり数量",
    pair: "ペア",
    pair_type: "種別",
    category_pair: "カテゴリペア",
    co_order_count: "同時注文数",
    sequence_count: "連続注文数",
    support_pct: "支持率%",
    recommend_score: "推薦スコア",
    recommendation: "推薦文",
    top_item_bonus: "TOP商品補正",
    rows: "行数",
    visits: "来店数",
    step: "ステップ",
  };
  return labels[key] || key;
}

function esc(value) {
  return String(value).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function clean(e) {
  return String(e?.message || e).replace(/^Error:\s*/, "").slice(0, 240);
}
