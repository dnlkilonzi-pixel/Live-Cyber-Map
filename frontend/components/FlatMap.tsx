/**
 * FlatMap – 2D interactive map using Leaflet + OpenStreetMap tiles.
 *
 * Rendered via the browser-only react-leaflet library (no API key required).
 * Displays all enabled data layers as circle markers on the 2D surface.
 */
import { useEffect, useRef } from "react";
import { AttackEvent } from "../types/attack";
import { LayerData, LayerDefinition, LayerState } from "../types/layers";
import { CountryRisk } from "../types/intelligence";

// These imports are dynamic (browser-only) – loaded lazily by the parent page.
// We declare types here to keep the component file clean.
declare global {
  interface Window {
    L: typeof import("leaflet");
  }
}

interface FlatMapProps {
  attacks: AttackEvent[];
  enabledLayers: LayerState;
  layerDefinitions: LayerDefinition[];
  layerData: Record<string, LayerData>;
  riskScores: CountryRisk[];
  onCountryClick?: (iso2: string) => void;
}

export default function FlatMap({
  attacks,
  enabledLayers,
  layerDefinitions,
  layerData,
  riskScores,
  onCountryClick,
}: FlatMapProps) {
  const mapRef = useRef<import("leaflet").Map | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const attackLayerRef = useRef<import("leaflet").LayerGroup | null>(null);
  const dataLayerRefs = useRef<
    Record<string, import("leaflet").LayerGroup>
  >({});

  // Initialise Leaflet map
  useEffect(() => {
    if (typeof window === "undefined" || mapRef.current) return;

    const initMap = async () => {
      // Dynamically import leaflet to avoid SSR issues
      const L = (await import("leaflet")).default;
      // Fix default marker icon paths broken by webpack asset hashing.
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      delete (L.Icon.Default.prototype as any)._getIconUrl;
      L.Icon.Default.mergeOptions({
        iconUrl: "/leaflet/marker-icon.png",
        iconRetinaUrl: "/leaflet/marker-icon-2x.png",
        shadowUrl: "/leaflet/marker-shadow.png",
      });

      if (!containerRef.current || mapRef.current) return;

      const map = L.map(containerRef.current, {
        center: [20, 0],
        zoom: 2,
        zoomControl: true,
        attributionControl: true,
      });

      // Dark tile layer (CartoDB Dark Matter – free, no key)
      L.tileLayer(
        "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
        {
          attribution:
            '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
          subdomains: "abcd",
          maxZoom: 19,
        }
      ).addTo(map);

      attackLayerRef.current = L.layerGroup().addTo(map);
      mapRef.current = map;
    };

    initMap();

    return () => {
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
      }
    };
  }, []);

  // Update attack arc markers
  useEffect(() => {
    if (!mapRef.current || !attackLayerRef.current) return;

    const updateAttacks = async () => {
      const L = (await import("leaflet")).default;
      attackLayerRef.current!.clearLayers();

      const recent = attacks.slice(0, 100);
      for (const attack of recent) {
        const color = getAttackColor(attack.attack_type);
        // Source marker (faded)
        L.circleMarker([attack.source_lat, attack.source_lng], {
          radius: 3,
          color,
          fillColor: color,
          fillOpacity: 0.4,
          weight: 1,
        }).addTo(attackLayerRef.current!);

        // Destination marker (bright)
        L.circleMarker([attack.dest_lat, attack.dest_lng], {
          radius: 5,
          color,
          fillColor: color,
          fillOpacity: 0.8,
          weight: 1,
        })
          .bindPopup(
            `<b>${attack.attack_type}</b><br/>
             ${attack.source_country} → ${attack.dest_country}<br/>
             Severity: ${attack.severity}/10`
          )
          .addTo(attackLayerRef.current!);

        // Line connecting source → dest
        L.polyline(
          [
            [attack.source_lat, attack.source_lng],
            [attack.dest_lat, attack.dest_lng],
          ],
          { color, weight: 1, opacity: 0.35 }
        ).addTo(attackLayerRef.current!);
      }
    };

    updateAttacks();
  }, [attacks]);

  // Update generic data layers
  useEffect(() => {
    if (!mapRef.current) return;

    const updateLayers = async () => {
      const L = (await import("leaflet")).default;

      for (const def of layerDefinitions) {
        const enabled = enabledLayers[def.id];
        const existing = dataLayerRefs.current[def.id];

        if (!enabled) {
          if (existing) {
            mapRef.current!.removeLayer(existing);
            delete dataLayerRefs.current[def.id];
          }
          continue;
        }

        // Skip attack layer – handled separately
        if (def.id === "cyber_attacks") continue;

        const data = layerData[def.id];
        if (!data) continue;

        // Remove old layer
        if (existing) mapRef.current!.removeLayer(existing);

        const group = L.layerGroup();

        // Country risk choropleth via circle markers
        if (def.id === "country_risk") {
          for (const risk of riskScores) {
            const r = risk.risk_score / 100;
            const color = riskColor(r);
            const marker = L.circleMarker([risk.lat, risk.lng], {
              radius: 8 + r * 12,
              color,
              fillColor: color,
              fillOpacity: 0.55,
              weight: 1,
            })
              .bindPopup(
                `<b>${risk.name}</b><br/>
                 Risk: ${risk.risk_score.toFixed(0)}/100<br/>
                 Cyber: ${risk.cyber_score.toFixed(0)} | News: ${risk.news_score.toFixed(0)}`
              );
            if (onCountryClick) {
              marker.on("click", () => onCountryClick(risk.iso2));
            }
            marker.addTo(group);
          }
        } else {
          for (const feature of data.features) {
            L.circleMarker([feature.lat, feature.lng], {
              radius: 4 + feature.value * 8,
              color: def.color,
              fillColor: def.color,
              fillOpacity: 0.65,
              weight: 1,
            })
              .bindPopup(`<b>${def.name}</b><br/>${feature.label}`)
              .addTo(group);
          }
        }

        group.addTo(mapRef.current!);
        dataLayerRefs.current[def.id] = group;
      }
    };

    updateLayers();
  }, [enabledLayers, layerData, layerDefinitions, riskScores]);

  return (
    <div
      ref={containerRef}
      style={{ width: "100%", height: "100%", background: "#10121c" }}
    />
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getAttackColor(attackType: string): string {
  const colors: Record<string, string> = {
    DDoS: "#ff4444",
    Malware: "#ff8800",
    Phishing: "#ffff00",
    Ransomware: "#ff0088",
    Intrusion: "#00ffff",
    BruteForce: "#ff00ff",
    SQLInjection: "#00ff88",
    XSS: "#8888ff",
    ZeroDay: "#ffffff",
  };
  return colors[attackType] ?? "#ffffff";
}

function riskColor(normalized: number): string {
  // green (0) → yellow (0.5) → red (1)
  if (normalized < 0.5) {
    const g = Math.round(255 - normalized * 2 * 55);
    return `rgb(255,${g},0)`;
  }
  const r = Math.round(255);
  const g = Math.round(255 * (1 - (normalized - 0.5) * 2));
  return `rgb(${r},${Math.max(0, g)},0)`;
}
