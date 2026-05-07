import type {
  LLMConnectionTestRequest,
  LLMConnectionTestResult,
  LLMSettingsPublic,
  LLMSettingsUpdate,
  SearchRequest,
  SearchResponse,
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

export interface SearchClient {
  search(req: SearchRequest): Promise<SearchResponse>;
  getSettings(): Promise<LLMSettingsPublic | null>;
  putSettings(body: LLMSettingsUpdate): Promise<LLMSettingsPublic>;
  testConnection(body: LLMConnectionTestRequest): Promise<LLMConnectionTestResult>;
}

type HttpMethod = "GET" | "POST" | "PUT";

export function searchClient(baseUrl: string): SearchClient {
  const root = baseUrl.replace(/\/$/, "");

  async function request<T>(method: HttpMethod, path: string, body?: unknown): Promise<T> {
    const url = `${root}${path}`;
    const init: RequestInit = { method };
    if (body !== undefined) {
      init.headers = { "content-type": "application/json" };
      init.body = JSON.stringify(body);
    }
    let res: Response;
    try {
      res = await fetch(url, init);
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
      return request<SearchResponse>("POST", "/search", req);
    },
    async getSettings() {
      try {
        return await request<LLMSettingsPublic>("GET", "/settings/llm");
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) return null;
        throw e;
      }
    },
    putSettings(body) {
      return request<LLMSettingsPublic>("PUT", "/settings/llm", body);
    },
    testConnection(body) {
      return request<LLMConnectionTestResult>("POST", "/settings/llm/test", body);
    },
  };
}
