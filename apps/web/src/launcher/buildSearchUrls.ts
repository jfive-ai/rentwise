/**
 * Pure helper: NormalizedQuery → one URL per source with each source's
 * unsupported-filter list. Tested independently of any window/DOM.
 */

import type { NormalizedQuery } from "@/src/api/types";
import { SOURCES, type SourceDef, type SourceId } from "./sources";

export interface SourceLaunchPlan {
  id: SourceId;
  label: string;
  url: string;
  unsupported: string[];
}

export function buildSearchUrls(
  query: NormalizedQuery,
  enabled: ReadonlySet<SourceId> = new Set(SOURCES.map((s) => s.id)),
): SourceLaunchPlan[] {
  const plans: SourceLaunchPlan[] = [];
  for (const source of SOURCES) {
    if (!enabled.has(source.id)) continue;
    const built = source.build(query);
    if (!built) continue;
    plans.push({
      id: source.id,
      label: source.label,
      url: built.url,
      unsupported: built.unsupported,
    });
  }
  return plans;
}

export type { SourceDef, SourceId };
