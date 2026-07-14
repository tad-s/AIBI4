import type {
  AnalysesResponse, AskResponse, Filters, QueryResult, QuerySpec, SessionMeta, StoreOption,
} from "../types";

const BASE = import.meta.env.VITE_API_BASE ?? "";

async function jget<T>(url: string): Promise<T> {
  const r = await fetch(`${BASE}${url}`);
  if (!r.ok) throw new Error((await r.text()) || r.statusText);
  return r.json();
}

async function jpost<T>(url: string, body: unknown): Promise<T> {
  const r = await fetch(`${BASE}${url}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail ?? detail; } catch { /* ignore */ }
    throw new Error(detail);
  }
  return r.json();
}

export const api = {
  datasets: () => jget<{ datasets: { id: string; label: string }[] }>("/api/datasets"),
  catalog: () => jget<{ metrics: any[]; dimensions: any[] }>("/api/catalog"),
  months: (dataset: string) => jget<{ months: string[] }>(`/api/months?dataset=${dataset}`),
  stores: (dataset: string) => jget<{ stores: StoreOption[] }>(`/api/stores?dataset=${dataset}`),

  createSession: (dataset: string) =>
    jpost<{ session_id: string }>("/api/sessions", { dataset }),

  sessionMeta: (sid: string) =>
    jget<{ dataset: string; meta: SessionMeta }>(`/api/sessions/${sid}/meta`),

  query: (sid: string, spec: QuerySpec, global_filters: Filters) =>
    jpost<QueryResult>(`/api/sessions/${sid}/query`, { spec, global_filters }),

  dashboard: (sid: string, global_filters: Filters) =>
    jpost<{ kpis: QueryResult[]; tiles: QueryResult[] }>(
      `/api/sessions/${sid}/dashboard`, { global_filters }),

  ask: (sid: string, message: string, global_filters: Filters, history: any[]) =>
    jpost<AskResponse>(`/api/sessions/${sid}/ask`, { message, global_filters, history }),

  analyses: (sid: string, global_filters: Filters) =>
    jpost<AnalysesResponse>(`/api/sessions/${sid}/analyses`, { global_filters }),
};

/** SSE 相当のデータ投入（fetch stream を手動パース）。 */
export async function loadData(
  body: { session_id: string; dataset: string; months: string[]; store_ids: number[] | null },
  onEvent: (ev: any) => void,
): Promise<void> {
  const r = await fetch(`${BASE}/api/load`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok || !r.body) throw new Error((await r.text()) || "load failed");

  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const parts = buf.split("\n\n");
    buf = parts.pop() ?? "";
    for (const p of parts) {
      const line = p.trim();
      if (line.startsWith("data:")) {
        try { onEvent(JSON.parse(line.slice(5).trim())); } catch { /* ignore */ }
      }
    }
  }
}
