import type {
  CapturePairResponse,
  LLMConnectionTestRequest,
  LLMConnectionTestResult,
  LLMSettingsPublic,
  LLMSettingsUpdate,
  SaveSearchRequest,
  SavedSearchListResponse,
  SavedSearchResponse,
  SearchRequest,
  SearchResponse,
  TranslateQueryRequest,
  TranslateQueryResult,
  WebPushPublicKeyResponse,
  WebPushSubscribeRequest,
  WebPushSubscribeResponse,
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
  getSettings(): Promise<LLMSettingsPublic | null>;
  putSettings(body: LLMSettingsUpdate): Promise<LLMSettingsPublic>;
  testConnection(body: LLMConnectionTestRequest): Promise<LLMConnectionTestResult>;
  getCapturePair(): Promise<CapturePairResponse>;
  rotateCapturePair(): Promise<CapturePairResponse>;
  saveSearch(req: SaveSearchRequest): Promise<SavedSearchResponse>;
  listSavedSearches(): Promise<SavedSearchListResponse>;
  deleteSavedSearch(cacheKey: string): Promise<void>;
  getWebPushPublicKey(): Promise<WebPushPublicKeyResponse | null>;
  subscribeWebPush(req: WebPushSubscribeRequest): Promise<WebPushSubscribeResponse>;
  unsubscribeWebPush(id: number): Promise<void>;
}

type HttpMethod = "GET" | "POST" | "PUT" | "DELETE";

// Keep `searchClient` exported for backwards compatibility with existing
// imports, but it now returns the broader `ApiClient`.
export function searchClient(baseUrl: string): ApiClient {
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
    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  }

  return {
    search(req) {
      return request<SearchResponse>("POST", "/search", req);
    },
    translateQuery(req) {
      return request<TranslateQueryResult>("POST", "/translate-query", req);
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
    getCapturePair() {
      return request<CapturePairResponse>("GET", "/capture/pair");
    },
    rotateCapturePair() {
      return request<CapturePairResponse>("POST", "/capture/pair/rotate");
    },
    saveSearch(req) {
      return request<SavedSearchResponse>("POST", "/searches", req);
    },
    listSavedSearches() {
      return request<SavedSearchListResponse>("GET", "/searches");
    },
    async deleteSavedSearch(cacheKey: string) {
      await request<void>(
        "DELETE",
        `/searches/${encodeURIComponent(cacheKey)}`,
      );
    },
    async getWebPushPublicKey() {
      try {
        return await request<WebPushPublicKeyResponse>(
          "GET",
          "/notifications/web-push/public-key",
        );
      } catch (e) {
        // Server returns 503 when web push isn't configured. The UI
        // surfaces "browser notifications unavailable" rather than a
        // hard error in that case.
        if (e instanceof ApiError && e.status === 503) return null;
        throw e;
      }
    },
    subscribeWebPush(req) {
      return request<WebPushSubscribeResponse>(
        "POST",
        "/notifications/web-push/subscribe",
        req,
      );
    },
    async unsubscribeWebPush(id: number) {
      await request<void>(
        "DELETE",
        `/notifications/web-push/subscribe/${id}`,
      );
    },
  };
}

// Alias to encourage the new name in fresh code.
export const apiClient = searchClient;
