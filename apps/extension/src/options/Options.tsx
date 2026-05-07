import { useEffect, useState } from "react";
import { clearPairing, getPairing, setPairing } from "@/storage";

type Status = { kind: "idle" } | { kind: "ok"; message: string } | { kind: "err"; message: string };

const DEFAULT_SERVER = "http://127.0.0.1:8000";

export function Options() {
  const [serverUrl, setServerUrl] = useState(DEFAULT_SERVER);
  const [token, setToken] = useState("");
  const [status, setStatus] = useState<Status>({ kind: "idle" });

  useEffect(() => {
    void getPairing().then((p) => {
      if (p) {
        setServerUrl(p.serverUrl);
        setToken(p.token);
      }
    });
  }, []);

  async function save() {
    setStatus({ kind: "idle" });
    if (!serverUrl.startsWith("http://") && !serverUrl.startsWith("https://")) {
      setStatus({ kind: "err", message: "Server URL must start with http:// or https://" });
      return;
    }
    if (token.trim().length < 16) {
      setStatus({ kind: "err", message: "Token looks too short — paste the full value from Settings → Extension" });
      return;
    }
    // Validate by hitting GET /capture/pair (web-app facing, no token required).
    // A successful response means we can reach the API.
    try {
      const res = await fetch(`${serverUrl.replace(/\/$/, "")}/capture/pair`);
      if (!res.ok) {
        setStatus({ kind: "err", message: `API responded ${res.status}` });
        return;
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setStatus({ kind: "err", message: `Could not reach API: ${msg}` });
      return;
    }
    await setPairing({ serverUrl: serverUrl.replace(/\/$/, ""), token: token.trim() });
    setStatus({ kind: "ok", message: "Saved." });
  }

  async function unpair() {
    await clearPairing();
    setToken("");
    setStatus({ kind: "ok", message: "Pairing cleared." });
  }

  return (
    <div>
      <h1>RentWise Capture</h1>
      <p>
        Paste the token shown in your RentWise app under <strong>Settings → Extension</strong>.
        The extension stores both values locally; nothing is sent to any third party.
      </p>

      <div className="row">
        <label htmlFor="server">RentWise API URL</label>
        <input
          id="server"
          type="text"
          value={serverUrl}
          onChange={(e) => setServerUrl(e.target.value)}
        />
        <div className="hint">Default: {DEFAULT_SERVER}</div>
      </div>

      <div className="row">
        <label htmlFor="token">Pairing token</label>
        <input
          id="token"
          type="password"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          placeholder="paste from Settings → Extension"
        />
      </div>

      <div className="row" style={{ display: "flex", gap: 8 }}>
        <button onClick={() => void save()}>Save & validate</button>
        <button onClick={() => void unpair()}>Clear pairing</button>
      </div>

      {status.kind === "ok" && <div className="row ok">{status.message}</div>}
      {status.kind === "err" && <div className="row err">{status.message}</div>}
    </div>
  );
}
