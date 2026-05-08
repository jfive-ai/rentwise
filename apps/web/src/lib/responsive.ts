/**
 * Phase 7 PR-C-1: viewport-aware layout helpers.
 *
 * The defaults are deliberately width-driven (not user-agent or platform):
 * a 1366px laptop screen wants the desktop layout regardless of OS, and a
 * 375px mobile browser wants the phone layout even when running in DevTools.
 */

import { useWindowDimensions } from "react-native";
import type { ViewMode } from "@/src/components/ResultsToolbar";

/** Bands match common Tailwind/MDN breakpoints; tweak in one place if we ever change them. */
export const BREAKPOINTS = {
  /** Below this width we treat the device as a phone (one-column, list default). */
  narrow: 640,
  /** Below this width the filter sidebar is stacked above the results. */
  stacked: 768,
  /** At/above this width we have room for split view side-by-side. */
  wide: 1280,
} as const;

/**
 * Pick the initial view mode based on the viewport width.
 *
 * - <640: list — phone-friendly density.
 * - >=1280: split — wide desktops can hold map + list side-by-side.
 * - otherwise: cards — original default.
 *
 * Honor user override: callers should only consult this on first mount, then
 * stop applying it once the user has manually picked a view from the toolbar.
 */
export function defaultViewForWidth(width: number): ViewMode {
  if (width < BREAKPOINTS.narrow) return "list";
  if (width >= BREAKPOINTS.wide) return "split";
  return "cards";
}

export function isStacked(width: number): boolean {
  return width < BREAKPOINTS.stacked;
}

/**
 * Live viewport width. Thin wrapper around useWindowDimensions that exists
 * so tests can mock this single module instead of patching react-native.
 */
export function useViewportWidth(): number {
  return useWindowDimensions().width;
}
