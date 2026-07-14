import { useMemo, useState } from "react";
import type { ChartType, QueryResult } from "../types";
import { buildOption } from "../charts/buildOption";
import { fmtValue } from "../charts/format";
import { EChart } from "./EChart";
import { DIM_TO_FILTER, useApp } from "../state/store";

const TYPE_OPTS: { id: ChartType; icon: string; label: string }[] = [
  { id: "bar", icon: "▊", label: "棒" },
  { id: "line", icon: "〰", label: "折れ線" },
  { id: "pie", icon: "◕", label: "円" },
];

export function ChartTile({
  res, ai = false, onRemove,
}: { res: QueryResult; ai?: boolean; onRemove?: () => void }) {
  const [showData, setShowData] = useState(false);
  const [ctype, setCtype] = useState<ChartType>(res.spec.chart_type);
  const applyCrossFilter = useApp((s) => s.applyCrossFilter);
  const view = useMemo(
    () => ({ ...res, spec: { ...res.spec, chart_type: ctype } }),
    [res, ctype],
  );
  const option = useMemo(() => buildOption(view), [view]);
  const empty = res.rows.length === 0;

  const dim = res.dimensions[0];
  const crossable = !!dim && (dim.id === "hour" || dim.id in DIM_TO_FILTER);

  const handleClick = crossable
    ? (p: any) => {
        const row = res.rows.find((r) => String(r.dim0) === String(p.name));
        const raw = row ? row.dim0_raw : p.name;
        applyCrossFilter(dim!.id, raw);
      }
    : undefined;

  return (
    <div className={`tile ${ai ? "tile-ai" : ""}`}>
      <div className="tile-head">
        <div className="tile-title">
          {ai && <span className="ai-badge">AI</span>}
          {res.title}
          {crossable && !showData && <span className="click-hint">クリックで絞り込み</span>}
        </div>
        <div className="tile-actions">
          {!showData && dim && (
            <div className="type-switch">
              {TYPE_OPTS.map((t) => (
                <button key={t.id} title={t.label} className={ctype === t.id ? "on" : ""}
                  onClick={() => setCtype(t.id)}>{t.icon}</button>
              ))}
            </div>
          )}
          <button className="tile-btn" title="元データ" onClick={() => setShowData((v) => !v)}>⊞</button>
          {onRemove && <button className="tile-btn" title="削除" onClick={onRemove}>✕</button>}
        </div>
      </div>

      {empty ? (
        <div className="tile-empty">該当データがありません</div>
      ) : showData ? (
        <div className="tile-table-wrap">
          <table className="tile-table">
            <thead>
              <tr><th>{dim?.label ?? "項目"}</th><th className="num">{res.metric.label}</th></tr>
            </thead>
            <tbody>
              {res.rows.map((r, i) => (
                <tr key={i}>
                  <td>{r.dim0 ?? "全体"}</td>
                  <td className="num">{fmtValue(r.value, res.metric.fmt, res.metric.unit)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EChart
          option={option}
          height={dim?.kind === "cat" && res.rows.length > 8 ? 320 : 260}
          onClick={handleClick}
        />
      )}
    </div>
  );
}
