/**
 * CountryDrilldown – modal showing full detail for a selected country.
 *
 * Sections:
 *   1. Risk breakdown (composite + sub-scores) + 24-hour sparkline
 *   2. Recent news items filtered by country name
 *   3. Relevant financial assets (index / currency for the country)
 *   4. Active cyber attacks from/to this country in the last 5 minutes
 */
import { useCallback, useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { CountryRisk, NewsItem } from "../types/intelligence";
import { MarketSummary, TickerQuote } from "../types/financial";
import { AttackEvent } from "../types/attack";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface TrendPoint {
  ts: number;
  risk_score: number;
  cyber_score: number;
  news_score: number;
}

// Map country names / iso2 codes to relevant financial symbols
const COUNTRY_ASSETS: Record<string, string[]> = {
  US: ["^GSPC", "^DJI", "^IXIC"],
  GB: ["^FTSE", "GBP/USD"],
  DE: ["^GDAXI", "EUR/USD"],
  FR: ["^FCHI", "EUR/USD"],
  JP: ["^N225", "USD/JPY"],
  CN: ["USD/CNY"],
  HK: ["^HSI"],
  KR: ["USD/KRW"],
  IN: ["USD/INR"],
  BR: ["USD/BRL"],
  AU: ["AUD/USD"],
  CA: ["USD/CAD"],
  CH: ["USD/CHF"],
};

interface Props {
  iso2: string;
  onClose: () => void;
  riskScores: CountryRisk[];
  news: NewsItem[];
  attacks: AttackEvent[];
  financialSummary: MarketSummary | null;
}

export default function CountryDrilldown({
  iso2,
  onClose,
  riskScores,
  news,
  attacks,
  financialSummary,
}: Props) {
  const risk = riskScores.find((r) => r.iso2 === iso2);
  const countryName = risk?.name ?? iso2;

  // Load 24-hour trend data for the sparkline
  const [trend, setTrend] = useState<TrendPoint[]>([]);
  const [trendLoading, setTrendLoading] = useState(false);

  const loadTrend = useCallback(async () => {
    setTrendLoading(true);
    try {
      const resp = await fetch(
        `${API_URL}/api/intelligence/risk/${iso2}/trend?hours=24`
      );
      if (resp.ok) {
        const json = await resp.json();
        setTrend(json.points ?? []);
      }
    } catch {
      // Silently ignore — sparkline is optional
    } finally {
      setTrendLoading(false);
    }
  }, [iso2]);

  useEffect(() => {
    loadTrend();
  }, [loadTrend]);

  // Filter news mentioning the country name
  const countryNews = news
    .filter((n) =>
      n.title.toLowerCase().includes(countryName.toLowerCase()) ||
      (n.summary ?? "").toLowerCase().includes(countryName.toLowerCase())
    )
    .slice(0, 8);

  // Relevant financial assets
  const relatedSymbols = COUNTRY_ASSETS[iso2] ?? [];
  const relatedAssets: TickerQuote[] = [];
  if (financialSummary) {
    const allTickers = [
      ...financialSummary.indices,
      ...financialSummary.forex,
      ...financialSummary.stocks,
    ];
    relatedSymbols.forEach((sym) => {
      const found = allTickers.find((t) => t.symbol === sym);
      if (found) relatedAssets.push(found);
    });
  }

  // Active attacks (last 5 min) from/to this country
  const fiveMinAgo = Date.now() / 1000 - 300;
  const activeAttacks = attacks
    .filter(
      (a) =>
        (a.source_country === countryName || a.dest_country === countryName) &&
        (a.timestamp ? new Date(a.timestamp).getTime() / 1000 > fiveMinAgo : true)
    )
    .slice(0, 10);

  const riskColor = (score: number) => {
    if (score >= 75) return "text-red-400";
    if (score >= 50) return "text-orange-400";
    if (score >= 25) return "text-yellow-400";
    return "text-green-400";
  };

  const formatPct = (v: number) => {
    const sign = v >= 0 ? "+" : "";
    return `${sign}${v.toFixed(2)}%`;
  };

  return (
    <AnimatePresence>
      <motion.div
        key="drilldown-backdrop"
        className="fixed inset-0 z-50 flex items-center justify-center"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
      >
        <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
        <motion.div
          key="drilldown-panel"
          initial={{ scale: 0.92, opacity: 0, y: 20 }}
          animate={{ scale: 1, opacity: 1, y: 0 }}
          exit={{ scale: 0.92, opacity: 0, y: 20 }}
          transition={{ type: "spring", damping: 25, stiffness: 300 }}
          className="relative z-10 w-full max-w-2xl max-h-[85vh] overflow-y-auto rounded-lg side-panel border border-white/10 shadow-2xl scrollbar-thin"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="sticky top-0 z-10 flex items-center justify-between px-5 py-4 border-b border-white/10 bg-black/80 backdrop-blur-md">
            <div>
              <h2 className="font-bold text-lg text-white">{countryName}</h2>
              <p className="text-xs text-gray-500 uppercase tracking-widest">{iso2} · Country Intelligence</p>
            </div>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-white text-2xl leading-none px-2"
              aria-label="Close"
            >
              ×
            </button>
          </div>

          <div className="p-5 space-y-6">
            {/* Risk breakdown */}
            {risk ? (
              <section>
                <h3 className="text-xs uppercase tracking-widest text-gray-500 mb-3">Risk Assessment</h3>
                <div className="grid grid-cols-2 gap-3">
                  <div className="col-span-2 flex items-center justify-between rounded bg-white/5 px-4 py-3">
                    <span className="text-sm text-gray-300">Composite Risk</span>
                    <span className={`text-2xl font-bold font-mono ${riskColor(risk.risk_score)}`}>
                      {risk.risk_score.toFixed(0)}<span className="text-sm text-gray-500">/100</span>
                    </span>
                  </div>
                  {[
                    { label: "Cyber Score", value: risk.cyber_score },
                    { label: "News Score", value: risk.news_score },
                    { label: "Stability Baseline", value: risk.stability_baseline },
                    { label: "Attacks (24h)", value: risk.attack_count_24h, raw: true },
                  ].map(({ label, value, raw }) => (
                    <div key={label} className="flex flex-col rounded bg-white/5 px-3 py-2">
                      <span className="text-xs text-gray-500 mb-1">{label}</span>
                      <span className={`text-lg font-mono font-bold ${raw ? "text-gray-200" : riskColor(value)}`}>
                        {raw ? value : `${value.toFixed(0)}`}
                      </span>
                      {!raw && (
                        <div className="mt-1 h-1 rounded-full bg-white/10 overflow-hidden">
                          <div
                            className="h-full rounded-full"
                            style={{
                              width: `${value}%`,
                              background: value >= 75 ? "#f87171" : value >= 50 ? "#fb923c" : value >= 25 ? "#fbbf24" : "#4ade80",
                            }}
                          />
                        </div>
                      )}
                    </div>
                  ))}
                </div>

                {/* 24-hour multi-series sparkline */}
                <div className="mt-3 rounded bg-white/5 px-4 py-3">
                  <p className="text-xs text-gray-500 mb-2">24-hour risk trend</p>
                  {trendLoading ? (
                    <div className="h-12 flex items-center justify-center">
                      <span className="text-xs text-gray-600 animate-pulse">Loading…</span>
                    </div>
                  ) : trend.length >= 2 ? (
                    <MultiSeriesSparkline points={trend} />
                  ) : (
                    <div className="h-12 flex items-center justify-center">
                      <span className="text-xs text-gray-600">No trend data yet</span>
                    </div>
                  )}
                </div>
              </section>
            ) : (
              <p className="text-xs text-gray-500">No risk data available for {countryName}.</p>
            )}

            {/* Active attacks */}
            <section>
              <h3 className="text-xs uppercase tracking-widest text-gray-500 mb-3">
                Active Attacks (last 5 min) — {activeAttacks.length}
              </h3>
              {activeAttacks.length === 0 ? (
                <p className="text-xs text-gray-600">No active attacks detected.</p>
              ) : (
                <div className="space-y-1.5">
                  {activeAttacks.map((a) => (
                    <div
                      key={a.id}
                      className="flex items-center gap-3 text-xs px-3 py-2 rounded bg-white/5"
                    >
                      <span
                        className="w-2 h-2 rounded-full shrink-0"
                        style={{ background: ATTACK_COLORS[a.attack_type] ?? "#fff" }}
                      />
                      <span className="text-gray-400">{a.attack_type}</span>
                      <span className="text-gray-600 ml-auto">
                        {a.source_country} → {a.dest_country}
                      </span>
                      <span className="text-gray-500">Sev {a.severity}</span>
                    </div>
                  ))}
                </div>
              )}
            </section>

            {/* Financial assets */}
            {relatedAssets.length > 0 && (
              <section>
                <h3 className="text-xs uppercase tracking-widest text-gray-500 mb-3">Related Markets</h3>
                <div className="grid grid-cols-2 gap-2">
                  {relatedAssets.map((t) => (
                    <div key={t.symbol} className="flex items-center justify-between rounded bg-white/5 px-3 py-2">
                      <div>
                        <p className="text-xs font-bold text-gray-200">{t.symbol}</p>
                        <p className="text-xs text-gray-500">{t.name}</p>
                      </div>
                      <div className="text-right">
                        <p className="text-sm font-mono text-gray-200">
                          {t.price < 10 ? t.price.toFixed(4) : t.price.toFixed(2)}
                        </p>
                        <p className={`text-xs font-mono ${t.change_pct >= 0 ? "text-green-400" : "text-red-400"}`}>
                          {formatPct(t.change_pct)}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {/* News */}
            <section>
              <h3 className="text-xs uppercase tracking-widest text-gray-500 mb-3">
                Recent News — {countryNews.length} items
              </h3>
              {countryNews.length === 0 ? (
                <p className="text-xs text-gray-600">No recent news matching {countryName}.</p>
              ) : (
                <div className="space-y-2">
                  {countryNews.map((n) => (
                    <a
                      key={n.id}
                      href={n.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="block rounded bg-white/5 hover:bg-white/10 px-3 py-2 transition-colors"
                    >
                      <p className="text-xs text-gray-200 leading-snug line-clamp-2">{n.title}</p>
                      <p className="text-xs text-gray-600 mt-1">{n.source}</p>
                    </a>
                  ))}
                </div>
              )}
            </section>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}

const ATTACK_COLORS: Record<string, string> = {
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

/** Inline SVG multi-series sparkline (risk + cyber + news). No external deps. */
function MultiSeriesSparkline({ points }: { points: TrendPoint[] }) {
  const W = 340;
  const H = 52;
  const PAD = 4;

  const allValues = points.flatMap((p) => [p.risk_score, p.cyber_score, p.news_score]);
  const minV = Math.min(...allValues);
  const maxV = Math.max(...allValues);
  const range = maxV - minV || 1;

  const toX = (i: number) => PAD + (i / (points.length - 1)) * (W - PAD * 2);
  const toY = (v: number) => H - PAD - ((v - minV) / range) * (H - PAD * 2);

  const series = [
    { key: "risk_score" as keyof TrendPoint, color: "#f87171", label: "Risk" },
    { key: "cyber_score" as keyof TrendPoint, color: "#60a5fa", label: "Cyber" },
    { key: "news_score" as keyof TrendPoint, color: "#fbbf24", label: "News" },
  ];

  const lastRisk = points[points.length - 1].risk_score;
  const firstRisk = points[0].risk_score;
  const delta = lastRisk - firstRisk;

  return (
    <div>
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} aria-label="24h multi-series risk sparkline">
        {series.map(({ key, color }) => {
          const pathD = points
            .map((p, i) => `${i === 0 ? "M" : "L"}${toX(i).toFixed(1)},${toY(p[key] as number).toFixed(1)}`)
            .join(" ");
          return (
            <path
              key={key}
              d={pathD}
              fill="none"
              stroke={color}
              strokeWidth={1.5}
              strokeLinejoin="round"
              strokeOpacity={key === "risk_score" ? 1 : 0.55}
            />
          );
        })}
        {/* Last-value dot for composite risk */}
        <circle
          cx={toX(points.length - 1)}
          cy={toY(lastRisk)}
          r={2.5}
          fill="#f87171"
        />
      </svg>
      <div className="flex items-center justify-between mt-1 text-xs font-mono">
        <div className="flex gap-2">
          {series.map(({ label, color }) => (
            <span key={label} style={{ color }} className="flex items-center gap-1">
              <span className="inline-block w-2 h-0.5 rounded" style={{ background: color }} />
              {label}
            </span>
          ))}
        </div>
        <span
          className="text-xs font-mono"
          style={{ color: delta >= 0 ? "#f87171" : "#4ade80" }}
        >
          {delta >= 0 ? "+" : ""}{delta.toFixed(1)} pts
        </span>
      </div>
    </div>
  );
}
