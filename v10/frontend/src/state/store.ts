import { create } from "zustand";
import { api, exportXlsx, loadData } from "../api/client";
import { emptyFilters, type AnalysisResult, type Filters, type QueryResult, type QuerySpec, type SavedView, type SessionMeta, type StoreOption } from "../types";

type LoadPhase = "idle" | "loading" | "processing" | "loaded" | "error";
type View = "dashboard" | "base" | "flow" | "explore";

interface ChatMsg {
  role: "user" | "assistant";
  content: string;
  action?: "query" | "clarify" | "impossible";
  result?: QueryResult | null;
  confidence?: number | null;
}

interface AppState {
  // setup
  dataset: string;
  datasets: { id: string; label: string }[];
  catalog: { metrics: any[]; dimensions: any[] };
  availableMonths: string[];
  availableStores: StoreOption[];
  selectedMonths: string[];
  selectedStoreIds: number[];

  // session / data
  sessionId: string | null;
  meta: SessionMeta | null;
  loadPhase: LoadPhase;
  loadPct: number;
  loadRows: number;
  loadError: string;

  // view / dashboard
  view: View;
  globalFilters: Filters;
  kpis: QueryResult[];
  tiles: QueryResult[];
  aiTiles: QueryResult[];
  dashboardLoading: boolean;

  // analyses
  baseAnalyses: AnalysisResult[];
  flowAnalyses: AnalysisResult[];
  analysesLoaded: boolean;
  analysesLoading: boolean;

  // ai chat
  chat: ChatMsg[];
  asking: boolean;

  // saved views
  savedViews: SavedView[];

  // actions
  init: () => Promise<void>;
  setDataset: (d: string) => Promise<void>;
  toggleMonth: (m: string) => void;
  toggleStore: (id: number) => void;
  fetchData: () => Promise<void>;
  setGlobalFilter: (patch: Partial<Filters>) => Promise<void>;
  refreshDashboard: () => Promise<void>;
  refreshAnalyses: () => Promise<void>;
  setView: (v: View) => void;
  ask: (message: string) => Promise<void>;
  removeAiTile: (idx: number) => void;
  applyCrossFilter: (dimId: string, raw: any) => Promise<void>;
  clearFilters: () => Promise<void>;
  exportResult: (res: QueryResult) => Promise<void>;
  loadSaved: () => Promise<void>;
  saveView: (res: QueryResult, name: string) => Promise<void>;
  runSaved: (view: SavedView) => Promise<void>;
  deleteSaved: (id: string) => Promise<void>;
}

// 軸ID → グローバルフィルタのフィールド
export const DIM_TO_FILTER: Record<string, keyof Filters> = {
  store: "stores",
  category: "categories",
  month: "months",
  customer_layer: "customer_layers",
  weather: "weather",
  dow: "dow",
};

export const useApp = create<AppState>((set, get) => ({
  dataset: "izakaya",
  datasets: [],
  catalog: { metrics: [], dimensions: [] },
  availableMonths: [],
  availableStores: [],
  selectedMonths: [],
  selectedStoreIds: [],

  sessionId: null,
  meta: null,
  loadPhase: "idle",
  loadPct: 0,
  loadRows: 0,
  loadError: "",

  view: "dashboard",
  globalFilters: emptyFilters(),
  kpis: [],
  tiles: [],
  aiTiles: [],
  dashboardLoading: false,

  baseAnalyses: [],
  flowAnalyses: [],
  analysesLoaded: false,
  analysesLoading: false,

  chat: [],
  asking: false,

  savedViews: [],

  async init() {
    const [ds, cat] = await Promise.all([api.datasets(), api.catalog()]);
    set({ datasets: ds.datasets, catalog: { metrics: cat.metrics, dimensions: cat.dimensions } });
    await get().setDataset(get().dataset);
  },

  async setDataset(d: string) {
    set({ dataset: d, selectedMonths: [], selectedStoreIds: [] });
    const [m, s] = await Promise.all([api.months(d), api.stores(d)]);
    // 直近2ヶ月をデフォルト選択
    const months = m.months;
    set({
      availableMonths: months,
      availableStores: s.stores,
      selectedMonths: months.slice(-2),
    });
  },

  toggleMonth(m: string) {
    const cur = get().selectedMonths;
    set({ selectedMonths: cur.includes(m) ? cur.filter((x) => x !== m) : [...cur, m] });
  },

  toggleStore(id: number) {
    const cur = get().selectedStoreIds;
    set({ selectedStoreIds: cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id] });
  },

  async fetchData() {
    const { dataset, selectedMonths, selectedStoreIds } = get();
    if (selectedMonths.length === 0) {
      set({ loadError: "分析期間（月）を1つ以上選択してください。" });
      return;
    }
    set({ loadPhase: "loading", loadPct: 0, loadRows: 0, loadError: "" });
    try {
      const { session_id } = await api.createSession(dataset);
      await loadData(
        {
          session_id,
          dataset,
          months: selectedMonths,
          store_ids: selectedStoreIds.length ? selectedStoreIds : null,
        },
        (ev) => {
          if (ev.type === "progress") set({ loadPct: ev.pct, loadRows: ev.rows });
          else if (ev.type === "processing") set({ loadPhase: "processing" });
          else if (ev.type === "error") set({ loadPhase: "error", loadError: ev.message });
          else if (ev.type === "done") set({ meta: ev.meta });
        },
      );
      if (get().loadPhase === "error") return;
      // グローバルフィルタは取得月をデフォルトに
      set({
        sessionId: session_id,
        loadPhase: "loaded",
        view: "dashboard",
        globalFilters: { ...emptyFilters(), months: [] },
        aiTiles: [],
        chat: [],
        baseAnalyses: [],
        flowAnalyses: [],
        analysesLoaded: false,
      });
      await get().refreshDashboard();
      await get().loadSaved();
    } catch (e: any) {
      set({ loadPhase: "error", loadError: e?.message ?? String(e) });
    }
  },

  async setGlobalFilter(patch: Partial<Filters>) {
    set({ globalFilters: { ...get().globalFilters, ...patch } });
    await get().refreshDashboard();
    // 分析タブを既に読み込み済みなら連動して更新
    if (get().analysesLoaded) await get().refreshAnalyses();
  },

  async refreshDashboard() {
    const { sessionId, globalFilters } = get();
    if (!sessionId) return;
    set({ dashboardLoading: true });
    try {
      const d = await api.dashboard(sessionId, globalFilters);
      set({ kpis: d.kpis, tiles: d.tiles });
    } finally {
      set({ dashboardLoading: false });
    }
  },

  async refreshAnalyses() {
    const { sessionId, globalFilters } = get();
    if (!sessionId) return;
    set({ analysesLoading: true });
    try {
      const d = await api.analyses(sessionId, globalFilters);
      set({ baseAnalyses: d.base, flowAnalyses: d.order_flow, analysesLoaded: true });
    } finally {
      set({ analysesLoading: false });
    }
  },

  setView(v: View) {
    set({ view: v });
    if ((v === "base" || v === "flow") && !get().analysesLoaded && !get().analysesLoading) {
      get().refreshAnalyses();
    }
  },

  async ask(message: string) {
    const { sessionId, globalFilters, chat } = get();
    if (!sessionId || !message.trim()) return;
    const history = chat.map((c) => ({ role: c.role, content: c.content }));
    set({ chat: [...chat, { role: "user", content: message }], asking: true });
    try {
      const res = await api.ask(sessionId, message, globalFilters, history);
      const assistantMsg: ChatMsg = {
        role: "assistant",
        content: res.message || (res.action === "query" ? "分析結果を表示しました。" : ""),
        action: res.action,
        result: res.result,
        confidence: res.confidence ?? res.result?.confidence ?? null,
      };
      set({ chat: [...get().chat, assistantMsg] });
      if (res.action === "query" && res.result) {
        set({ aiTiles: [res.result, ...get().aiTiles] });
      }
    } catch (e: any) {
      set({ chat: [...get().chat, { role: "assistant", content: `エラー: ${e?.message ?? e}` }] });
    } finally {
      set({ asking: false });
    }
  },

  removeAiTile(idx: number) {
    set({ aiTiles: get().aiTiles.filter((_, i) => i !== idx) });
  },

  async applyCrossFilter(dimId: string, raw: any) {
    const gf = { ...get().globalFilters };
    if (dimId === "hour") {
      const h = Number(raw);
      // 同じ時間で絞り込み中ならトグル解除
      if (gf.hour_min === h && gf.hour_max === h) { gf.hour_min = null; gf.hour_max = null; }
      else { gf.hour_min = h; gf.hour_max = h; }
      set({ globalFilters: gf });
    } else {
      const field = DIM_TO_FILTER[dimId];
      if (!field) return; // item など対象外
      const cur = [...(gf[field] as any[])];
      const val = field === "dow" ? Number(raw) : String(raw);
      const idx = cur.findIndex((x) => x === val);
      if (idx >= 0) cur.splice(idx, 1); else cur.push(val);
      (gf[field] as any) = cur;
      set({ globalFilters: gf });
    }
    await get().refreshDashboard();
    if (get().analysesLoaded) await get().refreshAnalyses();
  },

  async clearFilters() {
    set({ globalFilters: emptyFilters() });
    await get().refreshDashboard();
    if (get().analysesLoaded) await get().refreshAnalyses();
  },

  async exportResult(res: QueryResult) {
    const { sessionId, globalFilters } = get();
    if (!sessionId) return;
    await exportXlsx(sessionId, res.spec, globalFilters, res.confidence ?? null);
  },

  async loadSaved() {
    try {
      const { items } = await api.listSaved(get().dataset);
      set({ savedViews: items });
    } catch {
      set({ savedViews: [] });
    }
  },

  async saveView(res: QueryResult, name: string) {
    const item = await api.saveView(name, res.spec, get().dataset);
    set({ savedViews: [item, ...get().savedViews] });
  },

  async runSaved(view: SavedView) {
    const { sessionId, globalFilters } = get();
    if (!sessionId) return;
    const spec: QuerySpec = { ...view.spec, title: view.name };
    const res = await api.query(sessionId, spec, globalFilters);
    set({ aiTiles: [res, ...get().aiTiles], view: "dashboard" });
  },

  async deleteSaved(id: string) {
    await api.deleteSaved(id);
    set({ savedViews: get().savedViews.filter((v) => v.id !== id) });
  },
}));
