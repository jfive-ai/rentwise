import type {
  SearchRequest,
  SearchResponse,
  TranslateQueryRequest,
  TranslateQueryResult,
} from "./types";

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

export interface ApiClient {
  search(req: SearchRequest): Promise<SearchResponse>;
  translateQuery(req: TranslateQueryRequest): Promise<TranslateQueryResult>;
}

// Keep `searchClient` exported for backwards compatibility with existing
// imports, but it now returns the broader `ApiClient`.
export function searchClient(baseUrl: string): ApiClient {
  const base = baseUrl.replace(/\/$/, "");

  async function call<T>(path: string, body: unknown): Promise<T> {
    let res: Response;
    try {
      res = await fetch(`${base}${path}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
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
        try {
          payload = await cloned.text();
        } catch {
          /* truly unreadable */
        }
      }
      throw new ApiError(res.status, `HTTP ${res.status}`, payload);
    }
    return (await res.json()) as T;
  }

  return {
    search(req) {
      return call<SearchResponse>("/search", req);
    },
    translateQuery(req) {
      return call<TranslateQueryResult>("/translate-query", req);
    },
  };
}

// Alias to encourage the new name in fresh code.
export const apiClient = searchClient;
