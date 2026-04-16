// Theme system – supports cyber, tech, and finance variants.
// Themes are applied via CSS custom properties on :root.

export type ThemeId = "cyber" | "tech" | "finance";

export interface Theme {
  id: ThemeId;
  name: string;
  description: string;
  icon: string;
  // CSS variable values
  vars: Record<string, string>;
  // Globe appearance
  globe: {
    imageUrl: string;
    backgroundColor: string;
    atmosphereColor: string;
    arcColor: string;
  };
  // Tailwind class overrides
  accentClass: string;
  panelClass: string;
}

export const THEMES: Record<ThemeId, Theme> = {
  cyber: {
    id: "cyber",
    name: "Cyber Ops",
    description: "Dark matrix aesthetic – focused on threat intelligence",
    icon: "🛡️",
    vars: {
      "--color-accent": "#00ff88",
      "--color-accent-2": "#00ffff",
      "--color-accent-3": "#ff4444",
      "--color-bg": "#000011",
      "--color-panel": "rgba(0,0,30,0.85)",
      "--color-border": "rgba(0,255,136,0.25)",
      "--color-text": "#e2e8f0",
      "--color-text-muted": "#64748b",
    },
    globe: {
      imageUrl: "https://unpkg.com/three-globe/example/img/earth-dark.jpg",
      backgroundColor: "#000011",
      atmosphereColor: "#1a237e",
      arcColor: "#00ff88",
    },
    accentClass: "text-green-400",
    panelClass: "bg-black/80 border-green-900/40",
  },
  tech: {
    id: "tech",
    name: "Tech Command",
    description: "Blue-toned tech-focused view for technology intelligence",
    icon: "🖥️",
    vars: {
      "--color-accent": "#60a5fa",
      "--color-accent-2": "#a78bfa",
      "--color-accent-3": "#34d399",
      "--color-bg": "#040714",
      "--color-panel": "rgba(4,7,28,0.90)",
      "--color-border": "rgba(96,165,250,0.25)",
      "--color-text": "#e2e8f0",
      "--color-text-muted": "#64748b",
    },
    globe: {
      imageUrl: "https://unpkg.com/three-globe/example/img/earth-blue-marble.jpg",
      backgroundColor: "#040714",
      atmosphereColor: "#1e3a5f",
      arcColor: "#60a5fa",
    },
    accentClass: "text-blue-400",
    panelClass: "bg-slate-900/85 border-blue-900/40",
  },
  finance: {
    id: "finance",
    name: "Finance Center",
    description: "Gold-toned financial market intelligence dashboard",
    icon: "💹",
    vars: {
      "--color-accent": "#fbbf24",
      "--color-accent-2": "#34d399",
      "--color-accent-3": "#f87171",
      "--color-bg": "#080500",
      "--color-panel": "rgba(12,8,0,0.90)",
      "--color-border": "rgba(251,191,36,0.20)",
      "--color-text": "#e2e8f0",
      "--color-text-muted": "#64748b",
    },
    globe: {
      imageUrl: "https://unpkg.com/three-globe/example/img/earth-night.jpg",
      backgroundColor: "#080500",
      atmosphereColor: "#3d2b00",
      arcColor: "#fbbf24",
    },
    accentClass: "text-yellow-400",
    panelClass: "bg-amber-950/85 border-amber-900/30",
  },
};

export const DEFAULT_THEME: ThemeId = "cyber";

export function applyTheme(themeId: ThemeId): void {
  if (typeof document === "undefined") return;
  const theme = THEMES[themeId];
  const root = document.documentElement;
  for (const [key, value] of Object.entries(theme.vars)) {
    root.style.setProperty(key, value);
  }
  root.setAttribute("data-theme", themeId);
}
