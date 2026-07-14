import { useApp } from "../state/store";

export function LoadProgress() {
  const { loadPhase, loadPct, loadRows, loadError } = useApp();

  if (loadPhase === "error") {
    return (
      <div className="center-panel">
        <div className="load-card error">
          <div className="load-title">取得に失敗しました</div>
          <div className="load-detail">{loadError}</div>
        </div>
      </div>
    );
  }

  if (loadPhase === "loading" || loadPhase === "processing") {
    return (
      <div className="center-panel">
        <div className="load-card">
          <div className="load-title">
            {loadPhase === "processing" ? "DuckDB に投入中…" : "データを取得しています…"}
          </div>
          <div className="load-bar"><div className="load-fill" style={{ width: `${loadPct}%` }} /></div>
          <div className="load-meta">
            <span>{loadPct}%</span>
            <span>累計 {loadRows.toLocaleString()} 件</span>
          </div>
        </div>
      </div>
    );
  }

  // idle
  return (
    <div className="center-panel">
      <div className="empty-hero">
        <div className="empty-mark">✦</div>
        <div className="empty-title">AIネイティブ BI</div>
        <div className="empty-desc">
          左で分析期間と店舗を選び「データを取得する」を押すと、<br />
          ダッシュボードが自動生成され、AIに自然言語で追加分析を依頼できます。
        </div>
      </div>
    </div>
  );
}
