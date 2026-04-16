/**
 * useSettings – persists user preferences to localStorage so the app
 * reopens exactly as the user left it.
 *
 * Stored keys:
 *   gid:theme          – active ThemeId
 *   gid:mapView        – "globe" | "flat"
 *   gid:leftPanel      – "dashboard" | "layers" | null
 *   gid:rightPanel     – "intel" | "financial" | "risk" | null
 *   gid:showFinancial  – boolean
 *   gid:enabledLayers  – JSON object { [layerId]: boolean }
 */

import { useCallback, useEffect, useRef } from "react";
import { ThemeId, DEFAULT_THEME } from "../lib/themes";
import { LayerState } from "../types/layers";

type MapView = "globe" | "flat";
type RightPanel = "intel" | "financial" | "risk" | null;
type LeftPanel = "dashboard" | "layers" | null;

export interface Settings {
  theme: ThemeId;
  mapView: MapView;
  leftPanel: LeftPanel;
  rightPanel: RightPanel;
  showFinancial: boolean;
  enabledLayers: LayerState;
}

const KEYS = {
  theme: "gid:theme",
  mapView: "gid:mapView",
  leftPanel: "gid:leftPanel",
  rightPanel: "gid:rightPanel",
  showFinancial: "gid:showFinancial",
  enabledLayers: "gid:enabledLayers",
} as const;

function read<T>(key: string, fallback: T): T {
  if (typeof window === "undefined") return fallback;
  try {
    const raw = localStorage.getItem(key);
    if (raw === null) return fallback;
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

function write<T>(key: string, value: T): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // localStorage can throw in private browsing mode with full storage
  }
}

/** Load persisted settings from localStorage (safe to call during SSR). */
export function loadSettings(): Settings {
  return {
    theme: read<ThemeId>(KEYS.theme, DEFAULT_THEME),
    mapView: read<MapView>(KEYS.mapView, "globe"),
    leftPanel: read<LeftPanel>(KEYS.leftPanel, "dashboard"),
    rightPanel: read<RightPanel>(KEYS.rightPanel, null),
    showFinancial: read<boolean>(KEYS.showFinancial, false),
    enabledLayers: read<LayerState>(KEYS.enabledLayers, {
      cyber_attacks: true,
      country_risk: true,
    }),
  };
}

/** Returns a stable save function that persists individual setting fields. */
export function usePersistSettings() {
  const saveTheme = useCallback((v: ThemeId) => write(KEYS.theme, v), []);
  const saveMapView = useCallback((v: MapView) => write(KEYS.mapView, v), []);
  const saveLeftPanel = useCallback((v: LeftPanel) => write(KEYS.leftPanel, v), []);
  const saveRightPanel = useCallback((v: RightPanel) => write(KEYS.rightPanel, v), []);
  const saveShowFinancial = useCallback((v: boolean) => write(KEYS.showFinancial, v), []);
  const saveEnabledLayers = useCallback((v: LayerState) => write(KEYS.enabledLayers, v), []);

  return {
    saveTheme,
    saveMapView,
    saveLeftPanel,
    saveRightPanel,
    saveShowFinancial,
    saveEnabledLayers,
  };
}
