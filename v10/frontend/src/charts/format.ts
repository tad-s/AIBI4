export function fmtValue(v: number | null, fmt: string, unit: string): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  switch (fmt) {
    case "yen":
      return `¥${Math.round(v).toLocaleString("ja-JP")}`;
    case "pct":
      return `${(v * 100).toFixed(1)}%`;
    case "float1":
      return `${v.toFixed(1)}${unit}`;
    case "int":
    default:
      return `${Math.round(v).toLocaleString("ja-JP")}${unit}`;
  }
}

/** 軸ラベル・KPI用の短縮表記（千=K, 百万=M）。 */
export function fmtCompact(v: number | null, fmt: string): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const abs = Math.abs(v);
  let s: string;
  if (fmt === "pct") return `${(v * 100).toFixed(1)}%`;
  if (abs >= 1_000_000) s = `${(v / 1_000_000).toFixed(1)}M`;
  else if (abs >= 1_000) s = `${(v / 1_000).toFixed(0)}K`;
  else s = fmt === "yen" || fmt === "int" ? Math.round(v).toString() : v.toFixed(1);
  return fmt === "yen" ? `¥${s}` : s;
}
