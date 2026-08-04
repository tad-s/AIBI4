import { useState } from "react";
import { useApp } from "../state/store";
import { ConfidenceBadge } from "./Evidence";

const SUGGESTIONS = [
  "店舗別の売上ランキングを見せて",
  "時間帯ごとの客単価は？",
  "カテゴリ別の売上構成",
  "曜日別の注文数の違い",
];

export function AskBar() {
  const { ask, asking, chat } = useApp();
  const [text, setText] = useState("");
  const [open, setOpen] = useState(false);

  const send = async (msg?: string) => {
    const m = (msg ?? text).trim();
    if (!m || asking) return;
    setText("");
    setOpen(true);
    await ask(m);
  };

  return (
    <div className="askbar-wrap">
      <div className="askbar">
        <span className="ask-icon">✦</span>
        <input
          className="ask-input"
          placeholder="AIに質問して分析を作る　例:「新宿店の時間帯別の客単価は？」"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") send(); }}
          onFocus={() => setOpen(true)}
        />
        <button className="ask-send" onClick={() => send()} disabled={asking}>
          {asking ? "…" : "送信"}
        </button>
      </div>

      {!chat.length && (
        <div className="ask-suggestions">
          {SUGGESTIONS.map((s) => (
            <button key={s} className="ask-sugg" onClick={() => send(s)}>{s}</button>
          ))}
        </div>
      )}

      {open && chat.length > 0 && (
        <div className="ask-thread">
          {chat.map((c, i) => (
            <div key={i} className={`ask-msg ask-${c.role} ${c.action ? `act-${c.action}` : ""}`}>
              {c.role === "assistant" && c.action && c.action !== "query" && (
                <span className="act-tag">
                  {c.action === "clarify" ? "確認" : "対応不可"}
                </span>
              )}
              <span>{c.content}</span>
              {c.role === "assistant" && c.action === "query" && c.confidence != null && (
                <div className="ask-conf"><ConfidenceBadge c={c.confidence} /></div>
              )}
            </div>
          ))}
          {asking && <div className="ask-msg ask-assistant"><span className="dots">分析中…</span></div>}
        </div>
      )}
    </div>
  );
}
