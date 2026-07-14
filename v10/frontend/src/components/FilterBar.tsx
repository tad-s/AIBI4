import { useApp } from "../state/store";
import type { Filters } from "../types";

const DOW = ["月", "火", "水", "木", "金", "土", "日"];

/** グローバルフィルタ（全タイル・全分析に連動）。
 *  月・カテゴリのクイックトグル ＋ クロスフィルタで付いた全条件のチップ表示。 */
export function FilterBar() {
  const { meta, globalFilters, setGlobalFilter, applyCrossFilter, clearFilters } = useApp();
  if (!meta) return null;

  const toggle = (field: "months" | "categories", val: string) => {
    const cur = globalFilters[field];
    const next = cur.includes(val) ? cur.filter((x) => x !== val) : [...cur, val];
    setGlobalFilter({ [field]: next } as any);
  };

  // 適用中フィルタのチップ（クロスフィルタ由来を含む全フィールド）
  const active: { label: string; onRemove: () => void }[] = [];
  const listFields: [keyof Filters, string, string][] = [
    ["stores", "店舗", "store"],
    ["customer_layers", "客層", "customer_layer"],
    ["weather", "天気", "weather"],
  ];
  for (const [field, label, dimId] of listFields) {
    for (const v of globalFilters[field] as string[]) {
      active.push({ label: `${label}: ${v}`, onRemove: () => applyCrossFilter(dimId, v) });
    }
  }
  for (const d of globalFilters.dow) {
    active.push({ label: `曜日: ${DOW[d]}`, onRemove: () => applyCrossFilter("dow", d) });
  }
  if (globalFilters.hour_min !== null && globalFilters.hour_min === globalFilters.hour_max) {
    const h = globalFilters.hour_min;
    active.push({ label: `時間帯: ${h}時`, onRemove: () => applyCrossFilter("hour", h) });
  }

  const anyActive =
    active.length > 0 || globalFilters.months.length > 0 || globalFilters.categories.length > 0;

  return (
    <div className="filterbar">
      <div className="fb-group">
        <span className="fb-label">期間</span>
        {meta.months.map((m) => (
          <button key={m} className={`fb-chip ${globalFilters.months.includes(m) ? "on" : ""}`}
            onClick={() => toggle("months", m)}>{m}</button>
        ))}
      </div>
      <div className="fb-divider" />
      <div className="fb-group">
        <span className="fb-label">カテゴリ</span>
        {meta.categories.filter((c) => c !== "除外").map((c) => (
          <button key={c} className={`fb-chip ${globalFilters.categories.includes(c) ? "on" : ""}`}
            onClick={() => toggle("categories", c)}>{c}</button>
        ))}
      </div>

      {active.length > 0 && (
        <>
          <div className="fb-divider" />
          <div className="fb-group">
            <span className="fb-label">絞り込み中</span>
            {active.map((a, i) => (
              <button key={i} className="fb-chip active-chip" onClick={a.onRemove}>
                {a.label} <span className="chip-x">✕</span>
              </button>
            ))}
          </div>
        </>
      )}

      {anyActive && (
        <button className="fb-clear" onClick={clearFilters}>すべて解除</button>
      )}
    </div>
  );
}
