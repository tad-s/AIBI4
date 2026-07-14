import { useMemo, useState } from "react";
import type { AnalysisResult } from "../types";
import { hydrate } from "../charts/hydrate";
import { EChart } from "./EChart";

export function AnalysisCard({ res }: { res: AnalysisResult }) {
  const [tab, setTab] = useState<"chart" | "data">("chart");
  const option = useMemo(
    () => (res.chart ? hydrate(res.chart.option, res.chart.fmt) : null),
    [res],
  );

  return (
    <div className="acard">
      <div className="acard-head">
        <div className="acard-title">{res.title}</div>
        {res.table && (
          <div className="acard-toggle">
            <button className={tab === "chart" ? "on" : ""} onClick={() => setTab("chart")}>グラフ</button>
            <button className={tab === "data" ? "on" : ""} onClick={() => setTab("data")}>データ</button>
          </div>
        )}
      </div>

      {!option ? (
        <div className="acard-empty">{res.insight || "データが不足しています"}</div>
      ) : tab === "data" && res.table ? (
        <div className="acard-table-wrap">
          <table className="tile-table">
            <thead>
              <tr>{res.table.columns.map((c) => <th key={c} className={typeof res.table!.rows[0]?.[res.table!.columns.indexOf(c)] === "number" ? "num" : ""}>{c}</th>)}</tr>
            </thead>
            <tbody>
              {res.table.rows.map((row, i) => (
                <tr key={i}>{row.map((cell, j) => (
                  <td key={j} className={typeof cell === "number" ? "num" : ""}>
                    {typeof cell === "number" ? cell.toLocaleString("ja-JP") : cell}
                  </td>
                ))}</tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EChart option={option} height={res.chart!.height} />
      )}

      <div className="acard-insight">
        <div className="acard-lead">💡 {res.insight}</div>
        {res.insights.length > 0 && (
          <ul className="acard-list">
            {res.insights.map((s, i) => <li key={i} dangerouslySetInnerHTML={{ __html: mark(s) }} />)}
          </ul>
        )}
        {res.advice.length > 0 && (
          <div className="acard-advice">
            <div className="acard-advice-label">打ち手</div>
            <ul className="acard-list">
              {res.advice.map((s, i) => <li key={i} dangerouslySetInnerHTML={{ __html: mark(s) }} />)}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}

function mark(s: string): string {
  return s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}
