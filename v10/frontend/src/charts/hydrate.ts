import { fmtValue, fmtCompact } from "./format";

/** バックエンドが返す ECharts option（関数なし）に、fmt に応じた数値フォーマッタを注入する。 */
export function hydrate(option: any, fmt: string): any {
  const opt = JSON.parse(JSON.stringify(option));

  // ツールチップの数値整形
  if (opt.tooltip) {
    if (Array.isArray(opt.tooltip)) {
      opt.tooltip.forEach((t: any) => (t.valueFormatter = (v: number) => fmtValue(v, fmt, "")));
    } else {
      opt.tooltip.valueFormatter = (v: number) => fmtValue(v, fmt, "");
    }
  }

  // 値軸ラベルを短縮表記（既にformatterがある軸は尊重）
  const fixAxis = (ax: any) => {
    if (!ax) return;
    if (Array.isArray(ax)) { ax.forEach(fixAxis); return; }
    if (ax.type === "value" && !(ax.axisLabel && ax.axisLabel.formatter)) {
      ax.axisLabel = { ...(ax.axisLabel || {}), formatter: (v: number) => fmtCompact(v, fmt) };
    }
  };
  fixAxis(opt.xAxis);
  fixAxis(opt.yAxis);

  return opt;
}
