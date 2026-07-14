import type { EChartsOption } from "echarts";
import type { QueryResult } from "../types";
import { fmtValue, fmtCompact } from "./format";

const CATEGORY_COLORS: Record<string, string> = {
  "ドリンク": "#5b9bd5", "揚げ物": "#f39c12", "串": "#e74c3c", "海鮮": "#1abc9c",
  "鍋": "#e67e22", "サラダ": "#70ad47", "ヘビー": "#c0392b", "軽いつまみ": "#2ecc71",
  "締め": "#9b59b6", "その他": "#95a5a6",
};

const PALETTE = [
  "#4f7bd8", "#22a2b8", "#f39c12", "#e05a6d", "#70ad47",
  "#9b59b6", "#e67e22", "#1abc9c", "#5d6d7e", "#c0392b",
];

const AXIS_COLOR = "#8a93a6";
const GRID_COLOR = "#eef1f6";

function baseTooltip(fmt: string, unit: string): any {
  return {
    trigger: "item",
    backgroundColor: "rgba(28,32,44,0.92)",
    borderWidth: 0,
    textStyle: { color: "#fff", fontSize: 12 },
    formatter: (p: any) => {
      const name = Array.isArray(p) ? p[0]?.axisValueLabel : p.name;
      const val = Array.isArray(p) ? p[0]?.value : p.value;
      return `${name}<br/><b>${fmtValue(val, fmt, unit)}</b>`;
    },
  };
}

export function buildOption(res: QueryResult): EChartsOption {
  const { rows, metric, dimensions, spec } = res;
  const fmt = metric.fmt, unit = metric.unit;
  const labels = rows.map((r) => r.dim0 ?? "");
  const values = rows.map((r) => (r.value ?? 0));
  const dimKind = dimensions[0]?.kind ?? "cat";

  if (spec.chart_type === "pie") {
    return {
      color: PALETTE,
      tooltip: {
        trigger: "item",
        backgroundColor: "rgba(28,32,44,0.92)", borderWidth: 0,
        textStyle: { color: "#fff", fontSize: 12 },
        formatter: (p: any) => `${p.name}<br/><b>${fmtValue(p.value, fmt, unit)}</b> (${p.percent}%)`,
      },
      legend: { type: "scroll", bottom: 0, textStyle: { color: AXIS_COLOR, fontSize: 11 } },
      series: [{
        type: "pie",
        radius: ["42%", "70%"],
        center: ["50%", "46%"],
        avoidLabelOverlap: true,
        itemStyle: { borderColor: "#fff", borderWidth: 2, borderRadius: 4 },
        label: { formatter: "{b}\n{d}%", fontSize: 11, color: "#4a5163" },
        data: rows.map((r) => ({
          name: String(r.dim0),
          value: r.value ?? 0,
          itemStyle: CATEGORY_COLORS[String(r.dim0)] ? { color: CATEGORY_COLORS[String(r.dim0)] } : undefined,
        })),
      }],
    };
  }

  if (spec.chart_type === "line" || spec.chart_type === "area") {
    return {
      tooltip: { ...baseTooltip(fmt, unit), trigger: "axis" },
      grid: { left: 8, right: 20, top: 20, bottom: 8, containLabel: true },
      xAxis: {
        type: "category", data: labels, boundaryGap: false,
        axisLine: { lineStyle: { color: GRID_COLOR } },
        axisLabel: { color: AXIS_COLOR, fontSize: 11 },
        axisTick: { show: false },
      },
      yAxis: {
        type: "value",
        splitLine: { lineStyle: { color: GRID_COLOR } },
        axisLabel: { color: AXIS_COLOR, fontSize: 11, formatter: (v: number) => fmtCompact(v, fmt) },
      },
      series: [{
        type: "line", data: values, smooth: true, symbolSize: 7,
        lineStyle: { width: 3, color: "#4f7bd8" },
        itemStyle: { color: "#4f7bd8" },
        areaStyle: spec.chart_type === "area"
          ? { color: { type: "linear", x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [{ offset: 0, color: "rgba(79,123,216,0.35)" }, { offset: 1, color: "rgba(79,123,216,0.02)" }] } }
          : undefined,
      }],
    };
  }

  // bar（時系列は縦棒、カテゴリ/ランキングは横棒）
  const horizontal = dimKind !== "time";
  const catAxis = {
    type: "category" as const,
    data: horizontal ? [...labels].reverse() : labels,
    axisLine: { lineStyle: { color: GRID_COLOR } },
    axisLabel: { color: AXIS_COLOR, fontSize: 11, interval: 0,
      rotate: !horizontal && labels.length > 8 ? 30 : 0 },
    axisTick: { show: false },
  };
  const valAxis = {
    type: "value" as const,
    splitLine: { lineStyle: { color: GRID_COLOR } },
    axisLabel: { color: AXIS_COLOR, fontSize: 11, formatter: (v: number) => fmtCompact(v, fmt) },
  };
  const barData = (horizontal ? [...values].reverse() : values).map((v, i) => ({
    value: v,
    itemStyle: {
      color: CATEGORY_COLORS[String((horizontal ? [...labels].reverse() : labels)[i])] ?? "#4f7bd8",
      borderRadius: horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0],
    },
  }));

  return {
    tooltip: { ...baseTooltip(fmt, unit), trigger: "axis", axisPointer: { type: "shadow" } },
    grid: { left: 8, right: 24, top: 16, bottom: 8, containLabel: true },
    xAxis: horizontal ? valAxis : catAxis,
    yAxis: horizontal ? catAxis : valAxis,
    series: [{
      type: "bar",
      data: barData,
      barMaxWidth: 34,
      label: {
        show: rows.length <= 15,
        position: horizontal ? "right" : "top",
        color: "#6b7280", fontSize: 10,
        formatter: (p: any) => fmtCompact(p.value, fmt),
      },
    }],
  };
}
