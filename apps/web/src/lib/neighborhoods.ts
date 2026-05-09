/**
 * User-typed neighborhood label → official City of Vancouver
 * `local-area-boundary` name. Mirrors the backend's resolver in
 * `apps/api/rentwise/enrichment/neighborhoods.py`. Keep the two in
 * sync — when one changes, change both.
 *
 * Anything not in this map passes through unchanged. Comparison is
 * case-insensitive at the call site.
 */
const ALIASES: Record<string, string> = {
  dunbar: "Dunbar-Southlands",
  southlands: "Dunbar-Southlands",
  "point grey": "West Point Grey",
  "pt grey": "West Point Grey",
  kits: "Kitsilano",
  "the drive": "Grandview-Woodland",
  "commercial drive": "Grandview-Woodland",
  "main street": "Mount Pleasant",
  main: "Mount Pleasant",
  "olympic village": "Mount Pleasant",
  "false creek": "Mount Pleasant",
  cambie: "South Cambie",
  yaletown: "Downtown",
  "coal harbour": "Downtown",
  gastown: "Downtown",
  chinatown: "Strathcona",
  "south granville": "Fairview",
};

const UMBRELLAS: Record<string, string[]> = {
  "east van": [
    "Grandview-Woodland",
    "Hastings-Sunrise",
    "Kensington-Cedar Cottage",
    "Killarney",
    "Mount Pleasant",
    "Renfrew-Collingwood",
    "Riley Park",
    "Strathcona",
    "Sunset",
    "Victoria-Fraserview",
  ],
  "east vancouver": [
    "Grandview-Woodland",
    "Hastings-Sunrise",
    "Kensington-Cedar Cottage",
    "Killarney",
    "Mount Pleasant",
    "Renfrew-Collingwood",
    "Riley Park",
    "Strathcona",
    "Sunset",
    "Victoria-Fraserview",
  ],
  "west side": [
    "Arbutus Ridge",
    "Dunbar-Southlands",
    "Fairview",
    "Kerrisdale",
    "Kitsilano",
    "Marpole",
    "Oakridge",
    "Shaughnessy",
    "South Cambie",
    "West Point Grey",
  ],
  westside: [
    "Arbutus Ridge",
    "Dunbar-Southlands",
    "Fairview",
    "Kerrisdale",
    "Kitsilano",
    "Marpole",
    "Oakridge",
    "Shaughnessy",
    "South Cambie",
    "West Point Grey",
  ],
};

/** Single-name alias resolution. Returns the input unchanged if no alias matches. */
export function resolveNeighborhoodAlias(name: string): string {
  const key = name.trim().toLowerCase();
  if (UMBRELLAS[key]) {
    // Umbrella expanding into multiple polygons isn't representable in a
    // single-string return — the caller (e.g. the map highlighter) uses
    // `expandNeighborhoodNames` for the multi-polygon case.
    return name;
  }
  return ALIASES[key] ?? name;
}

/** Expands aliases (incl. umbrellas) into one or more official names. */
export function expandNeighborhoodNames(names: string[]): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  const add = (n: string) => {
    if (!seen.has(n)) {
      seen.add(n);
      out.push(n);
    }
  };
  for (const raw of names) {
    const key = raw.trim().toLowerCase();
    if (!key) continue;
    if (UMBRELLAS[key]) {
      UMBRELLAS[key].forEach(add);
    } else if (ALIASES[key]) {
      add(ALIASES[key]);
    } else {
      add(raw);
    }
  }
  return out;
}
