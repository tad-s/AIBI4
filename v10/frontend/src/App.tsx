import { useEffect } from "react";
import { useApp } from "./state/store";
import { Sidebar } from "./components/Sidebar";
import { FilterBar } from "./components/FilterBar";
import { AskBar } from "./components/AskBar";
import { KpiRow } from "./components/KpiRow";
import { ChartTile } from "./components/ChartTile";
import { AnalysisCard } from "./components/AnalysisCard";
import { Explore } from "./components/Explore";
import { LoadProgress } from "./components/LoadProgress";

const TABS: { id: "dashboard" | "base" | "flow" | "explore"; label: string }[] = [
  { id: "dashboard", label: "📊 ダッシュボード" },
  { id: "explore", label: "🧭 探索" },
  { id: "base", label: "🔬 ベース分析" },
  { id: "flow", label: "🔀 注文導線分析" },
];

export default function App() {
  const s = useApp();
  useEffect(() => { s.init(); }, []);

  const loaded = s.loadPhase === "loaded" && s.meta;

  return (
    <div className="app">
      <Sidebar />
      <main className="main">
        {!loaded ? (
          <LoadProgress />
        ) : (
          <>
            <div className="topbar">
              <AskBar />
              <div className="data-meta">
                <span className="dot" /> {s.meta!.order_rows.toLocaleString()} 伝票 /{" "}
                {s.meta!.item_rows.toLocaleString()} 明細
              </div>
            </div>

            <div className="tabbar">
              {TABS.map((t) => (
                <button
                  key={t.id}
                  className={`tab ${s.view === t.id ? "on" : ""}`}
                  onClick={() => s.setView(t.id)}
                >{t.label}</button>
              ))}
            </div>

            <FilterBar />

            <div className="dash-scroll">
              {s.view === "dashboard" && (
                <>
                  <KpiRow kpis={s.kpis} />
                  {s.aiTiles.length > 0 && (
                    <section>
                      <div className="section-title">AI分析</div>
                      <div className="grid">
                        {s.aiTiles.map((t, i) => (
                          <ChartTile key={`ai-${i}`} res={t} ai onRemove={() => s.removeAiTile(i)} />
                        ))}
                      </div>
                    </section>
                  )}
                  <section>
                    <div className="section-title">
                      ダッシュボード {s.dashboardLoading && <span className="mini-spin">更新中…</span>}
                    </div>
                    <div className="grid">
                      {s.tiles.map((t, i) => <ChartTile key={`t-${i}`} res={t} />)}
                    </div>
                  </section>
                </>
              )}

              {s.view === "explore" && <Explore />}

              {(s.view === "base" || s.view === "flow") && (
                <section>
                  {s.analysesLoading ? (
                    <div className="analyses-loading">
                      <span className="spinner" /> 12項目の分析を計算中…
                    </div>
                  ) : (
                    <div className="grid grid-wide">
                      {(s.view === "base" ? s.baseAnalyses : s.flowAnalyses).map((a) => (
                        <AnalysisCard key={a.id} res={a} />
                      ))}
                    </div>
                  )}
                </section>
              )}
            </div>
          </>
        )}
      </main>
    </div>
  );
}
