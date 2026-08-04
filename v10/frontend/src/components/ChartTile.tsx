import { useMemo, useState } from "react";
import type { ChartType, QueryResult } from "../types";
import { buildOption } from "../charts/buildOption";
import { fmtValue } from "../charts/format";
import { EChart } from "./EChart";
import { Evidence } from "./Evidence";
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
  const [showEvidence, setShowEvidence] = useState(false);
  const [busy, setBusy] = useState(false);
  const [ctype, setCtype] = useState<ChartType>(res.spec.chart_type);
  const applyCrossFilter = useApp((s) => s.applyCrossFilter);
  const exportResult = useApp((s) => s.exportResult);
  const saveView = useApp((s) => s.saveView);

  const onExport = async () => {
    setBusy(true);
    try { await exportResult(res); }
    catch (e: any) { alert(`Excel出力に失敗しました: ${e?.message ?? e}`); }
    finally { setBusy(false); }
  };

  const onSave = async () => {
    const name = window.prompt("保存する分析の名前", res.title);
    if (!name) return;
    setBusy(true);
    try { await saveView(res, name); }
    catch (e: any) { alert(`保存に失敗しました: ${e?.message ?? e}`); }
    finally { setBusy(false); }
  };
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
          <button className={`tile-btn ${showEvidence ? "on" : ""}`} title="根拠（使用データ・集計式・フィルタ・SQL）"
            onClick={() => setShowEvidence((v) => !v)}>🔍</button>
          <button className="tile-btn" title="この分析を保存" onClick={onSave} disabled={busy}>★</button>
          <button className="tile-btn" title="Excelで出力" onClick={onExport} disabled={busy}>⬇</button>
          {onRemove && <button className="tile-btn" title="削除" onClick={onRemove}>✕</button>}
        </div>
      </div>

      {showEvidence && <Evidence res={res} />}

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
