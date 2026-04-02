/**
 * app.js — AIBI4 V8 メインアプリケーション
 */
import * as api from "./api.js";
import { VoiceRecorder } from "./voice.js";

// ── 状態 ──
let sessionId = null;
let voiceRecorder = null;
let isRecording = false;

// ── DOM ──
const $ = id => document.getElementById(id);
const monthSelect    = $("month-select");
const storeSelect    = $("store-select");
const fetchBtn       = $("fetch-btn");
const progressArea   = $("progress-area");
const progressFill   = $("progress-fill");
const progressText   = $("progress-text");
const analysisArea   = $("analysis-area");
const chatSection    = $("chat-section");
const chatMessages   = $("chat-messages");
const chatInput      = $("chat-input");
const chatSendBtn    = $("chat-send-btn");
const clearChatBtn   = $("clear-chat-btn");
const voiceBtn       = $("voice-btn");
const chatGraphsArea = $("chat-graphs-area");
const toastEl        = $("toast");

// ── Toast ──
let toastTimer;
function showToast(msg, type = "info") {
  toastEl.textContent = msg;
  toastEl.className = `show ${type}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toastEl.className = ""; }, 3500);
}

// ── レンダリング: グラフカード ──
function renderGraphCard(title, imageB64, insight, table) {
  const card = document.createElement("div");
  card.className = "graph-card";

  const header = document.createElement("div");
  header.className = "graph-card-header";
  header.textContent = title;

  const img = document.createElement("img");
  img.src = `data:image/png;base64,${imageB64}`;
  img.alt = title;
  img.loading = "lazy";

  card.appendChild(header);
  card.appendChild(img);

  if (insight) {
    const ins = document.createElement("div");
    ins.className = "graph-card-insight";
    ins.innerHTML = insight.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    card.appendChild(ins);
  }

  if (table && table.length > 0) {
    const det = document.createElement("details");
    const sum = document.createElement("summary");
    sum.textContent = "📋 データテーブル";
    det.appendChild(sum);
    const div = document.createElement("div");
    div.appendChild(buildTable(table));
    det.appendChild(div);
    card.appendChild(det);
  }

  return card;
}

function buildTable(rows) {
  const t = document.createElement("table");
  t.className = "data-table";
  if (rows.length === 0) return t;
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
      td.textContent = typeof v === "number" ? v.toLocaleString("ja-JP", { maximumFractionDigits: 2 }) : (v ?? "");
    });
  });
  return t;
}

function renderErrorCard(title, errorMsg) {
  const card = document.createElement("div");
  card.className = "graph-card";
  card.innerHTML = `<div class="graph-card-header">${title}</div><div class="graph-error">⚠️ ${errorMsg}</div>`;
  return card;
}

// ── 初期化 ──
async function init() {
  // セッション作成
  try {
    const { session_id } = await api.createSession();
    sessionId = session_id;
  } catch (e) {
    showToast("セッション作成に失敗しました。サーバーを確認してください。", "error");
    return;
  }

  // 利用可能な月を取得
  try {
    const { months } = await api.getMonths();
    monthSelect.innerHTML = "";
    months.forEach(m => {
      const opt = document.createElement("option");
      opt.value = m;
      opt.textContent = m;
      monthSelect.appendChild(opt);
    });
    // 直近2ヶ月をデフォルト選択
    const recent = months.slice(-2);
    Array.from(monthSelect.options).forEach(o => {
      o.selected = recent.includes(o.value);
    });
  } catch (e) {
    showToast(`月一覧の取得に失敗: ${e.message}`, "error");
  }

  // 店舗一覧を取得
  try {
    const { stores } = await api.getStores();
    storeSelect.innerHTML = '<option value="">全店舗</option>';
    stores.forEach(s => {
      const opt = document.createElement("option");
      opt.value = s.store_id;
      opt.textContent = s.store_name;
      storeSelect.appendChild(opt);
    });
  } catch (e) {
    showToast(`店舗一覧の取得に失敗: ${e.message}`, "error");
  }

  // 音声入力サポート確認
  if (!VoiceRecorder.isSupported()) {
    voiceBtn.disabled = true;
    voiceBtn.title = "このブラウザは音声入力をサポートしていません";
  }

  // イベントリスナー登録
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
  const selectedMonths = Array.from(monthSelect.selectedOptions).map(o => o.value);
  if (selectedMonths.length === 0) {
    showToast("月を1つ以上選択してください。", "warn");
    return;
  }
  const selectedStoreIds = Array.from(storeSelect.selectedOptions)
    .map(o => o.value).filter(v => v !== "").map(Number);

  fetchBtn.disabled = true;
  progressArea.style.display = "flex";
  progressFill.style.width = "0%";
  progressText.textContent = "データ取得を開始します…";
  analysisArea.innerHTML = "";
  chatMessages.innerHTML = "";
  chatGraphsArea.innerHTML = "";
  chatSection.style.display = "none";

  try {
    await api.fetchData(
      sessionId,
      selectedMonths,
      selectedStoreIds.length > 0 ? selectedStoreIds : null,
      (done, total, rows, pct) => {
        progressFill.style.width = `${pct}%`;
        progressText.textContent = `📡 ${done}/${total} チャンク完了 (${pct}%) — 累計 ${rows.toLocaleString()} 件`;
      }
    );

    progressFill.style.width = "100%";
    progressText.textContent = "✅ データ取得完了。分析を実行中…";
    showToast("データ取得完了！分析を実行中です。", "success");

    // 6項目分析を自動実行
    await runBuiltinAnalysis();

    // チャット欄を表示
    chatSection.style.display = "block";

  } catch (e) {
    showToast(`エラー: ${e.message}`, "error");
    progressText.textContent = `❌ エラー: ${e.message}`;
  } finally {
    fetchBtn.disabled = false;
  }
}

// ── 6項目分析 ──
async function runBuiltinAnalysis() {
  analysisArea.innerHTML = `<div style="display:flex;align-items:center;gap:10px;padding:20px;">
    <span class="spinner"></span> 6項目の分析を実行中…
  </div>`;

  try {
    const { analyses } = await api.runAnalysis(sessionId);
    analysisArea.innerHTML = "";

    const header = document.createElement("div");
    header.className = "section-header";
    header.innerHTML = `<h2>🔬 ベース分析（6項目）</h2>`;
    analysisArea.appendChild(header);

    const grid = document.createElement("div");
    grid.className = "graph-grid";
    analyses.forEach(a => {
      const card = renderGraphCard(a.title, a.image_b64, a.insight, a.table);
      grid.appendChild(card);
    });
    analysisArea.appendChild(grid);
    showToast("6項目の分析が完了しました。", "success");
  } catch (e) {
    analysisArea.innerHTML = `<div class="empty-state"><div class="icon">⚠️</div><p>分析エラー: ${e.message}</p></div>`;
    showToast(`分析エラー: ${e.message}`, "error");
  }
}

// ── チャット ──
async function onChatSend() {
  const message = chatInput.value.trim();
  if (!message || !sessionId) return;

  appendMessage("user", message);
  chatInput.value = "";
  chatSendBtn.disabled = true;

  const loadingMsg = appendMessage("assistant", "🤔 分析中…");

  try {
    const result = await api.chat(sessionId, message);
    loadingMsg.remove();
    if (result.text) appendMessage("assistant", result.text);

    // グラフ表示
    if (result.graphs && result.graphs.length > 0) {
      const grid = document.createElement("div");
      grid.className = "graph-grid";
      result.graphs.forEach((g, i) => {
        if (g.image_b64) {
          grid.appendChild(renderGraphCard(`チャットグラフ ${i + 1}`, g.image_b64, "", null));
        } else if (g.error) {
          grid.appendChild(renderErrorCard(`グラフ ${i + 1}`, g.error));
        }
      });
      chatGraphsArea.appendChild(grid);
    }
  } catch (e) {
    loadingMsg.textContent = `❌ エラー: ${e.message}`;
    showToast(`チャットエラー: ${e.message}`, "error");
  } finally {
    chatSendBtn.disabled = false;
  }
}

function appendMessage(role, text) {
  const div = document.createElement("div");
  div.className = `msg msg-${role}`;
  div.innerHTML = text.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
                       .replace(/\n/g, "<br>");
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return div;
}

async function onClearChat() {
  if (!sessionId) return;
  await api.clearChat(sessionId);
  chatMessages.innerHTML = "";
  chatGraphsArea.innerHTML = "";
  showToast("チャット履歴をクリアしました。", "info");
}

// ── 音声入力 ──
async function onVoiceClick() {
  if (!sessionId) { showToast("先にデータを取得してください。", "warn"); return; }
  if (!isRecording) {
    try {
      voiceRecorder = new VoiceRecorder();
      await voiceRecorder.start();
      isRecording = true;
      voiceBtn.classList.add("recording");
      voiceBtn.title = "録音中…クリックで停止";
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
      showToast("音声を変換中…", "info");

      const { text } = await api.transcribeAudio(sessionId, blob);
      if (text) {
        chatInput.value = (chatInput.value ? chatInput.value + " " : "") + text;
        chatInput.focus();
        showToast(`音声変換完了: 「${text}」`, "success");
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
