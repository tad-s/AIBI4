/**
 * app.js — AIBI4 V9 メインアプリ
 */
import * as api from "./api.js";
import { VoiceRecorder } from "./voice.js";

// ── 状態 ──
let sessionId = null;
let voiceRecorder = null;
let isRecording = false;
let selectedMonths = new Set();
let selectedStoreIds = new Set();
let allStores = [];
let currentDataset = "izakaya";

// ── DOM ──
const $ = id => document.getElementById(id);
const monthChips      = $("month-chips");
const storeSearch     = $("store-search");
const storeList       = $("store-list");
const storePreview    = $("store-preview");
const fetchBtn        = $("fetch-btn");
const pocBtn          = $("poc-btn");
const sbStatus        = $("sb-status");
const emptyState      = $("empty-state");
const fetchState      = $("fetch-state");
const fpBarFill       = $("fp-bar-fill");
const fpPct           = $("fp-pct");
const fpDetail        = $("fp-detail");
const fpRows          = $("fp-rows");
const fpMonths        = $("fp-months");
const loadedState     = $("loaded-state");
const infoRows        = $("info-rows");
const infoMonths      = $("info-months");
const infoStores      = $("info-stores");
const kpiBar          = $("kpi-bar");
const analysisGrid    = $("analysis-grid");
const skeletonGrid    = $("skeleton-grid");
const chatInput       = $("chat-input");
const chatSendBtn     = $("chat-send-btn");
const chatNewSendBtn  = $("chat-new-send-btn");
const clearChatBtn    = $("clear-chat-btn");
const voiceBtn        = $("voice-btn");
const chatGraphsArea  = $("chat-graphs-area");
const toastEl         = $("toast");
const datasetSelect   = $("dataset-select");
const exportBtn       = $("export-btn");
const evidenceBtn     = $("evidence-btn");
const pocCatBtn       = $("poc-cat-btn");
const catModal        = $("cat-modal");
const catModalBody    = $("cat-modal-body");
const drillModal      = $("drill-modal");
const drillModalBody  = $("drill-modal-body");
let pocMode           = false;   // PoC分析を表示中か（エビデンスDL/カテゴリ編集の分岐用）
const POC_CATEGORIES  = ["ドリンク","揚げ物","串","海鮮","鍋","サラダ","ヘビー","軽いつまみ","締め","デザート","その他"];

// ── ライトボックス ──
const imgModal      = $("img-modal");
const imgModalImg   = $("img-modal-img");
const imgModalTitle = $("img-modal-title");

function openLightbox(src, title) {
  imgModalImg.src       = src;
  imgModalTitle.textContent = title;
  imgModal.classList.add("open");
  document.body.style.overflow = "hidden";
}
function closeLightbox() {
  imgModal.classList.remove("open");
  document.body.style.overflow = "";
  imgModalImg.src = "";
}

$("img-modal-close").addEventListener("click", closeLightbox);
imgModal.querySelector(".img-modal-backdrop").addEventListener("click", closeLightbox);
document.addEventListener("keydown", e => { if (e.key === "Escape") closeLightbox(); });

// ── Toast ──
let toastTimer;
function showToast(msg, type = "info") {
  toastEl.textContent = msg;
  toastEl.className = `show ${type}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toastEl.className = ""; }, 4000);
}

// ── タブ切り替え ──
document.querySelectorAll(".tab").forEach(tab => {
  tab.addEventListener("click", () => {
    const target = tab.dataset.tab;
    document.querySelectorAll(".tab").forEach(t => t.classList.toggle("active", t === tab));
    document.querySelectorAll(".tab-panel").forEach(p => {
      p.classList.toggle("active", p.id === `tab-${target}`);
    });
  });
});

// ── 月チップ ──
function renderMonthChips(months) {
  monthChips.innerHTML = "";
  if (months.length === 0) {
    monthChips.innerHTML = '<span style="font-size:11px;color:var(--text-muted)">データなし</span>';
    return;
  }
  months.forEach(m => {
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.textContent = m;
    chip.title = m;
    chip.addEventListener("click", () => {
      if (selectedMonths.has(m)) {
        selectedMonths.delete(m);
        chip.classList.remove("selected");
      } else {
        selectedMonths.add(m);
        chip.classList.add("selected");
      }
    });
    monthChips.appendChild(chip);
  });
  // 直近2ヶ月をデフォルト選択
  const recent = months.slice(-2);
  monthChips.querySelectorAll(".chip").forEach(chip => {
    if (recent.includes(chip.textContent)) {
      chip.classList.add("selected");
      selectedMonths.add(chip.textContent);
    }
  });
}

// ── 店舗リスト ──
function renderStoreList(stores) {
  allStores = stores;
  _renderFilteredStores("");
}

function _renderFilteredStores(query) {
  storeList.innerHTML = "";
  const filtered = query
    ? allStores.filter(s => s.store_name.includes(query))
    : allStores;

  // 全店舗オプション
  const allItem = document.createElement("label");
  allItem.className = "store-item" + (selectedStoreIds.size === 0 ? " checked" : "");
  allItem.innerHTML = `<input type="checkbox" ${selectedStoreIds.size === 0 ? "checked" : ""}> 全店舗`;
  allItem.querySelector("input").addEventListener("change", e => {
    if (e.target.checked) {
      selectedStoreIds.clear();
      _updateStoreChecks();
    }
  });
  storeList.appendChild(allItem);

  filtered.forEach(s => {
    const item = document.createElement("label");
    item.className = "store-item" + (selectedStoreIds.has(s.store_id) ? " checked" : "");
    item.innerHTML = `<input type="checkbox" ${selectedStoreIds.has(s.store_id) ? "checked" : ""}> ${s.store_name}`;
    item.querySelector("input").addEventListener("change", e => {
      if (e.target.checked) {
        selectedStoreIds.add(s.store_id);
      } else {
        selectedStoreIds.delete(s.store_id);
      }
      _updateStoreChecks();
    });
    storeList.appendChild(item);
  });
  _updateStorePreview();
}

function _updateStoreChecks() {
  // 全店舗チェックボックスを同期
  const allCb = storeList.querySelector("input");
  if (allCb) allCb.checked = selectedStoreIds.size === 0;
  storeList.querySelectorAll(".store-item").forEach((item, i) => {
    if (i === 0) {
      item.classList.toggle("checked", selectedStoreIds.size === 0);
    } else {
      const s = allStores.find(s => item.textContent.includes(s.store_name));
      if (s) item.classList.toggle("checked", selectedStoreIds.has(s.store_id));
    }
  });
  _updateStorePreview();
}

function _updateStorePreview() {
  if (selectedStoreIds.size === 0) {
    storePreview.textContent = "全店舗が対象";
  } else {
    const names = [...selectedStoreIds]
      .map(id => allStores.find(s => s.store_id === id)?.store_name ?? id)
      .slice(0, 3);
    const rest = selectedStoreIds.size > 3 ? ` 他${selectedStoreIds.size - 3}店` : "";
    storePreview.textContent = names.join("、") + rest;
  }
}

storeSearch.addEventListener("input", e => _renderFilteredStores(e.target.value));

// ── スケルトンローダー ──
function showSkeletons(n = 6) {
  skeletonGrid.innerHTML = "";
  for (let i = 0; i < n; i++) {
    skeletonGrid.innerHTML += `
      <div class="skeleton-card">
        <div class="skeleton-header"></div>
        <div class="skeleton-body"></div>
        <div class="skeleton-footer"></div>
      </div>`;
  }
  skeletonGrid.style.display = "grid";
}

// ── グラフカード ──
function buildGraphCard(title, imageB64, insight, table, insights, advice, drill) {
  const card = document.createElement("div");
  card.className = "graph-card";

  // ヘッダー
  const header = document.createElement("div");
  header.className = "graph-header";
  // 分析番号を抽出 (例: "分析①" → "①")
  const numMatch = title.match(/[①②③④⑤⑥]/);
  if (numMatch) {
    const badge = document.createElement("span");
    badge.className = "analysis-num";
    badge.textContent = numMatch[0];
    header.appendChild(badge);
  }
  const titleSpan = document.createElement("span");
  titleSpan.textContent = title.replace(/分析[①②③④⑤⑥]\s*/, "").replace(/※.*$/, "").trim();
  header.appendChild(titleSpan);
  if (title.includes("ダミー")) {
    const badge = document.createElement("span");
    badge.style.cssText = "margin-left:auto;font-size:9px;color:var(--warn);background:rgba(243,156,18,.1);border:1px solid rgba(243,156,18,.3);border-radius:3px;padding:1px 5px;";
    badge.textContent = "参考イメージ";
    header.appendChild(badge);
  }
  card.appendChild(header);

  // グラフ画像（クリックで拡大）
  const img = document.createElement("img");
  img.src = `data:image/png;base64,${imageB64}`;
  img.alt = title;
  img.title = "クリックで拡大";
  img.addEventListener("click", () => openLightbox(img.src, title));
  card.appendChild(img);

  // 知見・アドバイス（2列レイアウト）または従来の insight 表示
  const md = t => t.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  if (insights && insights.length > 0) {
    const ia = document.createElement("div");
    ia.className = "insight-advice-block";

    const insCol = document.createElement("div");
    insCol.className = "ia-insights";
    const insLabel = document.createElement("div");
    insLabel.className = "ia-label";
    insLabel.textContent = "📌 読み取れる知見";
    insCol.appendChild(insLabel);
    const insList = document.createElement("ul");
    for (const line of insights) {
      const li = document.createElement("li");
      li.innerHTML = md(line);
      insList.appendChild(li);
    }
    insCol.appendChild(insList);
    ia.appendChild(insCol);

    if (advice && advice.length > 0) {
      const advCol = document.createElement("div");
      advCol.className = "ia-advice";
      const advLabel = document.createElement("div");
      advLabel.className = "ia-label";
      advLabel.textContent = "💼 アドバイス";
      advCol.appendChild(advLabel);
      const advList = document.createElement("ul");
      for (const line of advice) {
        const li = document.createElement("li");
        li.innerHTML = md(line);
        advList.appendChild(li);
      }
      advCol.appendChild(advList);
      ia.appendChild(advCol);
    }

    card.appendChild(ia);
  } else if (insight) {
    const ins = document.createElement("div");
    ins.className = "graph-insight";
    ins.innerHTML = "💡 " + md(insight);
    card.appendChild(ins);
  }

  // テーブル（折りたたみ）。ドリル可能なら既定で開く。
  if (table && table.length > 0) {
    const det = document.createElement("details");
    if (drill) det.open = true;
    const sum = document.createElement("summary");
    sum.textContent = drill
      ? `📋 集計データ（${table.length}行・各行の「${drill.label || "内訳"}」で詳細）`
      : `📋 集計データ（${table.length}行）`;
    det.appendChild(sum);
    const wrap = document.createElement("div");
    wrap.className = "table-wrap";
    wrap.appendChild(buildTable(table, drill));
    det.appendChild(wrap);
    card.appendChild(det);
  }

  return card;
}

function buildTable(rows, drill) {
  const t = document.createElement("table");
  t.className = "data-table";
  if (!rows.length) return t;
  const keys = Object.keys(rows[0]);
  const thead = t.createTHead();
  const tr = thead.insertRow();
  keys.forEach(k => { const th = document.createElement("th"); th.textContent = k; tr.appendChild(th); });
  if (drill) { const th = document.createElement("th"); th.textContent = "操作"; tr.appendChild(th); }
  const tbody = t.createTBody();
  rows.forEach(row => {
    const tr2 = tbody.insertRow();
    keys.forEach(k => {
      const td = tr2.insertCell();
      const v = row[k];
      if (typeof v === "number") {
        td.textContent = Number.isInteger(v) ? v.toLocaleString("ja-JP") : v.toFixed(2);
      } else {
        td.textContent = v ?? "";
      }
    });
    if (drill) {
      const td = tr2.insertCell();
      const btn = document.createElement("button");
      btn.className = "drill-btn";
      btn.textContent = drill.label || "内訳";
      const key = row[drill.col];
      btn.addEventListener("click", () => openDrill(drill.type, key));
      td.appendChild(btn);
    }
  });
  return t;
}

// ── ドリルダウン内訳モーダル ──
function closeDrill() { drillModal.classList.remove("open"); }

async function openDrill(type, value) {
  drillModal.classList.add("open");
  $("drill-modal-title").textContent = "内訳";
  $("drill-modal-sub").textContent = "";
  drillModalBody.innerHTML = '<div style="padding:24px;color:var(--text-muted);">読み込み中…</div>';
  try {
    if (type === "item_hours") {
      const d = await api.drillPocItemHours(value);
      $("drill-modal-title").textContent = `${value} の時間帯別`;
      $("drill-modal-sub").textContent = `PoC①母集団（2組以上・15品以上）での注文時刻別 数量。合計 ${d.total_qty.toLocaleString()} 点。`;
      renderDrillHours(d.hours);
    } else if (type === "category_pair") {
      const [a, b] = value.split("→").map(s => s.trim());
      const d = await api.drillPocPair(a, b);
      $("drill-modal-title").textContent = `${value} の商品ペア内訳`;
      $("drill-modal-sub").textContent = `このカテゴリペアを構成する具体的な商品ペア（上位${d.rows.length}）。`;
      renderDrillRows(d.rows);
    } else if (type === "category_seq3") {
      const [a, b, c] = value.split("→").map(s => s.trim());
      const d = await api.drillPocSeq3(a, b, c);
      $("drill-modal-title").textContent = `${value} の商品3連鎖内訳`;
      $("drill-modal-sub").textContent = `このカテゴリ3連鎖を構成する具体的な商品3連鎖（上位${d.rows.length}）。`;
      renderDrillRows(d.rows);
    }
  } catch (e) {
    drillModalBody.innerHTML = `<div style="padding:24px;color:var(--danger);">読み込みエラー: ${e.message}</div>`;
  }
}

function renderDrillRows(rows) {
  drillModalBody.innerHTML = "";
  if (!rows || !rows.length) {
    drillModalBody.innerHTML = '<div style="padding:24px;color:var(--text-muted);">該当する内訳がありません。</div>';
    return;
  }
  const wrap = document.createElement("div");
  wrap.className = "table-wrap";
  wrap.appendChild(buildTable(rows));
  drillModalBody.appendChild(wrap);
}

function renderDrillHours(hours) {
  drillModalBody.innerHTML = "";
  if (!hours || !hours.length) {
    drillModalBody.innerHTML = '<div style="padding:24px;color:var(--text-muted);">時間帯データがありません。</div>';
    return;
  }
  const max = Math.max(...hours.map(h => h.数量));
  const box = document.createElement("div");
  box.className = "hours-chart";
  hours.forEach(h => {
    const row = document.createElement("div");
    row.className = "hours-row";
    row.innerHTML =
      `<span class="hours-label">${h.時間帯}</span>` +
      `<span class="hours-bar-track"><span class="hours-bar" style="width:${max ? (h.数量 / max * 100) : 0}%"></span></span>` +
      `<span class="hours-val">${h.数量.toLocaleString()}点 <span class="hours-sub">/ ${h.卓数}卓</span></span>`;
    box.appendChild(row);
  });
  drillModalBody.appendChild(box);
}

if (drillModal) {
  $("drill-modal-close").addEventListener("click", closeDrill);
  drillModal.querySelector(".img-modal-backdrop").addEventListener("click", closeDrill);
  document.addEventListener("keydown", e => { if (e.key === "Escape") closeDrill(); });
}

function buildErrorCard(title, errorMsg) {
  const card = document.createElement("div");
  card.className = "graph-card";
  card.innerHTML = `<div class="graph-header">${title}</div><div class="graph-error">⚠️ ${errorMsg}</div>`;
  return card;
}

// ── KPI カード ──
function buildKpiCards(df_info) {
  // df_info は /sessions/{sid}/summary の返り値
  // 追加の KPI は分析結果から読む想定だが、ここではシンプルに行数・月数・店舗数
  kpiBar.innerHTML = "";
  const items = [
    { label: "データ件数",    value: (df_info.rows || 0).toLocaleString("ja-JP"), sub: "明細行数" },
    { label: "選択月数",      value: selectedMonths.size + " ヶ月",  sub: [...selectedMonths].join(" / ") },
    { label: "対象店舗",      value: (df_info.stores?.length || 0) + " 店", sub: "取得済み店舗数" },
    { label: "列数",          value: (df_info.columns?.length || 0) + " 列", sub: "分析可能な項目数" },
  ];
  items.forEach(item => {
    const card = document.createElement("div");
    card.className = "kpi-card";
    card.innerHTML = `
      <div class="kpi-label">${item.label}</div>
      <div class="kpi-value">${item.value}</div>
      <div class="kpi-sub">${item.sub}</div>`;
    kpiBar.appendChild(card);
  });
}

// ── 初期化 ──
async function init() {
  // セッション作成
  try {
    const { session_id } = await api.createSession();
    sessionId = session_id;
  } catch (e) {
    const msg = e.message || "サーバー未接続";
    showToast(msg, "error");
    monthChips.innerHTML = `<span style="font-size:11px;color:var(--danger)">⚠️ サーバー未接続</span>`;
    storeList.innerHTML = `<div style="font-size:11px;color:var(--danger);padding:6px 8px;">http://localhost:8000 で起動してください</div>`;
    return;
  }

  // 月チップ
  try {
    const { months } = await api.getMonths(currentDataset);
    renderMonthChips(months);
  } catch (e) {
    showToast(`月一覧の取得に失敗: ${e.message}`, "error");
    monthChips.innerHTML = `<span style="font-size:11px;color:var(--danger)">⚠️ 取得失敗</span>`;
  }

  // 店舗リスト
  try {
    const { stores } = await api.getStores(currentDataset);
    renderStoreList(stores);
  } catch (e) {
    showToast(`店舗一覧の取得に失敗: ${e.message}`, "error");
    storeList.innerHTML = `<div style="font-size:11px;color:var(--danger);padding:6px 8px;">取得失敗</div>`;
  }

  // データセット切り替え
  datasetSelect.addEventListener("change", async () => {
    currentDataset = datasetSelect.value;
    selectedMonths.clear();
    selectedStoreIds.clear();
    allStores = [];
    monthChips.innerHTML = '<span class="chip" style="pointer-events:none;opacity:.5">読み込み中…</span>';
    storeList.innerHTML = "";
    loadedState.style.display = "none";
    emptyState.style.display = "flex";
    sbStatus.classList.add("hidden");
    try {
      const { months } = await api.getMonths(currentDataset);
      renderMonthChips(months);
    } catch (e) {
      showToast(`月一覧の取得に失敗: ${e.message}`, "error");
    }
    try {
      const { stores } = await api.getStores(currentDataset);
      renderStoreList(stores);
    } catch (e) {
      showToast(`店舗一覧の取得に失敗: ${e.message}`, "error");
    }
  });

  // 音声サポート確認
  if (!VoiceRecorder.isSupported()) {
    voiceBtn.disabled = true;
    voiceBtn.title = "このブラウザは音声入力に対応していません";
  }

  fetchBtn.addEventListener("click", onFetchClick);
  chatSendBtn.addEventListener("click", () => onChatSend(false));
  chatNewSendBtn.addEventListener("click", () => onChatSend(true));
  clearChatBtn.addEventListener("click", onClearChat);
  voiceBtn.addEventListener("click", onVoiceClick);
  exportBtn.addEventListener("click", onExportExcel);
  evidenceBtn?.addEventListener("click", onExportEvidence);
  chatInput.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); onChatSend(false); }
  });
}

// ── セッション自動復旧（Railway再起動後のインメモリ消失に対応）──
async function ensureSession() {
  if (!sessionId) {
    const { session_id } = await api.createSession();
    sessionId = session_id;
    return;
  }
  // セッションの生死確認 (404 ならば再作成)
  const r = await fetch(`/api/sessions/${sessionId}/summary`);
  if (r.status === 404) {
    const { session_id } = await api.createSession();
    sessionId = session_id;
    showToast("セッションを再作成しました。", "info");
  }
}

// ── データ取得 ──
async function onFetchClick() {
  if (selectedMonths.size === 0) {
    showToast("分析期間を1ヶ月以上選択してください。", "warn");
    return;
  }

  const months = [...selectedMonths].sort();
  const storeIds = selectedStoreIds.size > 0 ? [...selectedStoreIds] : null;

  // セッション有効性確認
  try {
    await ensureSession();
  } catch (e) {
    showToast("セッション確立に失敗しました。ページをリロードしてください。", "error");
    return;
  }

  // UI リセット
  fetchBtn.disabled = true;
  exportBtn.disabled = true;
  if (evidenceBtn) evidenceBtn.disabled = true;
  exportBtn.textContent = "📥 Excelエクスポート";
  emptyState.style.display = "none";
  loadedState.style.display = "none";
  chatGraphsArea.innerHTML = "";
  analysisGrid.innerHTML = "";
  kpiBar.innerHTML = "";

  // ── メイン進捗パネルを表示 ──
  fetchState.style.display = "flex";
  fpBarFill.style.width = "0%";
  fpPct.textContent = "0%";
  fpDetail.textContent = "Supabase に接続中…";
  fpRows.textContent = "累計 0 件取得";

  // 月チップを進捗パネルに表示
  fpMonths.innerHTML = months.map(m =>
    `<span class="fp-month-chip" id="fpc-${m}">${m}</span>`
  ).join("");

  try {
    await api.fetchData(
      sessionId, months, storeIds, currentDataset,
      (done, total, rows, pct, month) => {
        if (done === null) {
          // processing イベント（整形・LLM サマリー生成中）
          fpBarFill.style.width = "100%";
          fpPct.textContent = "100%";
          fpDetail.textContent = `⏳ ${month}`;
          fpMonths.querySelectorAll(".fp-month-chip").forEach(c => c.classList.add("active"));
          return;
        }
        // progress イベント
        fpBarFill.style.width = `${pct}%`;
        fpPct.textContent = `${pct}%`;
        fpDetail.textContent = `${month} — ${done} / ${total} チャンク完了`;
        fpRows.textContent = `累計 ${rows.toLocaleString()} 件取得`;
        fpMonths.querySelectorAll(".fp-month-chip").forEach(c => c.classList.remove("active"));
        const chip = document.getElementById(`fpc-${month}`);
        if (chip) chip.classList.add("active");
      }
    );

    // 取得完了 → 進捗パネルを閉じてロード済み表示へ
    fpBarFill.style.width = "100%";
    fpPct.textContent = "100%";
    fpDetail.textContent = "✅ 取得完了 — 分析を実行中…";
    fpMonths.querySelectorAll(".fp-month-chip").forEach(c => c.classList.add("active"));

    await new Promise(r => setTimeout(r, 600)); // 完了を一瞬見せる

    fetchState.style.display = "none";
    sbStatus.classList.remove("hidden");

    // ロード済み状態へ
    loadedState.style.display = "flex";
    loadedState.style.flexDirection = "column";
    infoMonths.textContent = months.join(", ");
    infoStores.textContent = storeIds ? `${storeIds.length}店選択` : "全店舗";
    showSkeletons(12);
    analysisGrid.appendChild(skeletonGrid);

    // サマリー情報取得 → KPI
    const summary = await api.getSessionSummary(sessionId);
    infoRows.textContent = summary.rows?.toLocaleString() ?? "—";
    infoStores.textContent = summary.stores?.length ? `${summary.stores.length}店` : "全店舗";
    buildKpiCards(summary);

    // チャット有効化
    chatInput.disabled = false;
    chatSendBtn.disabled = false;
    chatNewSendBtn.disabled = false;
    voiceBtn.disabled = !VoiceRecorder.isSupported();

    showToast("データ取得完了！12項目の分析を実行中です。", "success");

    // 12項目分析
    await runBuiltinAnalysis();

  } catch (e) {
    showToast(`エラー: ${e.message}`, "error");
    fetchState.style.display = "none";
    emptyState.style.display = "flex";
  } finally {
    fetchBtn.disabled = false;
  }
}

// ── 12項目分析 ──
async function runBuiltinAnalysis() {
  pocMode = false;
  if (pocCatBtn) pocCatBtn.style.display = "none";
  try {
    const { analyses } = await api.runAnalysis(sessionId);

    // スケルトンをクリアしてグリッド再構築
    analysisGrid.innerHTML = "";
    analyses.forEach(a => {
      const card = a.image_b64
        ? buildGraphCard(a.title, a.image_b64, a.insight, a.table, a.insights, a.advice, a.drill)
        : buildErrorCard(a.title, a.insight || "グラフ生成エラー");
      analysisGrid.appendChild(card);
    });

    exportBtn.disabled = false;
    if (evidenceBtn) evidenceBtn.disabled = false;
    exportBtn.title = "分析結果をExcelにエクスポート";
    showToast("12項目の分析が完了しました。", "success");
  } catch (e) {
    analysisGrid.innerHTML = `<div style="grid-column:1/-1;padding:40px;text-align:center;color:var(--danger);">⚠️ 分析エラー: ${e.message}</div>`;
    showToast(`分析エラー: ${e.message}`, "error");
  }
}

// ── テング池袋東口店 PoC分析（ベース分析を差し替え表示）──
async function runPocAnalysisFlow() {
  const origLabel = "🍶 テング池袋東口店 PoC分析";
  try {
    pocBtn.disabled = true;
    pocBtn.textContent = "⏳ PoC分析中…（初回は1分ほど）";
    if (!sessionId) {
      const { session_id } = await api.createSession();
      sessionId = session_id;
    }
    // ロード済み状態＋分析タブへ切替
    emptyState.style.display = "none";
    fetchState.style.display = "none";
    loadedState.style.display = "flex";
    loadedState.style.flexDirection = "column";
    sbStatus.classList.remove("hidden");
    const analysisTab = document.querySelector('.tab[data-tab="analysis"]');
    if (analysisTab) analysisTab.click();

    kpiBar.innerHTML = "";
    analysisGrid.innerHTML = "";
    showSkeletons(5);
    analysisGrid.appendChild(skeletonGrid);
    showToast("テング池袋PoC分析を実行中…（生データからorder粒度で集計）", "success");

    const { analyses, meta } = await api.runPocAnalysis(sessionId);

    analysisGrid.innerHTML = "";
    const banner = document.createElement("div");
    banner.style.cssText =
      "grid-column:1/-1;padding:14px 18px;border-radius:12px;margin-bottom:4px;" +
      "background:linear-gradient(135deg,rgba(124,92,255,.10),rgba(91,155,213,.10));" +
      "border:1px solid rgba(124,92,255,.35);";
    banner.innerHTML =
      `<div style="font-weight:800;font-size:15px;">🍶 ${meta.store} レコメンドPoC</div>
       <div style="font-size:12px;color:var(--text-muted);margin-top:5px;line-height:1.6;">
         対象期間 <b>${meta.period}</b>／来店 <b>${meta.visits.toLocaleString()}</b>・
         オーダー <b>${meta.orders.toLocaleString()}</b>・明細 <b>${meta.items.toLocaleString()}</b><br>${meta.note}</div>`;
    analysisGrid.appendChild(banner);

    analyses.forEach(a => {
      const card = a.image_b64
        ? buildGraphCard(a.title, a.image_b64, a.insight, a.table, a.insights, a.advice, a.drill)
        : buildErrorCard(a.title, a.insight || "生成エラー");
      analysisGrid.appendChild(card);
    });

    if (exportBtn) { exportBtn.disabled = false; exportBtn.title = "分析結果をExcelにエクスポート"; }
    if (evidenceBtn) evidenceBtn.disabled = false;
    pocMode = true;
    if (pocCatBtn) pocCatBtn.style.display = "";   // カテゴリ内訳/編集ボタンを表示
    // PoCデータをもとにチャット分析できるよう入力を有効化
    chatInput.disabled = false;
    chatSendBtn.disabled = false;
    chatNewSendBtn.disabled = false;
    if (typeof VoiceRecorder !== "undefined") voiceBtn.disabled = !VoiceRecorder.isSupported();
    chatInput.placeholder = "PoCデータで分析…（例: カテゴリ別の販売数量、連続注文の傾向）";
    showToast("テング池袋PoC分析が完了しました。チャットでもPoCデータを分析できます。", "success");
  } catch (e) {
    showToast(`PoC分析エラー: ${e.message}`, "error");
    analysisGrid.innerHTML =
      `<div style="grid-column:1/-1;padding:40px;text-align:center;color:var(--danger);">⚠️ PoC分析エラー: ${e.message}</div>`;
  } finally {
    pocBtn.disabled = false;
    pocBtn.textContent = origLabel;
  }
}
if (pocBtn) pocBtn.addEventListener("click", runPocAnalysisFlow);

// ── PoC カテゴリ内訳/編集モーダル ──
function closeCatModal() { catModal.classList.remove("open"); }

async function loadCategoryBreakdown() {
  catModalBody.innerHTML = '<div style="padding:24px;color:var(--text-muted);">読み込み中…</div>';
  catModal.classList.add("open");
  try {
    const data = await api.getPocCategories();
    renderCategoryBreakdown(data.categories || []);
  } catch (e) {
    catModalBody.innerHTML = `<div style="padding:24px;color:var(--danger);">読み込みエラー: ${e.message}</div>`;
  }
}

function renderCategoryBreakdown(categories) {
  catModalBody.innerHTML = "";
  categories.forEach(cat => {
    const sec = document.createElement("div");
    sec.className = "cat-section";
    const head = document.createElement("button");
    head.className = "cat-head";
    head.innerHTML =
      `<span class="cat-caret">▸</span>` +
      `<span class="cat-name">${cat.category}<span class="cat-fd">${cat.fd}</span></span>` +
      `<span class="cat-stat">${cat.item_count}品 / 数量${Math.round(cat.total_qty).toLocaleString()} / 来店${cat.total_visits}</span>`;
    const list = document.createElement("div");
    list.className = "cat-items";
    list.style.display = "none";
    cat.items.forEach(it => {
      const row = document.createElement("div");
      row.className = "cat-item-row";
      const info = document.createElement("span");
      info.className = "cat-item-name";
      info.innerHTML = `${it.item_name} <span class="cat-item-qty">数量${Math.round(it.qty).toLocaleString()}・来店${it.visits}</span>`;
      const sel = document.createElement("select");
      sel.className = "cat-select";
      POC_CATEGORIES.forEach(c => {
        const o = document.createElement("option");
        o.value = c; o.textContent = c;
        if (c === cat.category) o.selected = true;
        sel.appendChild(o);
      });
      sel.addEventListener("change", () => onCategoryChange(it.item_name, sel.value));
      row.appendChild(info);
      row.appendChild(sel);
      list.appendChild(row);
    });
    head.addEventListener("click", () => {
      const open = list.style.display !== "none";
      list.style.display = open ? "none" : "block";
      head.querySelector(".cat-caret").textContent = open ? "▸" : "▾";
    });
    sec.appendChild(head);
    sec.appendChild(list);
    catModalBody.appendChild(sec);
  });
}

async function onCategoryChange(itemName, category) {
  if (!confirm(`「${itemName}」のカテゴリを「${category}」に変更し、PoC分析を再集計します。よろしいですか？\n（PoC専用テーブルのみ更新・原本は不変）`)) {
    loadCategoryBreakdown();   // 変更を取り消してUIを戻す
    return;
  }
  try {
    await api.overridePocCategory(itemName, category);
    showToast(`「${itemName}」を「${category}」に変更しました。再集計します。`, "success");
    closeCatModal();
    await runPocAnalysisFlow();   // テーブル更新を反映して再集計
  } catch (e) {
    showToast(`カテゴリ変更エラー: ${e.message}`, "error");
  }
}

if (pocCatBtn) pocCatBtn.addEventListener("click", loadCategoryBreakdown);
$("cat-modal-close").addEventListener("click", closeCatModal);
catModal.querySelector(".img-modal-backdrop").addEventListener("click", closeCatModal);
document.addEventListener("keydown", e => { if (e.key === "Escape") closeCatModal(); });

// ── Excel エクスポート ──

async function onExportEvidence() {
  if (!sessionId) return;
  if (evidenceBtn) {
    evidenceBtn.disabled = true;
    evidenceBtn.textContent = "⏳ 生成中…";
  }
  try {
    // PoC表示中は「原本CSV→変換→集計」の来歴テキストを、それ以外は従来のJSONを出す
    const poc = pocMode;
    const res = await fetch(poc
      ? `/api/poc/evidence/${sessionId}`
      : `/api/sessions/${sessionId}/evidence-log`);
    if (!res.ok) throw new Error(await res.text());
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const ymd = new Date().toISOString().slice(0,10).replaceAll("-","");
    a.href = url;
    a.download = poc ? `テング池袋PoC_エビデンス_${ymd}.txt`
                     : `AIBI4_V9_evidence_${ymd}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    showToast("エビデンスログをダウンロードしました。", "success");
  } catch (e) {
    showToast(`エビデンスログ出力エラー: ${e.message}`, "error");
  } finally {
    if (evidenceBtn) {
      evidenceBtn.disabled = false;
      evidenceBtn.textContent = "🧾 エビデンスログ";
    }
  }
}

async function onExportExcel() {
  if (!sessionId) return;
  exportBtn.disabled = true;
  exportBtn.textContent = "⏳ 生成中…";
  try {
    const resp = await fetch(`/api/sessions/${sessionId}/export`);
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }));
      throw new Error(err.detail || resp.statusText);
    }
    const blob = await resp.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href     = url;
    a.download = `AIBI4_${new Date().toISOString().slice(0,10)}.xlsx`;
    a.click();
    URL.revokeObjectURL(url);
    showToast("Excelファイルをダウンロードしました。", "success");
  } catch (e) {
    showToast(`エクスポートエラー: ${e.message}`, "error");
  } finally {
    exportBtn.disabled = false;
    exportBtn.textContent = "📥 Excelエクスポート";
  }
}

// ── チャット ──
async function onChatSend(newChat = false) {
  const message = chatInput.value.trim();
  if (!message) return;
  if (chatInput.disabled) {
    showToast("先にデータを取得してください。", "warn");
    return;
  }
  if (!sessionId) {
    showToast("セッションが切れています。ページを再読み込みしてください。", "warn");
    return;
  }

  chatInput.value = "";
  chatSendBtn.disabled = true;
  chatNewSendBtn.disabled = true;

  // チャットタブに自動切り替え
  document.querySelector(".tab[data-tab='chat']")?.click();

  // メインエリア（chatGraphsArea）にローディングエントリーを表示
  const emptyEl = chatGraphsArea.querySelector(".empty-state");
  if (emptyEl) emptyEl.remove();

  const loadingEntry = document.createElement("div");
  loadingEntry.className = "chat-entry";
  const loadingQ = document.createElement("div");
  loadingQ.className = "chat-entry-question";
  loadingQ.textContent = newChat ? `【新規チャット】${message}` : message;
  const loadingA = document.createElement("div");
  loadingA.className = "chat-entry-answer";
  loadingA.style.color = "var(--text-muted)";
  loadingA.innerHTML = '<span class="spinner"></span>&nbsp;LLM が分析中です…（最大2分）';
  loadingEntry.appendChild(loadingQ);
  loadingEntry.appendChild(loadingA);
  chatGraphsArea.appendChild(loadingEntry);
  loadingEntry.scrollIntoView({ behavior: "smooth", block: "start" });

  try {
    let result;
    try {
      result = await api.chat(sessionId, message, newChat);
    } catch (e) {
      // セッション切れ（Railway再起動）の場合はデータ再取得を促す
      if (e.message?.includes("セッションが見つかりません") || e.message?.includes("404")) {
        loadingA.innerHTML = "❌ セッションが切れています。データを再取得してください。";
        showToast("セッション切れ: データを再取得してください。", "warn");
        chatSendBtn.disabled = false;
        chatNewSendBtn.disabled = false;
        return;
      }
      throw e;
    }

    // ローディングエントリーを実際の結果エントリーに置き換え
    loadingEntry.remove();

    const entry = document.createElement("div");
    entry.className = "chat-entry";

    const qDiv = document.createElement("div");
    qDiv.className = "chat-entry-question";
    qDiv.textContent = newChat ? `【新規チャット】${message}` : message;
    entry.appendChild(qDiv);

    if (result.text) {
      const aDiv = document.createElement("div");
      aDiv.className = "chat-entry-answer";
      aDiv.innerHTML = result.text
        .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
        .replace(/\n/g, "<br>");
      entry.appendChild(aDiv);
    }

    if (result.graphs?.length) {
      const graphsDiv = document.createElement("div");
      graphsDiv.className = "chat-entry-graphs";
      result.graphs.forEach(g => {
        const cardNum = chatGraphsArea.querySelectorAll(".graph-card").length + 1;
        const label = `チャットグラフ ${cardNum}`;
        const card = g.image_b64
          ? buildGraphCard(label, g.image_b64, "", null)
          : buildErrorCard(label, g.error || "描画エラー");
        graphsDiv.appendChild(card);
      });
      entry.appendChild(graphsDiv);
    }

    chatGraphsArea.appendChild(entry);

    // グラフがあれば最初のグラフカードが見えるようにスクロール、なければエントリ先頭
    const firstGraph = entry.querySelector(".graph-card");
    if (firstGraph) {
      firstGraph.scrollIntoView({ behavior: "smooth", block: "nearest" });
    } else {
      entry.scrollIntoView({ behavior: "smooth", block: "start" });
    }

  } catch (e) {
    loadingA.innerHTML = `❌ ${e.message}`;
    showToast(`チャットエラー: ${e.message}`, "error");
  } finally {
    chatSendBtn.disabled = false;
    chatNewSendBtn.disabled = false;
  }
}


async function onClearChat() {
  if (!sessionId) return;
  try {
    await api.clearChat(sessionId);
    chatGraphsArea.innerHTML = `
      <div class="empty-state" style="padding:40px 0;grid-column:1/-1;">
        <div class="empty-icon" style="font-size:36px;opacity:.3;">💬</div>
        <div class="empty-desc">左パネルのチャットで分析を指示すると<br>回答とグラフがここに表示されます。</div>
      </div>`;
    showToast("チャット履歴をクリアしました。", "info");
  } catch (e) {
    showToast(`クリアエラー: ${e.message}`, "error");
  }
}

// ── 音声入力 ──
async function onVoiceClick() {
  if (!sessionId || chatInput.disabled) {
    showToast("先にデータを取得してください。", "warn");
    return;
  }

  if (!isRecording) {
    try {
      voiceRecorder = new VoiceRecorder();
      await voiceRecorder.start();
      isRecording = true;
      voiceBtn.classList.add("recording");
      voiceBtn.title = "録音中… もう一度クリックで停止";
      showToast("🎤 録音中… もう一度クリックで停止", "info");
    } catch (e) {
      showToast(`マイクエラー: ${e.message}`, "error");
    }
  } else {
    try {
      const blob = await voiceRecorder.stop();
      isRecording = false;
      voiceBtn.classList.remove("recording");
      voiceBtn.title = "音声入力";
      showToast("音声をテキストに変換中…", "info");
      const { text } = await api.transcribeAudio(sessionId, blob);
      if (text) {
        chatInput.value = (chatInput.value ? chatInput.value + " " : "") + text;
        chatInput.focus();
        showToast(`変換完了: 「${text}」`, "success");
      }
    } catch (e) {
      isRecording = false;
      voiceBtn.classList.remove("recording");
      showToast(`音声変換エラー: ${e.message}`, "error");
    }
  }
}

// ── 起動 ──
init();
