/**
 * Global Intelligence Dashboard – main page.
 *
 * Layout:
 *   - Left panel  : Attack dashboard + Layer manager  (toggleable)
 *   - Center      : 3D Globe or 2D Flat Map           (switchable)
 *   - Right panel : Intelligence briefs / Risk / Fin  (toggleable)
 *   - Bottom bar  : Financial ticker                  (toggleable)
 *   - Top bar     : Controls, theme switcher, status
 */

import dynamic from "next/dynamic";
import Head from "next/head";
import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";

import { useWebSocket } from "../hooks/useWebSocket";
import { useIntelligence } from "../hooks/useIntelligence";
import { useFinancial } from "../hooks/useFinancial";
import { useLayers } from "../hooks/useLayers";

import Dashboard from "../components/Dashboard";
import AttackFeed from "../components/AttackFeed";
import ReplayControls from "../components/ReplayControls";

const Globe = dynamic(() => import("../components/Globe"), { ssr: false });
const FlatMap = dynamic(() => import("../components/FlatMap"), { ssr: false });
const IntelligenceBriefPanel = dynamic(() => import("../components/IntelligenceBrief"), { ssr: false });
const FinancialTicker = dynamic(() => import("../components/FinancialTicker"), { ssr: false });
const LayerPanel = dynamic(() => import("../components/LayerPanel"), { ssr: false });
const CountryRiskPanel = dynamic(() => import("../components/CountryRiskPanel"), { ssr: false });

import { ThemeId, THEMES, DEFAULT_THEME, applyTheme } from "../lib/themes";
import { NewsCategory } from "../types/intelligence";

type RightPanel = "intel" | "financial" | "risk" | null;
type LeftPanel = "dashboard" | "layers" | null;

export default function Home() {
  const { attacks, stats, isConnected, isAnomaly, anomalyScore, sendMessage } =
    useWebSocket();

  const [intelCategory, setIntelCategory] = useState<NewsCategory>("world");
  const intelligence = useIntelligence({ category: intelCategory, autoPoll: true });
  const financial = useFinancial();
  const layers = useLayers();

  const [mapView, setMapView] = useState<"globe" | "flat">("globe");
  const [theme, setTheme] = useState<ThemeId>(DEFAULT_THEME);
  const [leftPanel, setLeftPanel] = useState<LeftPanel>("dashboard");
  const [rightPanel, setRightPanel] = useState<RightPanel>(null);
  const [showFinancial, setShowFinancial] = useState(false);
  const [showReplay, setShowReplay] = useState(false);

  const [isReplaying, setIsReplaying] = useState(false);
  const [replayProgress, setReplayProgress] = useState(0);
  const [replayTotal, setReplayTotal] = useState(0);
  const [replaySpeed, setReplaySpeed] = useState(1);

  useEffect(() => { applyTheme(theme); }, [theme]);

  function handlePlay() {
    sendMessage("start_replay", { speed: replaySpeed });
    setIsReplaying(true); setReplayProgress(0);
  }
  function handleStop() {
    sendMessage("stop_replay");
    setIsReplaying(false); setReplayProgress(0); setReplayTotal(0);
  }
  function handleSpeedChange(speed: number) {
    setReplaySpeed(speed);
    if (isReplaying) sendMessage("set_replay_speed", { speed });
  }

  const toggleLeft = (panel: LeftPanel) => setLeftPanel((p) => (p === panel ? null : panel));
  const toggleRight = (panel: RightPanel) => setRightPanel((p) => (p === panel ? null : panel));

  const currentTheme = THEMES[theme];

  return (
    <>
      <Head>
        <title>Global Intelligence Dashboard</title>
        <meta name="description" content="Real-time global intelligence — cyber, news, finance, geopolitics" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <link rel="icon" href="/favicon.ico" />
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css" crossOrigin="anonymous" />
      </Head>

      <div className="relative w-screen h-screen overflow-hidden" style={{ background: currentTheme.globe.backgroundColor }}>

        {/* ── Map background ─────────────────────────────── */}
        <div className="absolute inset-0 z-0">
          {mapView === "globe" ? (
            <Globe attacks={attacks} theme={currentTheme} />
          ) : (
            <FlatMap
              attacks={attacks}
              enabledLayers={layers.enabledLayers}
              layerDefinitions={layers.availableLayers}
              layerData={layers.layerData}
              riskScores={intelligence.riskScores}
            />
          )}
        </div>

        {/* ── Top bar ────────────────────────────────────── */}
        <div className="absolute top-0 left-0 right-0 z-30 flex items-center justify-between px-3 py-2 bg-gradient-to-b from-black/80 to-transparent pointer-events-none">
          <div className="flex items-center gap-3 pointer-events-auto">
            <span className="blink-dot" />
            <span className="font-bold tracking-widest text-sm uppercase" style={{ color: "var(--color-accent)", textShadow: "0 0 10px var(--color-accent)" }}>
              GLOBAL INTEL
            </span>
            <div className={`flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-mono border ${isConnected ? "border-green-900/50 text-green-400" : "border-red-900/50 text-red-400"}`}>
              <span className={`w-1.5 h-1.5 rounded-full ${isConnected ? "bg-green-400" : "bg-red-400"}`} style={isConnected ? { boxShadow: "0 0 5px #4ade80" } : {}} />
              {isConnected ? "LIVE" : "OFFLINE"}
            </div>
          </div>

          <div className="pointer-events-auto">
            <AnimatePresence>
              {isAnomaly && (
                <motion.div key="anomaly" initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}
                  className="flex items-center gap-2 bg-red-900/70 border border-red-500 rounded px-3 py-1 animate-pulse">
                  <span className="text-red-400 text-xs font-bold uppercase tracking-widest">⚠ Anomaly</span>
                  <span className="text-red-300 text-xs font-mono">{anomalyScore.toFixed(3)}</span>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          <div className="flex items-center gap-1.5 pointer-events-auto">
            {/* Map view toggle */}
            <div className="flex border border-white/20 rounded overflow-hidden">
              {(["globe", "flat"] as const).map((v) => (
                <button key={v} onClick={() => setMapView(v)}
                  className={`px-2 py-1 text-xs transition-colors ${mapView === v ? "bg-white/20 text-white" : "text-gray-500 hover:text-gray-300"}`}>
                  {v === "globe" ? "🌐 3D" : "🗺️ 2D"}
                </button>
              ))}
            </div>

            {/* Theme switcher */}
            <div className="flex border border-white/20 rounded overflow-hidden">
              {(["cyber", "tech", "finance"] as ThemeId[]).map((t) => (
                <button key={t} onClick={() => setTheme(t)} title={THEMES[t].name}
                  className={`px-2 py-1 text-xs transition-colors ${theme === t ? "bg-white/20 text-white" : "text-gray-500 hover:text-gray-300"}`}>
                  {THEMES[t].icon}
                </button>
              ))}
            </div>

            {/* Panel buttons */}
            {[
              { key: "intel" as RightPanel, icon: "📰", label: "INTEL" },
              { key: "risk" as RightPanel, icon: "🌡️", label: "RISK" },
            ].map(({ key, icon, label }) => (
              <button key={label} onClick={() => toggleRight(key)}
                className={`px-2 py-1 text-xs border rounded transition-colors ${rightPanel === key ? "border-[var(--color-accent)] text-[var(--color-accent)]" : "border-white/20 text-gray-400 hover:text-white"}`}>
                {icon} {label}
              </button>
            ))}

            <button onClick={() => setShowFinancial((v) => !v)}
              className={`px-2 py-1 text-xs border rounded transition-colors ${showFinancial ? "border-[var(--color-accent)] text-[var(--color-accent)]" : "border-white/20 text-gray-400 hover:text-white"}`}>
              📈 MARKETS
            </button>

            <button onClick={() => toggleLeft("layers")}
              className={`px-2 py-1 text-xs border rounded transition-colors ${leftPanel === "layers" ? "border-[var(--color-accent)] text-[var(--color-accent)]" : "border-white/20 text-gray-400 hover:text-white"}`}>
              🗂️ LAYERS
            </button>

            <button onClick={() => setShowReplay((v) => !v)}
              className="px-2 py-1 text-xs border border-white/20 text-gray-400 hover:text-white rounded transition-colors">
              ⏮ REPLAY
            </button>
          </div>
        </div>

        {/* ── Left panel ─────────────────────────────────── */}
        <AnimatePresence>
          {leftPanel && (
            <motion.div key={`left-${leftPanel}`}
              initial={{ x: -320, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: -320, opacity: 0 }}
              transition={{ type: "spring", damping: 25, stiffness: 200 }}
              className="absolute top-10 left-0 bottom-0 z-20 side-panel overflow-hidden" style={{ width: 320 }}>
              {leftPanel === "dashboard" ? (
                <div className="relative h-full">
                  <button onClick={() => setLeftPanel(null)} className="absolute top-2 right-2 z-10 text-gray-500 hover:text-white text-lg p-1">×</button>
                  <Dashboard stats={stats} isConnected={isConnected} isAnomaly={isAnomaly} anomalyScore={anomalyScore} />
                </div>
              ) : (
                <LayerPanel layers={layers.availableLayers} enabled={layers.enabledLayers} onToggle={layers.toggleLayer} onClose={() => setLeftPanel(null)} />
              )}
            </motion.div>
          )}
        </AnimatePresence>

        {/* Dashboard quick-open tab */}
        {!leftPanel && (
          <div className="absolute top-14 left-0 z-20 flex flex-col gap-1 p-1">
            <button onClick={() => toggleLeft("dashboard")} title="Dashboard"
              className="px-2 py-2 rounded-r border border-white/10 text-gray-500 hover:text-white hover:bg-white/10 transition-colors text-xs">📊</button>
            <button onClick={() => toggleLeft("layers")} title="Layers"
              className="px-2 py-2 rounded-r border border-white/10 text-gray-500 hover:text-white hover:bg-white/10 transition-colors text-xs">🗂️</button>
          </div>
        )}

        {/* ── Right panel ────────────────────────────────── */}
        <AnimatePresence>
          {rightPanel && (
            <motion.div key={`right-${rightPanel}`}
              initial={{ x: 320, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: 320, opacity: 0 }}
              transition={{ type: "spring", damping: 25, stiffness: 200 }}
              className="absolute top-10 right-0 bottom-0 z-20 side-panel-right overflow-hidden" style={{ width: 320 }}>
              {rightPanel === "intel" && (
                <IntelligenceBriefPanel
                  news={intelligence.news} brief={intelligence.brief} ollamaStatus={intelligence.ollamaStatus}
                  isLoadingNews={intelligence.isLoadingNews} isLoadingBrief={intelligence.isLoadingBrief}
                  onCategoryChange={(cat) => setIntelCategory(cat)}
                  onRefreshBrief={(cat) => intelligence.fetchBrief(cat)}
                  onClose={() => setRightPanel(null)}
                />
              )}
              {rightPanel === "risk" && (
                <CountryRiskPanel riskScores={intelligence.riskScores} isLoading={intelligence.isLoadingRisk} onClose={() => setRightPanel(null)} />
              )}
              {rightPanel === "financial" && (
                <FinancialTicker market={financial.market} isLoading={financial.isLoading} onClose={() => setRightPanel(null)} />
              )}
            </motion.div>
          )}
        </AnimatePresence>

        {/* Attack feed (right, when right panel closed) */}
        {!rightPanel && (
          <div className="absolute top-10 right-0 bottom-16 z-10 overflow-hidden">
            <AttackFeed attacks={attacks} />
          </div>
        )}

        {/* ── Financial ticker (bottom) ───────────────────── */}
        <AnimatePresence>
          {showFinancial && (
            <motion.div key="financial-ticker"
              initial={{ y: 320, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 320, opacity: 0 }}
              transition={{ type: "spring", damping: 25, stiffness: 200 }}
              className="absolute bottom-0 left-0 right-0 z-25 side-panel-right border-t border-white/10" style={{ height: 320 }}>
              <FinancialTicker market={financial.market} isLoading={financial.isLoading} onClose={() => setShowFinancial(false)} />
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── Replay controls ─────────────────────────────── */}
        <div className="absolute left-0 right-0 z-30 flex justify-center pointer-events-none" style={{ bottom: showFinancial ? 328 : 8 }}>
          <AnimatePresence>
            {showReplay && (
              <div className="pointer-events-auto">
                <ReplayControls
                  isReplaying={isReplaying} replayProgress={replayProgress} replayTotal={replayTotal} replaySpeed={replaySpeed}
                  onPlay={handlePlay} onStop={handleStop} onSpeedChange={handleSpeedChange}
                />
              </div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </>
  );
}
