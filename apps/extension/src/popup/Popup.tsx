import { useEffect, useState } from "react";
import { SOURCE_IDS, type SourceId } from "@/schemas/capture";
import {
  getAll,
  isSiteEnabled,
  setSiteEnabled,
  type StorageShape,
} from "@/storage";

const SOURCE_LABELS: Record<SourceId, string> = {
  rentals_ca: "Rentals.ca",
  padmapper: "PadMapper",
  zumper: "Zumper",
  rew_ca: "REW.ca",
  liv_rent: "liv.rent",
  facebook_marketplace: "Facebook Marketplace",
};

// All six sources have shipped content scripts.
const SHIPPED: SourceId[] = [
  "rentals_ca",
  "padmapper",
  "zumper",
  "rew_ca",
  "liv_rent",
  "facebook_marketplace",
];

export function Popup() {
  const [state, setState] = useState<StorageShape | null>(null);

  useEffect(() => {
    void getAll().then(setState);
  }, []);

  if (!state) return <div>Loading…</div>;

  const paired = Boolean(state.pairing?.token);
  const today = state.capturedToday;
  const totalToday = Object.values(today.bySite ?? {}).reduce<number>((a, b) => a + (b ?? 0), 0);

  async function toggle(source: SourceId, next: boolean) {
    await setSiteEnabled(source, next);
    setState(await getAll());
  }

  return (
    <div>
      <header style={{ marginBottom: 8 }}>
        <strong>RentWise Capture</strong>
        <div style={{ color: paired ? "#0a7" : "#a30", marginTop: 2 }}>
          {paired ? "✅ Paired" : "⚠️ Not paired"}
        </div>
        <div style={{ color: "#666", marginTop: 2 }}>Captured today: {totalToday}</div>
      </header>

      <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {SOURCE_IDS.map((id) => {
          const shipped = SHIPPED.includes(id);
          const enabled = state.enabledSites[id] !== false;
          const health = state.health[id];
          const count = today.bySite[id] ?? 0;
          return (
            <li
              key={id}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                padding: "6px 0",
                borderTop: "1px solid #eee",
                opacity: shipped ? 1 : 0.5,
              }}
            >
              <input
                type="checkbox"
                checked={shipped && enabled}
                disabled={!shipped}
                onChange={(e) => void toggle(id, e.target.checked)}
              />
              <div style={{ flex: 1 }}>
                <div>{SOURCE_LABELS[id]}</div>
                <div style={{ color: "#888", fontSize: 11 }}>
                  {health?.status === "degraded" && "⚠️ Selectors broken"}
                  {health?.status === "ok" && `Schema ${health.schemaVersion}`}
                  {!health && "No captures yet"}
                </div>
              </div>
              <div style={{ color: "#666" }}>{count}</div>
            </li>
          );
        })}
      </ul>

      <footer style={{ marginTop: 12, display: "flex", gap: 8 }}>
        <button onClick={() => chrome.runtime.openOptionsPage()}>Settings</button>
      </footer>
    </div>
  );
}
