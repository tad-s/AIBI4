import type { Filters, QueryResult } from "../types";

const VIEW_LABEL: Record<string, string> = {
  items: "商品明細（1商品=1行）",
  orders: "伝票（1来店=1行）",
};

const DOW = ["月", "火", "水", "木", "金", "土", "日"];

/** 適用中フィルタを人が読める文字列の配列にする。 */
function filterChips(f: Filters): { label: string; value: string }[] {
  const out: { label: string; value: string }[] = [];
  if (f.months?.length) out.push({ label: "月", value: f.months.join("・") });
  if (f.stores?.length) out.push({ label: "店舗", value: f.stores.join("・") });
  if (f.categories?.length) out.push({ label: "カテゴリ", value: f.categories.join("・") });
  if (f.customer_layers?.length) out.push({ label: "客層", value: f.customer_layers.join("・") });
  if (f.weather?.length) out.push({ label: "天気", value: f.weather.join("・") });
  if (f.dow?.length) out.push({ label: "曜日", value: f.dow.map((d) => DOW[d] ?? d).join("・") });
  if (f.hour_min != null || f.hour_max != null) {
    const lo = f.hour_min ?? 0;
    const hi = f.hour_max ?? 23;
    out.push({ label: "時間帯", value: lo === hi ? `${lo}時` : `${lo}〜${hi}時` });
  }
  return out;
}

/** 信頼度バッジ（0〜1）。欠損時は null。 */
export function ConfidenceBadge({ c }: { c?: number | null }) {
  if (c == null) return null;
  const pct = Math.round(c * 100);
  const level = c >= 0.8 ? "high" : c >= 0.5 ? "mid" : "low";
  const label = level === "high" ? "高" : level === "mid" ? "中" : "低";
  return <span className={`conf-badge conf-${level}`} title={`AIの写像確信度 ${pct}%`}>信頼度 {label}・{pct}%</span>;
}

/** AI回答の根拠（使用データ・集計式・軸・フィルタ・信頼度・SQL）を開示する。 */
export function Evidence({ res }: { res: QueryResult }) {
  const chips = filterChips(res.spec.filters);
  return (
    <div className="evidence">
      <div className="ev-row">
        <span className="ev-key">使用データ</span>
        <span className="ev-val">{VIEW_LABEL[res.metric.view ?? ""] ?? res.metric.view ?? "—"}</span>
      </div>
      <div className="ev-row">
        <span className="ev-key">指標</span>
        <span className="ev-val">
          {res.metric.label}
          {res.metric.agg && <code className="ev-code">{res.metric.agg}</code>}
          {res.metric.unit && <span className="ev-unit">単位: {res.metric.unit}</span>}
        </span>
      </div>
      <div className="ev-row">
        <span className="ev-key">軸</span>
        <span className="ev-val">
          {res.dimensions.length ? res.dimensions.map((d) => d.label).join(" × ") : "（全体集計）"}
        </span>
      </div>
      <div className="ev-row">
        <span className="ev-key">適用フィルタ</span>
        <span className="ev-val">
          {chips.length ? (
            <span className="ev-chips">
              {chips.map((c, i) => (
                <span key={i} className="ev-chip"><b>{c.label}</b> {c.value}</span>
              ))}
            </span>
          ) : "（なし）"}
        </span>
      </div>
      {res.confidence != null && (
        <div className="ev-row">
          <span className="ev-key">信頼度</span>
          <span className="ev-val"><ConfidenceBadge c={res.confidence} /></span>
        </div>
      )}
      <div className="ev-row ev-sql-row">
        <span className="ev-key">SQL</span>
        <pre className="ev-sql">{res.sql}</pre>
      </div>
    </div>
  );
}
