import type { SearchRequest, SearchResponse } from "./types";

export class ApiError extends Error {
  readonly status: number;
  readonly payload: unknown;
  constructor(status: number, message: string, payload?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

export interface SearchClient {
  search(req: SearchRequest): Promise<SearchResponse>;
}

export function searchClient(baseUrl: string): SearchClient {
  return {
    async search(req) {
      const url = `${baseUrl.replace(/\/$/, "")}/search`;
      let res: Response;
      try {
        res = await fetch(url, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(req),
        });
      } catch (e) {
        throw new ApiError(0, e instanceof Error ? e.message : String(e));
      }
      if (!res.ok) {
        let payload: unknown;
        const cloned = res.clone();
        try {
          payload = await res.json();
        } catch {
          try { payload = await cloned.text(); } catch { /* truly unreadable */ }
        }
        throw new ApiError(res.status, `HTTP ${res.status}`, payload);
      }
      return (await res.json()) as SearchResponse;
    },
  };
}
