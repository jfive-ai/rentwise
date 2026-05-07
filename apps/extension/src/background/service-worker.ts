/**
 * Background service worker.
 *
 * Receives messages from content scripts, validates them, and POSTs to the
 * user's local RentWise API. The content script never touches the network
 * to a non-source origin — that responsibility lives here so the host
 * permissions for 127.0.0.1/localhost stay scoped to the worker.
 */

import {
  CaptureHealthPayloadSchema,
  CapturePayloadSchema,
  CaptureResponseSchema,
  type CaptureHealthPayload,
  type CapturePayload,
  type CaptureResponse,
} from "@/schemas/capture";
import { bumpCapturedToday, getPairing, setSiteHealth } from "@/storage";

type CaptureRequest =
  | { kind: "capture"; payload: CapturePayload }
  | { kind: "health"; payload: CaptureHealthPayload };

type CaptureResult =
  | { ok: true; response: CaptureResponse }
  | { ok: false; error: string };

async function postCapture(payload: CapturePayload): Promise<CaptureResult> {
  const pairing = await getPairing();
  if (!pairing) {
    return { ok: false, error: "not_paired" };
  }
  try {
    const res = await fetch(`${pairing.serverUrl}/capture`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-RentWise-Token": pairing.token,
      },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      return { ok: false, error: `http_${res.status}` };
    }
    const json = await res.json();
    const parsed = CaptureResponseSchema.safeParse(json);
    if (!parsed.success) {
      return { ok: false, error: "bad_response_shape" };
    }
    await bumpCapturedToday(payload.source, parsed.data.accepted);
    await setSiteHealth(payload.source, {
      status: "ok",
      schemaVersion: payload.schema_version,
      at: Date.now(),
    });
    return { ok: true, response: parsed.data };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return { ok: false, error: `network_${message}` };
  }
}

async function postHealth(payload: CaptureHealthPayload): Promise<CaptureResult> {
  const pairing = await getPairing();
  if (!pairing) {
    return { ok: false, error: "not_paired" };
  }
  try {
    const res = await fetch(`${pairing.serverUrl}/capture/health`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-RentWise-Token": pairing.token,
      },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      return { ok: false, error: `http_${res.status}` };
    }
    await setSiteHealth(payload.source, {
      status: "degraded",
      schemaVersion: payload.schema_version,
      reason: payload.reason,
      at: Date.now(),
    });
    return {
      ok: true,
      response: { accepted: 0, skipped_duplicates: 0, errors: [] },
    };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return { ok: false, error: `network_${message}` };
  }
}

chrome.runtime.onMessage.addListener(
  (message: unknown, _sender, sendResponse: (r: CaptureResult) => void) => {
    if (!message || typeof message !== "object" || !("kind" in message)) {
      sendResponse({ ok: false, error: "bad_message" });
      return false;
    }
    const req = message as CaptureRequest;
    if (req.kind === "capture") {
      const parsed = CapturePayloadSchema.safeParse(req.payload);
      if (!parsed.success) {
        sendResponse({ ok: false, error: "bad_payload" });
        return false;
      }
      postCapture(parsed.data).then(sendResponse);
      return true; // async sendResponse
    }
    if (req.kind === "health") {
      const parsed = CaptureHealthPayloadSchema.safeParse(req.payload);
      if (!parsed.success) {
        sendResponse({ ok: false, error: "bad_health_payload" });
        return false;
      }
      postHealth(parsed.data).then(sendResponse);
      return true;
    }
    sendResponse({ ok: false, error: "unknown_kind" });
    return false;
  },
);
