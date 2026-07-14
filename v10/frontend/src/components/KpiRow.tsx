import type { QueryResult } from "../types";
import { fmtValue } from "../charts/format";

function Sparkline({ values, up }: { values: number[]; up: boolean }) {
  if (!values || values.length < 2) return null;
  const w = 108, h = 30, pad = 2;
  const min = Math.min(...values), max = Math.max(...values);
  const range = max - min || 1;
  const pts = values.map((v, i) => {
    const x = pad + (i / (values.length - 1)) * (w - pad * 2);
    const y = h - pad - ((v - min) / range) * (h - pad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const color = up ? "#35c26b" : "#e05a6d";
  return (
    <svg className="spark" width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
      <polyline points={pts.join(" ")} fill="none" stroke={color} strokeWidth="1.8"
        strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={pts[pts.length - 1].split(",")[0]} cy={pts[pts.length - 1].split(",")[1]} r="2.2" fill={color} />
    </svg>
  );
}

function KpiCard({ res }: { res: QueryResult }) {
  const v = res.rows[0]?.value ?? null;
  const delta = res.delta;
  const up = (delta ?? 0) >= 0;
  return (
    <div className="kpi-card">
      <div className="kpi-top">
        <div className="kpi-label">{res.metric.label}</div>
        {delta !== undefined && Number.isFinite(delta) && (
          <div className={`kpi-delta ${up ? "up" : "down"}`}>
            {up ? "▲" : "▼"} {Math.abs(delta * 100).toFixed(1)}%
          </div>
        )}
      </div>
      <div className="kpi-value">{fmtValue(v, res.metric.fmt, res.metric.unit)}</div>
      {res.spark && res.spark.length >= 2 && <Sparkline values={res.spark} up={up} />}
    </div>
  );
}

export function KpiRow({ kpis }: { kpis: QueryResult[] }) {
  if (!kpis.length) return null;
  return <div className="kpi-row">{kpis.map((k) => <KpiCard key={k.metric.id} res={k} />)}</div>;
}
