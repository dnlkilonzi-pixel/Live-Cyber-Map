// Data layer type definitions

export type LayerCategory =
  | "security"
  | "military"
  | "disasters"
  | "financial"
  | "infrastructure"
  | "geopolitical"
  | "health"
  | "environment"
  | "maritime";

export interface LayerDefinition {
  id: string;
  category: LayerCategory;
  name: string;
  description: string;
  icon: string;
  color: string;
  live: boolean;
}

export interface LayerFeature {
  id: string;
  type: string;
  lat: number;
  lng: number;
  value: number; // 0–1 normalized
  label: string;
  extra: Record<string, unknown>;
}

export interface LayerData {
  layer_id: string;
  features: LayerFeature[];
  last_updated: number;
  count: number;
}

export type LayerState = Record<string, boolean>; // layer_id -> enabled

// Category metadata for display
export const CATEGORY_META: Record<
  LayerCategory,
  { label: string; icon: string; color: string }
> = {
  security: { label: "Security & Cyber", icon: "🛡️", color: "#ff4444" },
  military: { label: "Military & Conflict", icon: "⚔️", color: "#8b4513" },
  disasters: { label: "Disasters & Hazards", icon: "⚠️", color: "#ff6600" },
  financial: { label: "Financial", icon: "📈", color: "#00ff88" },
  infrastructure: { label: "Infrastructure", icon: "🏗️", color: "#00bcd4" },
  geopolitical: { label: "Geopolitical", icon: "🌍", color: "#ab47bc" },
  health: { label: "Health & Humanitarian", icon: "🏥", color: "#ce93d8" },
  environment: { label: "Environment & Space", icon: "🌿", color: "#80cbc4" },
  maritime: { label: "Maritime", icon: "⚓", color: "#40c4ff" },
};
