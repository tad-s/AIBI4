/**
 * api.js — バックエンド API の薄いラッパー
 */
const BASE = "";  // 同一オリジンで配信されるため空文字

export async function getMonths() {
  const r = await fetch(`${BASE}/api/months`);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function getStores() {
  const r = await fetch(`${BASE}/api/stores`);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function createSession() {
  const r = await fetch(`${BASE}/api/sessions`, { method: "POST" });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function getSessionSummary(sid) {
  const r = await fetch(`${BASE}/api/sessions/${sid}/summary`);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

/**
 * データ取得（SSE）
 * onProgress(done, total, rows, pct) が呼ばれる。
 * 完了時に { rows, columns } を resolve。
 */
export function fetchData(sid, months, storeIds, onProgress) {
  return new Promise((resolve, reject) => {
    fetch(`${BASE}/api/fetch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sid, months, store_ids: storeIds }),
    }).then(res => {
      if (!res.ok) { res.text().then(t => reject(new Error(t))); return; }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      function pump() {
        reader.read().then(({ done, value }) => {
          if (done) { resolve({}); return; }
          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split("\n\n");
          buffer = parts.pop();
          for (const part of parts) {
            const line = part.replace(/^data: /, "").trim();
            if (!line) continue;
            try {
              const ev = JSON.parse(line);
              if (ev.type === "progress") onProgress(ev.done, ev.total, ev.rows, ev.pct);
              if (ev.type === "error") reject(new Error(ev.message));
              if (ev.type === "done") resolve(ev);
            } catch {}
          }
          pump();
        }).catch(reject);
      }
      pump();
    }).catch(reject);
  });
}

export async function runAnalysis(sid) {
  const r = await fetch(`${BASE}/api/analysis/${sid}`, { method: "POST" });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function chat(sid, message) {
  const r = await fetch(`${BASE}/api/chat/${sid}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function clearChat(sid) {
  await fetch(`${BASE}/api/chat/${sid}`, { method: "DELETE" });
}

export async function transcribeAudio(sid, blob) {
  const form = new FormData();
  form.append("audio", blob, "audio.webm");
  const r = await fetch(`${BASE}/api/voice/${sid}`, { method: "POST", body: form });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
