import { useMemo, useState } from "react";
import { useApp } from "../state/store";

export function Sidebar() {
  const {
    dataset, datasets, setDataset,
    availableMonths, selectedMonths, toggleMonth,
    availableStores, selectedStoreIds, toggleStore,
    fetchData, loadPhase,
    savedViews, runSaved, deleteSaved,
  } = useApp();
  const [storeSearch, setStoreSearch] = useState("");

  const filteredStores = useMemo(
    () => availableStores.filter((s) => s.store_name.includes(storeSearch)),
    [availableStores, storeSearch],
  );
  const loading = loadPhase === "loading" || loadPhase === "processing";

  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">A</div>
        <div className="brand-text">AIBI4 <span>v10</span></div>
      </div>

      <div className="sb-section">
        <div className="sb-label">データセット</div>
        <select className="sb-select" value={dataset} onChange={(e) => setDataset(e.target.value)}>
          {datasets.map((d) => <option key={d.id} value={d.id}>{d.label}</option>)}
        </select>
      </div>

      <div className="sb-section">
        <div className="sb-label">分析期間<span className="sb-hint">複数選択可</span></div>
        <div className="chip-wrap">
          {availableMonths.length === 0 && <span className="sb-muted">読み込み中…</span>}
          {availableMonths.map((m) => (
            <button
              key={m}
              className={`chip ${selectedMonths.includes(m) ? "on" : ""}`}
              onClick={() => toggleMonth(m)}
            >{m}</button>
          ))}
        </div>
      </div>

      <div className="sb-section sb-stores">
        <div className="sb-label">
          店舗フィルタ<span className="sb-hint">未選択=全店舗</span>
        </div>
        <input
          className="sb-input"
          placeholder="店舗を絞り込む…"
          value={storeSearch}
          onChange={(e) => setStoreSearch(e.target.value)}
        />
        <div className="store-list">
          {filteredStores.map((s) => (
            <label key={s.store_id} className="store-item">
              <input
                type="checkbox"
                checked={selectedStoreIds.includes(s.store_id)}
                onChange={() => toggleStore(s.store_id)}
              />
              <span>{s.store_name}</span>
            </label>
          ))}
        </div>
      </div>

      <button className="fetch-btn" onClick={fetchData} disabled={loading}>
        {loading ? "取得中…" : "データを取得する"}
      </button>

      {loadPhase === "loaded" && (
        <div className="sb-section sb-saved">
          <div className="sb-label">保存済み分析<span className="sb-hint">クリックで表示</span></div>
          {savedViews.length === 0 ? (
            <span className="sb-muted">タイルの ★ で保存できます</span>
          ) : (
            <div className="saved-list">
              {savedViews.map((v) => (
                <div key={v.id} className="saved-item">
                  <button className="saved-run" title="この分析を表示" onClick={() => runSaved(v)}>
                    ★ {v.name}
                  </button>
                  <button className="saved-del" title="削除" onClick={() => deleteSaved(v.id)}>✕</button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </aside>
  );
}
