/**
 * CountryRiskPanel – ranked list of country risk scores.
 * Shows the top-N highest-risk countries with breakdown bars.
 * Clicking a country row loads a 24-hour risk trend sparkline.
 */
import { motion } from "framer-motion";
import { useCallback, useState } from "react";
import { CountryRisk } from "../types/intelligence";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface TrendPoint {
  ts: number;
  risk_score: number;
}

interface CountryRiskPanelProps {
  riskScores: CountryRisk[];
  isLoading: boolean;
  onClose: () => void;
}

export default function CountryRiskPanel({
  riskScores,
  isLoading,
  onClose,
}: CountryRiskPanelProps) {
  const top = riskScores.slice(0, 25);
  const [expandedIso2, setExpandedIso2] = useState<string | null>(null);
  const [trendData, setTrendData] = useState<Record<string, TrendPoint[]>>({});
  const [loadingTrend, setLoadingTrend] = useState<string | null>(null);

  const loadTrend = useCallback(async (iso2: string) => {
    if (trendData[iso2]) return; // already cached
    setLoadingTrend(iso2);
    try {
      const resp = await fetch(
        `${API_URL}/api/intelligence/risk/${iso2}/trend?hours=24`
      );
      if (resp.ok) {
        const json = await resp.json();
        setTrendData((prev) => ({ ...prev, [iso2]: json.points ?? [] }));
      }
    } catch {
      // Silently ignore
    } finally {
      setLoadingTrend(null);
    }
  }, [trendData]);

  const toggleExpand = (iso2: string) => {
    if (expandedIso2 === iso2) {
      setExpandedIso2(null);
    } else {
      setExpandedIso2(iso2);
      loadTrend(iso2);
    }
  };

  const riskColor = (score: number): string => {
    if (score >= 80) return "#ff2200";
    if (score >= 60) return "#ff6600";
    if (score >= 40) return "#ffaa00";
    if (score >= 20) return "#88cc00";
    return "#00cc66";
  };

  const riskLabel = (score: number): string => {
    if (score >= 80) return "CRITICAL";
    if (score >= 60) return "HIGH";
    if (score >= 40) return "MEDIUM";
    if (score >= 20) return "LOW";
    return "MINIMAL";
  };

  return (
    <div className="flex flex-col h-full w-72 text-sm">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/10 shrink-0">
        <div>
          <span className="text-xs uppercase tracking-widest text-[var(--color-accent)] font-bold">
            Country Risk
          </span>
          <div className="text-xs text-gray-600 mt-0.5">
            {riskScores.length} countries tracked
          </div>
        </div>
        <button
          onClick={onClose}
          className="text-gray-500 hover:text-white text-lg leading-none p-1"
          aria-label="Close risk panel"
        >
          ×
        </button>
      </div>

      {/* Legend */}
      <div className="px-3 py-2 border-b border-white/10 shrink-0">
        <div className="flex items-center gap-2 flex-wrap">
          {[
            { label: "CRITICAL", color: "#ff2200" },
            { label: "HIGH", color: "#ff6600" },
            { label: "MEDIUM", color: "#ffaa00" },
            { label: "LOW", color: "#88cc00" },
          ].map((item) => (
            <div key={item.label} className="flex items-center gap-1">
              <div
                className="w-2 h-2 rounded-full"
                style={{ backgroundColor: item.color }}
              />
              <span className="text-xs text-gray-500">{item.label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Risk list */}
      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="p-3 space-y-3">
            {Array.from({ length: 10 }).map((_, i) => (
              <div key={i} className="space-y-1">
                <div className="h-3 bg-white/5 rounded animate-pulse w-32" />
                <div className="h-2 bg-white/5 rounded animate-pulse w-full" />
              </div>
            ))}
          </div>
        ) : (
          top.map((country, idx) => {
            const color = riskColor(country.risk_score);
            const label = riskLabel(country.risk_score);
            const isExpanded = expandedIso2 === country.iso2;
            const trend = trendData[country.iso2] ?? [];
            return (
              <div key={country.iso2}>
                <button
                  onClick={() => toggleExpand(country.iso2)}
                  className="w-full text-left px-3 py-2.5 border-b border-white/5 hover:bg-white/5 transition-colors"
                >
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-gray-600 font-mono w-5">
                        {idx + 1}
                      </span>
                      <span className="text-xs text-gray-200 font-medium truncate max-w-[130px]">
                        {country.name}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <span
                        className="text-xs font-mono font-bold px-1.5 py-0.5 rounded"
                        style={{
                          color,
                          backgroundColor: color + "22",
                        }}
                      >
                        {label}
                      </span>
                      <span
                        className="text-xs font-mono font-bold"
                        style={{ color }}
                      >
                        {country.risk_score.toFixed(0)}
                      </span>
                      <span className="text-gray-600 text-xs">
                        {isExpanded ? "▲" : "▼"}
                      </span>
                    </div>
                  </div>

                  {/* Composite bar */}
                  <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
                    <motion.div
                      className="h-full rounded-full"
                      style={{ backgroundColor: color }}
                      initial={{ width: 0 }}
                      animate={{ width: `${country.risk_score}%` }}
                      transition={{ duration: 0.6, ease: "easeOut" }}
                    />
                  </div>

                  {/* Sub-scores */}
                  <div className="flex items-center gap-3 mt-1">
                    <SubScore
                      label="Cyber"
                      value={country.cyber_score}
                      color="#ff4444"
                    />
                    <SubScore
                      label="News"
                      value={country.news_score}
                      color="#ffaa00"
                    />
                    <SubScore
                      label="Base"
                      value={country.stability_baseline}
                      color="#8888ff"
                    />
                    {country.attack_count_24h > 0 && (
                      <span className="text-xs text-gray-600 ml-auto">
                        {country.attack_count_24h} attacks
                      </span>
                    )}
                  </div>
                </button>

                {/* Sparkline expansion */}
                {isExpanded && (
                  <div className="px-3 py-2 bg-black/20 border-b border-white/5">
                    {loadingTrend === country.iso2 ? (
                      <div className="h-12 flex items-center justify-center">
                        <span className="text-xs text-gray-600 animate-pulse">
                          Loading trend…
                        </span>
                      </div>
                    ) : trend.length < 2 ? (
                      <div className="h-12 flex items-center justify-center">
                        <span className="text-xs text-gray-600">
                          No trend data yet — check back later
                        </span>
                      </div>
                    ) : (
                      <RiskSparkline points={trend} color={color} />
                    )}
                    <div className="text-xs text-gray-600 mt-1 text-center">
                      24-hour risk trend
                    </div>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

function SubScore({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: string;
}) {
  return (
    <div className="flex items-center gap-1">
      <span className="text-xs text-gray-600">{label}</span>
      <span className="text-xs font-mono" style={{ color }}>
        {value.toFixed(0)}
      </span>
    </div>
  );
}

/** Inline SVG sparkline – no external charting library needed. */
function RiskSparkline({
  points,
  color,
}: {
  points: TrendPoint[];
  color: string;
}) {
  const W = 220;
  const H = 40;
  const PAD = 4;

  const scores = points.map((p) => p.risk_score);
  const minVal = Math.min(...scores);
  const maxVal = Math.max(...scores);
  const range = maxVal - minVal || 1;

  const toX = (i: number) => PAD + (i / (points.length - 1)) * (W - PAD * 2);
  const toY = (v: number) => H - PAD - ((v - minVal) / range) * (H - PAD * 2);

  const pathD = points
    .map((p, i) => `${i === 0 ? "M" : "L"}${toX(i).toFixed(1)},${toY(p.risk_score).toFixed(1)}`)
    .join(" ");

  const areaD =
    pathD +
    ` L${toX(points.length - 1).toFixed(1)},${H - PAD} L${PAD},${H - PAD} Z`;

  const lastScore = scores[scores.length - 1];
  const firstScore = scores[0];
  const trend = lastScore - firstScore;

  return (
    <div>
      <svg
        width={W}
        height={H}
        viewBox={`0 0 ${W} ${H}`}
        aria-label="24-hour risk trend sparkline"
      >
        {/* Area fill */}
        <path d={areaD} fill={color} fillOpacity={0.1} />
        {/* Line */}
        <path d={pathD} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" />
        {/* Last value dot */}
        <circle
          cx={toX(points.length - 1)}
          cy={toY(lastScore)}
          r={2.5}
          fill={color}
        />
      </svg>
      <div className="flex justify-between text-xs font-mono mt-0.5">
        <span className="text-gray-600">{firstScore.toFixed(0)}</span>
        <span style={{ color }}>
          {trend >= 0 ? "+" : ""}
          {trend.toFixed(1)} pts
        </span>
        <span className="text-gray-600">{lastScore.toFixed(0)}</span>
      </div>
    </div>
  );
}
