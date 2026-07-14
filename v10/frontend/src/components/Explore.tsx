import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { useApp } from "../state/store";
import { buildOption } from "../charts/buildOption";
import { emptyFilters, type ChartType, type Filters, type QueryResult } from "../types";
import { EChart } from "./EChart";

const CHARTS: { id: ChartType; label: string }[] = [
  { id: "bar", label: "棒" }, { id: "line", label: "折れ線" },
  { id: "area", label: "エリア" }, { id: "pie", label: "円" }, { id: "table", label: "表" },
];

// ドリルダウンの標準チェーン（クリックで次の軸へ）
const DRILL_NEXT: Record<string, string> = {
  store: "category", category: "item", month: "date", weather: "category", customer_layer: "category",
};
const DIM_TO_FILTER: Record<string, keyof Filters> = {
  store: "stores", category: "categories", month: "months",
  customer_layer: "customer_layers", weather: "weather",
};

interface Crumb { dimId: string; dimLabel: string; value: string; }

export function Explore() {
  const { sessionId, globalFilters, catalog } = useApp();
  const metrics = catalog.metrics;
  const dims = catalog.dimensions;

  const [metric, setMetric] = useState("revenue");
  const [dim, setDim] = useState("store");
  const [chart, setChart] = useState<ChartType>("bar");
  const [crumbs, setCrumbs] = useState<Crumb[]>([]);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [loading, setLoading] = useState(false);

  const metricView = metrics.find((m) => m.id === metric)?.view ?? "items";
  const availDims = useMemo(
    () => dims.filter((d) => d.views.includes(metricView)),
    [dims, metricView],
  );

  // 指標を変えて軸が非互換になったら補正
  useEffect(() => {
    if (dim && !availDims.find((d) => d.id === dim)) {
      setDim(availDims[0]?.id ?? "");
      setCrumbs([]);
    }
  }, [metricView]);

  // ドリルのパンくずをフィルタに反映
  const drillFilters: Filters = useMemo(() => {
    const f = emptyFilters();
    for (const c of crumbs) {
      const field = DIM_TO_FILTER[c.dimId];
      if (field) (f[field] as string[]).push(c.value);
    }
    return f;
  }, [crumbs]);

  useEffect(() => {
    if (!sessionId || !dim) return;
    let cancelled = false;
    setLoading(true);
    const spec = {
      metric, dimensions: [dim], filters: drillFilters,
      chart_type: chart === "table" ? "bar" : chart, sort: "value_desc" as const,
      limit: 30,
    };
    api.query(sessionId, spec as any, globalFilters)
      .then((r) => { if (!cancelled) setResult(r); })
      .catch(() => { if (!cancelled) setResult(null); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [sessionId, metric, dim, chart, crumbs, globalFilters]);

  const option = useMemo(() => (result ? buildOption(result) : null), [result]);

  const onBarClick = (p: any) => {
    if (!result) return;
    const row = result.rows.find((r) => String(r.dim0) === String(p.name));
    const value = row ? String(row.dim0_raw) : String(p.name);
    const next = DRILL_NEXT[dim];
    const canDrill = next && availDims.find((d) => d.id === next) && DIM_TO_FILTER[dim];
    if (canDrill) {
      setCrumbs([...crumbs, { dimId: dim, dimLabel: dimLabel(dim), value }]);
      setDim(next);
    }
  };

  const dimLabel = (id: string) => dims.find((d) => d.id === id)?.label ?? id;
  const metricLabel = (id: string) => metrics.find((m) => m.id === id)?.label ?? id;

  return (
    <div className="explore">
      <div className="explore-controls">
        <div className="ex-field">
          <label>指標</label>
          <select value={metric} onChange={(e) => setMetric(e.target.value)}>
            {metrics.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
          </select>
        </div>
        <div className="ex-field">
          <label>軸</label>
          <select value={dim} onChange={(e) => { setDim(e.target.value); setCrumbs([]); }}>
            {availDims.map((d) => <option key={d.id} value={d.id}>{d.label}</option>)}
          </select>
        </div>
        <div className="ex-field">
          <label>グラフ</label>
          <div className="ex-charts">
            {CHARTS.map((c) => (
              <button key={c.id} className={chart === c.id ? "on" : ""} onClick={() => setChart(c.id)}>{c.label}</button>
            ))}
          </div>
        </div>
      </div>

      <div className="explore-canvas">
        <div className="ex-head">
          <div className="ex-title">
            {crumbs.length > 0 && (
              <span className="ex-crumbs">
                <button className="crumb-root" onClick={() => setCrumbs([])}>全体</button>
                {crumbs.map((c, i) => (
                  <span key={i}>
                    <span className="crumb-sep">›</span>
                    <button className="crumb" onClick={() => setCrumbs(crumbs.slice(0, i + 1))}>
                      {c.dimLabel}: {c.value}
                    </button>
                  </span>
                ))}
                <span className="crumb-sep">›</span>
              </span>
            )}
            {dimLabel(dim)}別 {metricLabel(metric)}
          </div>
          {DRILL_NEXT[dim] && availDims.find((d) => d.id === DRILL_NEXT[dim]) && (
            <span className="drill-hint">棒をクリックで「{dimLabel(DRILL_NEXT[dim])}」へドリルダウン</span>
          )}
        </div>

        {loading && !result ? (
          <div className="ex-loading"><span className="spinner" /></div>
        ) : chart === "table" && result ? (
          <ExploreTable res={result} />
        ) : option ? (
          <EChart option={option} height={440} onClick={onBarClick} />
        ) : (
          <div className="tile-empty">該当データがありません</div>
        )}
      </div>
    </div>
  );
}

function ExploreTable({ res }: { res: QueryResult }) {
  return (
    <div className="ex-table-wrap">
      <table className="tile-table">
        <thead><tr><th>{res.dimensions[0]?.label}</th><th className="num">{res.metric.label}</th></tr></thead>
        <tbody>
          {res.rows.map((r, i) => (
            <tr key={i}><td>{r.dim0}</td><td className="num">{(r.value ?? 0).toLocaleString("ja-JP")}</td></tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
