export type ChartType = "kpi" | "bar" | "line" | "area" | "pie" | "table";

export interface Filters {
  months: string[];
  stores: string[];
  categories: string[];
  customer_layers: string[];
  weather: string[];
  hour_min: number | null;
  hour_max: number | null;
  dow: number[];
}

export function emptyFilters(): Filters {
  return {
    months: [], stores: [], categories: [], customer_layers: [],
    weather: [], hour_min: null, hour_max: null, dow: [],
  };
}

export interface QuerySpec {
  metric: string;
  dimensions: string[];
  filters: Filters;
  chart_type: ChartType;
  sort: "value_desc" | "value_asc" | "dim_asc";
  limit: number;
  title?: string | null;
}

export interface ResultRow {
  value: number | null;
  [k: string]: any;
}

export interface QueryResult {
  spec: QuerySpec;
  metric: { id: string; label: string; unit: string; fmt: string };
  dimensions: { id: string; label: string; kind: string }[];
  rows: ResultRow[];
  sql: string;
  title: string;
  spark?: number[];
  delta?: number;
}

export interface SessionMeta {
  item_rows: number;
  order_rows: number;
  stores: string[];
  months: string[];
  categories: string[];
  has_weather: boolean;
}

export interface StoreOption {
  store_id: number;
  store_name: string;
}

export interface AskResponse {
  action: "query" | "clarify" | "impossible";
  message: string;
  result: QueryResult | null;
}

export interface AnalysisChart {
  option: any;
  fmt: string;
  height: number;
}

export interface AnalysisTable {
  columns: string[];
  rows: (string | number)[][];
}

export interface AnalysisResult {
  id: string;
  title: string;
  insight: string;
  insights: string[];
  advice: string[];
  chart: AnalysisChart | null;
  table: AnalysisTable | null;
}

export interface AnalysesResponse {
  base: AnalysisResult[];
  order_flow: AnalysisResult[];
  message: string;
}
