const $ = (id) => document.getElementById(id);

const els = {
  buildBtn: $("build-btn"),
  analyzeBtn: $("analyze-btn"),
  exportBtn: $("export-btn"),
  summary: $("summary"),
  categoryQuality: $("category-quality"),
  funnel: $("funnel"),
  toast: $("toast"),
};

let activeCategoryPairKey = "";
let activeQualityCategory = "";
let latestAnalysisResult = null;

const CATEGORY_CANDIDATES = [
  "ドリンク", "日本酒", "焼酎", "ワイン", "果実酒", "ソフトドリンク",
  "軽いつまみ", "揚げ物", "串", "巻き串", "海鮮", "肉料理", "ヘビー",
  "炒め物", "ピザ", "サラダ", "野菜料理", "鍋", "締め", "デザート",
  "逸品", "その他", "除外",
];
const DRINK_CATEGORIES = new Set(["ドリンク", "日本酒", "焼酎", "ワイン", "果実酒", "ソフトドリンク"]);

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
    latestAnalysisResult = result;
    renderSummary(result.summary);
    renderAnalysis1(result.analysis1);
    renderTable("a2-table", result.analysis2.rows, "co_order_count");
    renderTable("a3-table", result.analysis3.rows, "sequence_count");
    renderTable("a4-ff", result.analysis4.food_food, "recommend_score");
    renderTable("a4-dd", result.analysis4.drink_drink, "recommend_score");
    renderTable("a4-fd", result.analysis4.food_drink, "recommend_score");
    renderCategoryTop5(result.analysis4);
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
    ["その他数量", s.other_qty],
    ["その他比率", `${Number(s.other_share_pct || 0).toFixed(2)}%`],
  ];
  els.summary.innerHTML = metrics.map(([label, value]) => `
    <div class="metric"><span class="metric-label">${esc(label)}</span><span class="metric-value">${formatMetric(value)}</span></div>
  `).join("");
  renderCategoryQuality(s);
}

function renderCategoryQuality(s) {
  const categoryRows = dictToRows(s.category_counts || {}, "category", "total_qty")
    .map((row) => ({ ...row, item_count: (s.category_items?.[row.category] || []).length }));
  const selected = activeQualityCategory && categoryRows.some((row) => row.category === activeQualityCategory)
    ? activeQualityCategory
    : (categoryRows[0]?.category || "");
  activeQualityCategory = selected;
  els.categoryQuality.classList.remove("hidden");
  els.categoryQuality.innerHTML = `
    <h2>カテゴリ分類品質</h2>
    <p class="note">左のカテゴリ行をクリックすると、右側に含まれる商品内訳を表示します。カテゴリが誤っている商品は右側で補正して保存できます。</p>
    <div class="grid2 compact">
      <div>
        <h3>カテゴリ数量</h3>
        ${categoryQualityTable(categoryRows)}
      </div>
      <div>
        <div id="quality-category-items"></div>
      </div>
    </div>
  `;
  els.categoryQuality.querySelectorAll("[data-quality-category]").forEach((row) => {
    row.addEventListener("click", () => {
      activeQualityCategory = row.dataset.qualityCategory;
      renderCategoryQuality(s);
    });
  });
  renderQualityCategoryItems(s);
}

function categoryQualityTable(rows) {
  if (!rows.length) return `<p class="note">該当データがありません。</p>`;
  const max = Math.max(...rows.map((row) => Number(row.total_qty || 0)), 1);
  return `<div class="table-wrap"><table>
    <thead><tr><th>カテゴリ</th><th>数量</th><th>商品数</th><th>比較</th></tr></thead>
    <tbody>${rows.map((row) => `<tr class="clickable-row ${row.category === activeQualityCategory ? "selected-row" : ""}" data-quality-category="${escAttr(row.category)}">
      <td>${format(row.category)}</td>
      <td>${format(row.total_qty)}</td>
      <td>${format(row.item_count)}</td>
      ${bar(row.total_qty, max)}
    </tr>`).join("")}</tbody>
  </table></div>`;
}

function renderQualityCategoryItems(s) {
  const target = $("quality-category-items");
  if (!target) return;
  const category = activeQualityCategory;
  const rows = (s.category_items || {})[category] || [];
  const categoryOptions = mergedCategoryOptions(s);
  const totalQty = rows.reduce((sum, row) => sum + Number(row.total_qty || 0), 0);
  target.innerHTML = `
    <h3>${esc(category)} の商品内訳</h3>
    <p class="note">${rows.length.toLocaleString()}商品 / 数量 ${totalQty.toLocaleString()}。カテゴリ欄を編集して保存すると補正マスタに反映します。</p>
    ${categoryItemsEditTable(rows, category, categoryOptions)}
  `;
  target.querySelectorAll("[data-category-select]").forEach((select) => {
    select.addEventListener("change", () => syncFdForCategory(select));
  });
  target.querySelectorAll("[data-save-category]").forEach((button) => {
    button.addEventListener("click", () => saveCategoryOverride(button));
  });
}

function mergedCategoryOptions(s) {
  const existing = Object.keys(s.category_items || {});
  return [...new Set([...CATEGORY_CANDIDATES, ...existing])];
}

function categoryItemsEditTable(rows, currentCategory, categoryOptions) {
  if (!rows.length) return `<p class="note">該当データがありません。</p>`;
  const max = Math.max(...rows.map((row) => Number(row.total_qty || 0)), 1);
  return `<div class="table-wrap category-edit-wrap"><table>
    <thead><tr>
      <th>商品名</th><th>数量</th><th>卓数</th><th>売上</th><th>構成比%</th><th>カテゴリ編集</th><th>FD</th><th>保存</th><th>比較</th>
    </tr></thead>
    <tbody>${rows.map((row, idx) => {
      const rowId = `cat-edit-${idx}`;
      return `<tr>
        <td>${format(row.item_name)}</td>
        <td>${format(row.total_qty)}</td>
        <td>${format(row.table_count)}</td>
        <td>${format(row.sales)}</td>
        <td>${format(row.share_in_category_pct)}</td>
        <td><select class="category-input" id="${rowId}-category" data-category-select="${rowId}">
          ${categoryOptions.map((option) => `<option value="${escAttr(option)}"${option === currentCategory ? " selected" : ""}>${esc(option)}</option>`).join("")}
        </select></td>
        <td><select class="fd-select" id="${rowId}-fd">
          <option value="フード"${row.fd === "フード" ? " selected" : ""}>フード</option>
          <option value="ドリンク"${row.fd === "ドリンク" ? " selected" : ""}>ドリンク</option>
        </select></td>
        <td><button class="mini-btn" data-save-category="${rowId}" data-item-name="${escAttr(row.item_name)}">保存</button></td>
        ${bar(row.total_qty, max)}
      </tr>`;
    }).join("")}</tbody>
  </table></div>`;
}

function syncFdForCategory(select) {
  const rowId = select.dataset.categorySelect;
  const fdSelect = $(`${rowId}-fd`);
  if (!fdSelect) return;
  fdSelect.value = DRINK_CATEGORIES.has(select.value) ? "ドリンク" : "フード";
}

async function saveCategoryOverride(button) {
  const rowId = button.dataset.saveCategory;
  const itemName = button.dataset.itemName;
  const category = $(`${rowId}-category`)?.value;
  const fd = $(`${rowId}-fd`)?.value;
  if (!itemName || !category) {
    toast("商品名またはカテゴリが空です");
    return;
  }
  button.disabled = true;
  try {
    await postJson("/api/category-override", { item_name: itemName, category, fd, note: "画面から編集" });
    toast(`カテゴリ保存: ${itemName} → ${category}`);
    const result = await getJson("/api/analyze");
    latestAnalysisResult = result;
    renderSummary(result.summary);
    renderAnalysis1(result.analysis1);
    renderTable("a2-table", result.analysis2.rows, "co_order_count");
    renderTable("a3-table", result.analysis3.rows, "sequence_count");
    renderTable("a4-ff", result.analysis4.food_food, "recommend_score");
    renderTable("a4-dd", result.analysis4.drink_drink, "recommend_score");
    renderTable("a4-fd", result.analysis4.food_drink, "recommend_score");
    renderCategoryTop5(result.analysis4);
  } catch (e) {
    toast(`保存エラー: ${clean(e)}`);
  } finally {
    button.disabled = false;
  }
}

function dictToRows(obj, keyName, valueName) {
  return Object.entries(obj).map(([key, value]) => ({ [keyName]: key, [valueName]: value }));
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

function renderCategoryTop5(a4) {
  const rows = a4.category_top5 || [];
  const drilldown = a4.category_top5_drilldown || {};
  const target = $("a4-cat");
  if (!rows.length) {
    target.innerHTML = `<p class="note">該当データがありません。</p>`;
    $("a4-cat-drilldown").innerHTML = "";
    return;
  }
  if (!Object.keys(drilldown).length) {
    target.innerHTML = `${tableHtml(rows, "recommend_score")}<p class="note warning-note">ドリルダウンデータがAPIから返っていません。T1を再起動してから再度「分析実行」を押してください。</p>`;
    $("a4-cat-drilldown").innerHTML = "";
    return;
  }
  const firstKey = rows[0].category_pair_key || rows[0].category_pair;
  if (!activeCategoryPairKey || !drilldown[activeCategoryPairKey]) {
    activeCategoryPairKey = firstKey;
  }
  const maxScore = Math.max(...rows.map((row) => Number(row.recommend_score || 0)), 1);
  target.innerHTML = `<div class="table-wrap"><table>
    <thead><tr>
      <th>カテゴリペア</th><th>連続注文数</th><th>卓数</th><th>支持率%</th><th>推薦スコア</th><th>比較</th><th>操作</th>
    </tr></thead>
    <tbody>${rows.map((row) => {
      const key = row.category_pair_key || row.category_pair;
      const selected = key === activeCategoryPairKey;
      return `<tr class="${selected ? "selected-row" : ""}">
        <td>${format(row.category_pair)}</td>
        <td>${format(row.sequence_count)}</td>
        <td>${format(row.table_count)}</td>
        <td>${format(row.support_pct)}</td>
        <td>${format(row.recommend_score)}</td>
        ${bar(row.recommend_score, maxScore)}
        <td><button class="mini-btn" data-category-pair-key="${escAttr(key)}">内訳を見る</button></td>
      </tr>`;
    }).join("")}</tbody>
  </table></div>`;
  target.querySelectorAll("[data-category-pair-key]").forEach((button) => {
    button.addEventListener("click", () => {
      activeCategoryPairKey = button.dataset.categoryPairKey;
      renderCategoryTop5(a4);
    });
  });
  renderCategoryPairDrilldown(a4);
}

function renderCategoryPairDrilldown(a4) {
  const rows = a4.category_top5 || [];
  const selected = rows.find((row) => (row.category_pair_key || row.category_pair) === activeCategoryPairKey) || rows[0];
  const key = selected?.category_pair_key || selected?.category_pair || "";
  const details = (a4.category_top5_drilldown || {})[key] || [];
  $("a4-cat-drilldown").innerHTML = `
    <div class="drilldown-panel">
      <h3>${esc(selected?.category_pair || "")} の商品ペア内訳</h3>
      <p class="note">このカテゴリペアに含まれる、具体的な連続注文の商品ペア上位20件です。</p>
      ${tableHtml(details, "recommend_score")}
    </div>
  `;
}

function renderTable(id, rows, barKey) {
  $(id).innerHTML = tableHtml(rows || [], barKey);
}

function tableHtml(rows, barKey) {
  if (!rows || !rows.length) return `<p class="note">該当データがありません。</p>`;
  const headers = Object.keys(rows[0]).filter((key) => !key.endsWith("_key"));
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

function formatMetric(value) {
  if (typeof value === "string" && value.endsWith("%")) return esc(value);
  if (value === null || value === undefined || value === "") return "";
  const num = Number(value);
  if (Number.isFinite(num)) return num.toLocaleString();
  return esc(String(value));
}

function label(key) {
  const labels = {
    item_name: "商品名",
    fd: "FD",
    category: "カテゴリ",
    item_count: "商品数",
    total_qty: "数量",
    table_count: "卓数",
    order_count: "注文数",
    sales: "売上",
    qty_per_table: "卓あたり数量",
    avg_unit_price: "平均単価",
    share_in_category_pct: "カテゴリ内比率%",
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

function escAttr(value) {
  return esc(value).replace(/`/g, "&#96;");
}

function clean(e) {
  return String(e?.message || e).replace(/^Error:\s*/, "").slice(0, 240);
}
