import type {
  LLMConnectionTestRequest,
  LLMConnectionTestResult,
  LLMSettingsPublic,
  LLMSettingsUpdate,
  SaveSearchRequest,
  SavedSearchListResponse,
  SavedSearchResponse,
  SearchRequest,
  SearchResponse,
  SearchStreamEvent,
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
  /**
   * Streaming counterpart of {@link ApiClient.search} (issue #113). Yields
   * NDJSON events as the backend produces them, so the UI can render
   * listings before every adapter has finished. Pass an ``AbortSignal``
   * to cancel an in-flight stream — the backend cancels its adapter
   * tasks when the connection closes.
   */
  searchStream(
    req: SearchRequest,
    options?: { signal?: AbortSignal },
  ): AsyncIterable<SearchStreamEvent>;
  translateQuery(req: TranslateQueryRequest): Promise<TranslateQueryResult>;
  getSettings(): Promise<LLMSettingsPublic | null>;
  putSettings(body: LLMSettingsUpdate): Promise<LLMSettingsPublic>;
  testConnection(body: LLMConnectionTestRequest): Promise<LLMConnectionTestResult>;
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

  /**
   * Parse an NDJSON byte stream (one JSON object per `\n`-terminated line).
   *
   * Handles split frames (a chunk ends mid-line, the next chunk completes
   * it) and an optional trailing line that lacks a terminating newline.
   * Lines that fail to parse as JSON are dropped with a console warning
   * — better than crashing the whole stream over one malformed event.
   */
  async function* parseNdjson(
    body: ReadableStream<Uint8Array>,
  ): AsyncGenerator<SearchStreamEvent> {
    const reader = body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        if (value === undefined) continue;
        // Cross-realm Uint8Array safety: in jsdom + node:stream/web the
        // chunk's constructor comes from a different realm, so jsdom's
        // TextDecoder silently returns "" on it (`instanceof Uint8Array`
        // is false). Re-wrap into the local realm's Uint8Array so the
        // decoder treats it as bytes. In real browsers this is a no-op.
        let chunk: string;
        if (typeof value === "string") {
          chunk = value;
        } else {
          // ArrayBufferView-like: Uint8Array, Buffer, etc.
          const v = value as unknown as {
            buffer: ArrayBufferLike;
            byteOffset?: number;
            byteLength?: number;
          };
          const u8 = new Uint8Array(
            v.buffer,
            v.byteOffset ?? 0,
            v.byteLength ?? (value as unknown as { length: number }).length ?? 0,
          );
          chunk = decoder.decode(u8, { stream: true });
        }
        buf += chunk;
        let nl: number;
        while ((nl = buf.indexOf("\n")) >= 0) {
          const line = buf.slice(0, nl).trim();
          buf = buf.slice(nl + 1);
          if (line.length === 0) continue;
          try {
            yield JSON.parse(line) as SearchStreamEvent;
          } catch (e) {
            // eslint-disable-next-line no-console
            console.warn("searchStream: dropped malformed NDJSON line", line, e);
          }
        }
      }
      const tail = buf.trim();
      if (tail.length > 0) {
        try {
          yield JSON.parse(tail) as SearchStreamEvent;
        } catch (e) {
          // eslint-disable-next-line no-console
          console.warn("searchStream: dropped malformed NDJSON tail", tail, e);
        }
      }
    } finally {
      // Release the reader so the underlying connection can be torn
      // down; otherwise consumers that break early leak.
      reader.releaseLock();
    }
  }

  return {
    search(req) {
      return request<SearchResponse>("POST", "/search", req);
    },
    searchStream(req, options) {
      const url = `${root}/search/stream`;
      // The async generator captures `req`/`options` and starts the
      // fetch lazily on first iteration so a caller that constructs
      // the iterable but never iterates doesn't burn a request.
      return (async function* () {
        let res: Response;
        try {
          res = await fetch(url, {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify(req),
            signal: options?.signal,
          });
        } catch (e) {
          throw new ApiError(
            0,
            e instanceof Error ? e.message : String(e),
          );
        }
        if (!res.ok || !res.body) {
          let payload: unknown;
          try {
            payload = await res.json();
          } catch {
            try {
              payload = await res.text();
            } catch {
              /* unreadable */
            }
          }
          throw new ApiError(res.status, `HTTP ${res.status}`, payload);
        }
        yield* parseNdjson(res.body);
      })();
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
