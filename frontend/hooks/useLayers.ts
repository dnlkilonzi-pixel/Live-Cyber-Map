import { useCallback, useEffect, useRef, useState } from "react";
import { LayerData, LayerDefinition, LayerState } from "../types/layers";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Layers enabled by default on first load
const DEFAULT_ENABLED: string[] = ["cyber_attacks", "country_risk"];

const STORAGE_KEY = "gid:enabledLayers";

function loadPersistedLayers(): LayerState {
  if (typeof window === "undefined") {
    const s: LayerState = {};
    DEFAULT_ENABLED.forEach((id) => (s[id] = true));
    return s;
  }
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw) as LayerState;
  } catch {
    // ignore
  }
  const s: LayerState = {};
  DEFAULT_ENABLED.forEach((id) => (s[id] = true));
  return s;
}

interface UseLayersReturn {
  availableLayers: LayerDefinition[];
  enabledLayers: LayerState;
  layerData: Record<string, LayerData>;
  isLoading: boolean;
  toggleLayer: (layerId: string) => void;
  enableLayer: (layerId: string) => void;
  disableLayer: (layerId: string) => void;
  setEnabledLayers: (state: LayerState) => void;
  fetchLayerData: (layerId: string) => Promise<void>;
}

export function useLayers(): UseLayersReturn {
  const [availableLayers, setAvailableLayers] = useState<LayerDefinition[]>([]);
  const [enabledLayers, setEnabledLayersState] = useState<LayerState>(() => loadPersistedLayers());
  const [layerData, setLayerData] = useState<Record<string, LayerData>>({});
  const [isLoading, setIsLoading] = useState(false);

  const mountedRef = useRef(true);
  const fetchingRef = useRef<Set<string>>(new Set());

  // Persist enabled layers to localStorage whenever they change
  useEffect(() => {
    if (typeof window !== "undefined") {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(enabledLayers));
      } catch {
        // ignore
      }
    }
    // layerData intentionally excluded – it is refreshed on a separate timer
    // and should not trigger an extra persistence write
  }, [enabledLayers]); // eslint-disable-line react-hooks/exhaustive-deps

  // Fetch layer definitions
  useEffect(() => {
    mountedRef.current = true;
    const loadLayers = async () => {
      setIsLoading(true);
      try {
        const resp = await fetch(`${API_URL}/api/layers`);
        if (resp.ok && mountedRef.current) {
          const layers: LayerDefinition[] = await resp.json();
          setAvailableLayers(layers);
        }
      } catch {
        // Silently fail
      } finally {
        if (mountedRef.current) setIsLoading(false);
      }
    };
    loadLayers();
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const fetchLayerData = useCallback(async (layerId: string) => {
    if (fetchingRef.current.has(layerId)) return;
    fetchingRef.current.add(layerId);
    try {
      const resp = await fetch(`${API_URL}/api/layers/${encodeURIComponent(layerId)}`);
      if (resp.ok && mountedRef.current) {
        const data: LayerData = await resp.json();
        setLayerData((prev) => ({ ...prev, [layerId]: data }));
      }
    } catch {
      // Silently fail
    } finally {
      fetchingRef.current.delete(layerId);
    }
  }, []);

  // Auto-fetch data for newly enabled layers
  useEffect(() => {
    const enabledIds = Object.keys(enabledLayers).filter((id) => enabledLayers[id]);
    enabledIds.forEach((id) => {
      if (!layerData[id] && !fetchingRef.current.has(id)) {
        fetchLayerData(id);
      }
    });
  }, [enabledLayers, fetchLayerData]); // eslint-disable-line react-hooks/exhaustive-deps

  const toggleLayer = useCallback((layerId: string) => {
    setEnabledLayersState((prev) => {
      const next = { ...prev, [layerId]: !prev[layerId] };
      return next;
    });
  }, []);

  const enableLayer = useCallback((layerId: string) => {
    setEnabledLayersState((prev) => ({ ...prev, [layerId]: true }));
  }, []);

  const disableLayer = useCallback((layerId: string) => {
    setEnabledLayersState((prev) => ({ ...prev, [layerId]: false }));
  }, []);

  const setEnabledLayers = useCallback((state: LayerState) => {
    setEnabledLayersState(state);
  }, []);

  return {
    availableLayers,
    enabledLayers,
    layerData,
    isLoading,
    toggleLayer,
    enableLayer,
    disableLayer,
    setEnabledLayers,
    fetchLayerData,
  };
}
