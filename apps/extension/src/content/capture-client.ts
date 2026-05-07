/**
 * Content-script-side helper. Sends payloads to the background worker.
 * Content scripts never call fetch() directly — they hand off here.
 */

import type {
  CaptureHealthPayload,
  CapturePayload,
  CaptureResponse,
} from "@/schemas/capture";

type SendResult =
  | { ok: true; response: CaptureResponse }
  | { ok: false; error: string };

export function sendCapture(payload: CapturePayload): Promise<SendResult> {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage({ kind: "capture", payload }, (resp: SendResult) => {
      if (chrome.runtime.lastError) {
        resolve({ ok: false, error: chrome.runtime.lastError.message ?? "runtime_error" });
        return;
      }
      resolve(resp);
    });
  });
}

export function sendHealth(payload: CaptureHealthPayload): Promise<SendResult> {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage({ kind: "health", payload }, (resp: SendResult) => {
      if (chrome.runtime.lastError) {
        resolve({ ok: false, error: chrome.runtime.lastError.message ?? "runtime_error" });
        return;
      }
      resolve(resp);
    });
  });
}
