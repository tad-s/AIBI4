/**
 * app.js — AIBI4 V8.1 メインアプリ
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

// ── DOM ──
const $ = id => document.getElementById(id);
const monthChips      = $("month-chips");
const storeSearch     = $("store-search");
const storeList       = $("store-list");
const storePreview    = $("store-preview");
const fetchBtn        = $("fetch-btn");
const progressWrap    = $("progress-wrap");
const progressFill    = $("progress-fill");
const progressText    = $("progress-text");
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
const chatMsgs        = $("chat-msgs");
const chatInput       = $("chat-input");
const chatSendBtn     = $("chat-send-btn");
const clearChatBtn    = $("clear-chat-btn");
const voiceBtn        = $("voice-btn");
const chatGraphsArea  = $("chat-graphs-area");
const toastEl         = $("toast");

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
function buildGraphCard(title, imageB64, insight, table) {
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

  // グラフ画像
  const img = document.createElement("img");
  img.src = `data:image/png;base64,${imageB64}`;
  img.alt = title;
  img.loading = "lazy";
  card.appendChild(img);

  // インサイト
  if (insight) {
    const ins = document.createElement("div");
    ins.className = "graph-insight";
    ins.innerHTML = "💡 " + insight.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    card.appendChild(ins);
  }

  // テーブル（折りたたみ）
  if (table && table.length > 0) {
    const det = document.createElement("details");
    const sum = document.createElement("summary");
    sum.textContent = `📋 集計データ（${table.length}行）`;
    det.appendChild(sum);
    const wrap = document.createElement("div");
    wrap.className = "table-wrap";
    wrap.appendChild(buildTable(table));
    det.appendChild(wrap);
    card.appendChild(det);
  }

  return card;
}

function buildTable(rows) {
  const t = document.createElement("table");
  t.className = "data-table";
  if (!rows.length) return t;
  const keys = Object.keys(rows[0]);
  const thead = t.createTHead();
  const tr = thead.insertRow();
  keys.forEach(k => { const th = document.createElement("th"); th.textContent = k; tr.appendChild(th); });
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
  });
  return t;
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
    const { months } = await api.getMonths();
    renderMonthChips(months);
  } catch (e) {
    showToast(`月一覧の取得に失敗: ${e.message}`, "error");
    monthChips.innerHTML = `<span style="font-size:11px;color:var(--danger)">⚠️ 取得失敗</span>`;
  }

  // 店舗リスト
  try {
    const { stores } = await api.getStores();
    renderStoreList(stores);
  } catch (e) {
    showToast(`店舗一覧の取得に失敗: ${e.message}`, "error");
    storeList.innerHTML = `<div style="font-size:11px;color:var(--danger);padding:6px 8px;">取得失敗</div>`;
  }

  // 音声サポート確認
  if (!VoiceRecorder.isSupported()) {
    voiceBtn.disabled = true;
    voiceBtn.title = "このブラウザは音声入力に対応していません";
  }

  fetchBtn.addEventListener("click", onFetchClick);
  chatSendBtn.addEventListener("click", onChatSend);
  clearChatBtn.addEventListener("click", onClearChat);
  voiceBtn.addEventListener("click", onVoiceClick);
  chatInput.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); onChatSend(); }
  });
}

// ── データ取得 ──
async function onFetchClick() {
  if (selectedMonths.size === 0) {
    showToast("分析期間を1ヶ月以上選択してください。", "warn");
    return;
  }

  const months = [...selectedMonths].sort();
  const storeIds = selectedStoreIds.size > 0 ? [...selectedStoreIds] : null;

  // UI リセット
  fetchBtn.disabled = true;
  emptyState.style.display = "none";
  loadedState.style.display = "none";
  chatMsgs.innerHTML = "";
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

  // サイドバーのプログレスバーも更新
  progressWrap.classList.remove("hidden");
  progressFill.style.width = "0%";
  progressText.textContent = "接続中…";

  try {
    await api.fetchData(
      sessionId, months, storeIds,
      (done, total, rows, pct, month) => {
        if (done === null) {
          // processing イベント（整形・LLM サマリー生成中）
          fpBarFill.style.width = "100%";
          fpPct.textContent = "100%";
          fpDetail.textContent = `⏳ ${month}`;
          fpMonths.querySelectorAll(".fp-month-chip").forEach(c => c.classList.add("active"));
          progressFill.style.width = "100%";
          progressText.textContent = month;
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
        progressFill.style.width = `${pct}%`;
        progressText.textContent = `${done}/${total} チャンク完了 (${pct}%)`;
      }
    );

    // 取得完了 → 進捗パネルを閉じてロード済み表示へ
    fpBarFill.style.width = "100%";
    fpPct.textContent = "100%";
    fpDetail.textContent = "✅ 取得完了 — 分析を実行中…";
    fpMonths.querySelectorAll(".fp-month-chip").forEach(c => c.classList.add("active"));
    progressFill.style.width = "100%";
    progressText.textContent = "✅ 取得完了";

    await new Promise(r => setTimeout(r, 600)); // 完了を一瞬見せる

    fetchState.style.display = "none";
    sbStatus.classList.remove("hidden");

    // ロード済み状態へ
    loadedState.style.display = "flex";
    loadedState.style.flexDirection = "column";
    infoMonths.textContent = months.join(", ");
    infoStores.textContent = storeIds ? `${storeIds.length}店選択` : "全店舗";
    showSkeletons(6);
    analysisGrid.appendChild(skeletonGrid);

    // サマリー情報取得 → KPI
    const summary = await api.getSessionSummary(sessionId);
    infoRows.textContent = summary.rows?.toLocaleString() ?? "—";
    infoStores.textContent = summary.stores?.length ? `${summary.stores.length}店` : "全店舗";
    buildKpiCards(summary);

    // チャット有効化
    chatInput.disabled = false;
    chatSendBtn.disabled = false;
    voiceBtn.disabled = !VoiceRecorder.isSupported();

    showToast("データ取得完了！6項目の分析を実行中です。", "success");

    // 6項目分析
    await runBuiltinAnalysis();

  } catch (e) {
    showToast(`エラー: ${e.message}`, "error");
    fetchState.style.display = "none";
    emptyState.style.display = "flex";
  } finally {
    fetchBtn.disabled = false;
    setTimeout(() => progressWrap.classList.add("hidden"), 3000);
  }
}

// ── 6項目分析 ──
async function runBuiltinAnalysis() {
  try {
    const { analyses } = await api.runAnalysis(sessionId);

    // スケルトンをクリアしてグリッド再構築
    analysisGrid.innerHTML = "";
    analyses.forEach(a => {
      const card = a.image_b64
        ? buildGraphCard(a.title, a.image_b64, a.insight, a.table)
        : buildErrorCard(a.title, a.insight || "グラフ生成エラー");
      analysisGrid.appendChild(card);
    });

    showToast("6項目の分析が完了しました。", "success");
  } catch (e) {
    analysisGrid.innerHTML = `<div style="grid-column:1/-1;padding:40px;text-align:center;color:var(--danger);">⚠️ 分析エラー: ${e.message}</div>`;
    showToast(`分析エラー: ${e.message}`, "error");
  }
}

// ── チャット ──
async function onChatSend() {
  const message = chatInput.value.trim();
  if (!message || !sessionId) return;
  if (chatInput.disabled) {
    showToast("先にデータを取得してください。", "warn");
    return;
  }

  appendMsg("user", message);
  chatInput.value = "";
  chatSendBtn.disabled = true;

  const loadingMsg = appendMsg("assistant", '<span class="spinner"></span> 分析中…');

  // チャットタブに自動切り替え
  document.querySelector(".tab[data-tab='chat']")?.click();

  try {
    const result = await api.chat(sessionId, message);
    loadingMsg.remove();
    if (result.text) appendMsg("assistant", result.text);

    if (result.graphs?.length) {
      // チャットグラフエリアの empty state を消す
      const empty = chatGraphsArea.querySelector(".empty-state");
      if (empty) empty.remove();

      result.graphs.forEach((g, i) => {
        const label = `チャットグラフ ${chatGraphsArea.querySelectorAll(".graph-card").length + 1}`;
        const card = g.image_b64
          ? buildGraphCard(label, g.image_b64, "", null)
          : buildErrorCard(label, g.error || "描画エラー");
        chatGraphsArea.appendChild(card);
      });
    }
  } catch (e) {
    loadingMsg.innerHTML = `❌ ${e.message}`;
    showToast(`チャットエラー: ${e.message}`, "error");
  } finally {
    chatSendBtn.disabled = false;
  }
}

function appendMsg(role, html) {
  const div = document.createElement("div");
  div.className = `msg msg-${role}`;
  div.innerHTML = typeof html === "string"
    ? html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/\n/g, "<br>")
    : html;
  chatMsgs.appendChild(div);
  chatMsgs.scrollTop = chatMsgs.scrollHeight;
  return div;
}

async function onClearChat() {
  if (!sessionId) return;
  try {
    await api.clearChat(sessionId);
    chatMsgs.innerHTML = "";
    chatGraphsArea.innerHTML = `
      <div class="empty-state" style="padding:40px 0;grid-column:1/-1;">
        <div class="empty-icon" style="font-size:36px;opacity:.3;">💬</div>
        <div class="empty-desc">左パネルのチャットで分析を指示すると<br>グラフがここに表示されます。</div>
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
