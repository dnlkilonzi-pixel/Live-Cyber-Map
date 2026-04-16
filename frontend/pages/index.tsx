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
import { loadSettings, usePersistSettings } from "../hooks/useSettings";
import { useIsMobile } from "../hooks/useIsMobile";

import Dashboard from "../components/Dashboard";
import AttackFeed from "../components/AttackFeed";
import ReplayControls from "../components/ReplayControls";

const Globe = dynamic(() => import("../components/Globe"), { ssr: false });
const FlatMap = dynamic(() => import("../components/FlatMap"), { ssr: false });
const IntelligenceBriefPanel = dynamic(() => import("../components/IntelligenceBrief"), { ssr: false });
const FinancialTicker = dynamic(() => import("../components/FinancialTicker"), { ssr: false });
const LayerPanel = dynamic(() => import("../components/LayerPanel"), { ssr: false });
const CountryRiskPanel = dynamic(() => import("../components/CountryRiskPanel"), { ssr: false });
const CountryDrilldown = dynamic(() => import("../components/CountryDrilldown"), { ssr: false });
const OllamaSettings = dynamic(() => import("../components/OllamaSettings"), { ssr: false });
const NotificationTray = dynamic(() => import("../components/NotificationTray"), { ssr: false });
const AlertRuleManager = dynamic(() => import("../components/AlertRuleManager"), { ssr: false });

import { ThemeId, THEMES, DEFAULT_THEME, applyTheme } from "../lib/themes";
import { NewsCategory } from "../types/intelligence";

type RightPanel = "intel" | "financial" | "risk" | null;
type LeftPanel = "dashboard" | "layers" | null;

export default function Home() {
  const { attacks, stats, isConnected, isAnomaly, anomalyScore, sendMessage, notifications, clearNotifications, markAllRead, replaySyncPosition, reconnectedAt } =
    useWebSocket();

  const isMobile = useIsMobile();
  // Load persisted settings once on mount (safe during SSR via typeof window check)
  const saved = loadSettings();
  const persist = usePersistSettings();

  const [intelCategory, setIntelCategory] = useState<NewsCategory>("world");
  const intelligence = useIntelligence({ category: intelCategory, autoPoll: true });
  const financial = useFinancial();
  const layers = useLayers();

  const [mapView, setMapView] = useState<"globe" | "flat">(
    // Default to flat map on mobile (3D globe is GPU-heavy)
    typeof window !== "undefined" && window.innerWidth < 768 ? "flat" : saved.mapView
  );
  const [theme, setTheme] = useState<ThemeId>(saved.theme);
  const [leftPanel, setLeftPanel] = useState<LeftPanel>(saved.leftPanel);
  const [rightPanel, setRightPanel] = useState<RightPanel>(saved.rightPanel);
  const [showFinancial, setShowFinancial] = useState(saved.showFinancial);
  const [showReplay, setShowReplay] = useState(false);

  const [isReplaying, setIsReplaying] = useState(false);
  const [replayProgress, setReplayProgress] = useState(0);
  const [replayTotal, setReplayTotal] = useState(0);
  const [replaySpeed, setReplaySpeed] = useState(1);

  // Country drill-down modal state
  const [drilldownCountry, setDrilldownCountry] = useState<string | null>(null);
  const [showAlerts, setShowAlerts] = useState(false);
  const [showOllamaSettings, setShowOllamaSettings] = useState(false);
  const [bboxCaptureCallback, setBboxCaptureCallback] = useState<((lat: number, lng: number) => void) | null>(null);

  // Unread notification count — cleared when alert panel is opened
  const unreadNotifCount = notifications.filter((n) => !n.read).length;

  // New attacks since feed was last viewed
  const [lastSeenAttackCount, setLastSeenAttackCount] = useState(0);
  const newAttackCount = Math.max(0, attacks.length - lastSeenAttackCount);
  const handleViewFeed = () => setLastSeenAttackCount(attacks.length);

  // WS reconnect toast
  const [showReconnectToast, setShowReconnectToast] = useState(false);
  useEffect(() => {
    if (!reconnectedAt) return;
    setShowReconnectToast(true);
    const t = setTimeout(() => setShowReconnectToast(false), 4000);
    return () => clearTimeout(t);
  }, [reconnectedAt]);

  useEffect(() => { applyTheme(theme); persist.saveTheme(theme); }, [theme]); // eslint-disable-line react-hooks/exhaustive-deps -- persist is a stable object from usePersistSettings (useCallback references)

  // ── Restore state from URL hash (share links) ─────────────────────────
  useEffect(() => {
    if (typeof window === "undefined") return;
    const hash = window.location.hash.replace(/^#/, "");
    if (!hash) return;
    try {
      const params = new URLSearchParams(hash);
      const v = params.get("view");
      const t = params.get("theme");
      const l = params.get("left");
      const r = params.get("right");
      if (v === "globe" || v === "flat") setMapView(v);
      if (t === "cyber" || t === "tech" || t === "finance") setTheme(t);
      if (l) setLeftPanel((l as LeftPanel) || null);
      if (r) setRightPanel((r as RightPanel) || null);
    } catch {
      // Invalid hash — ignore
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Export: capture the map canvas as PNG ──────────────────────────────
  const handleExportPng = () => {
    // Grab the first canvas in the document (Globe or Leaflet map)
    const canvas = document.querySelector("canvas");
    if (!canvas) {
      alert("No map canvas found. Switch to Globe view for PNG export.");
      return;
    }
    try {
      const dataUrl = canvas.toDataURL("image/png");
      const a = document.createElement("a");
      a.href = dataUrl;
      a.download = `intel-map-${new Date().toISOString().slice(0, 19).replace(/:/g, "-")}.png`;
      a.click();
    } catch {
      alert("Could not capture map — cross-origin tiles may block this in 2D mode.");
    }
  };

  // ── Share: encode current view state into URL hash ─────────────────────
  const handleCopyShareLink = () => {
    const hash = new URLSearchParams({
      view: mapView,
      theme,
      left: leftPanel ?? "",
      right: rightPanel ?? "",
    }).toString();
    const url = `${window.location.origin}${window.location.pathname}#${hash}`;
    navigator.clipboard.writeText(url).then(() => {
      alert("Share link copied to clipboard!");
    }).catch(() => {
      prompt("Copy this link:", url);
    });
  };

  function handlePlay() {
    sendMessage("start_replay", { speed: replaySpeed });
    setIsReplaying(true);
    setReplayProgress(0);
  }
  function handleStop() {
    sendMessage("stop_replay");
    setIsReplaying(false);
    setReplayProgress(0);
    setReplayTotal(0);
  }
  function handleSpeedChange(speed: number) {
    setReplaySpeed(speed);
    if (isReplaying) sendMessage("set_replay_speed", { speed });
  }
  async function handleSeek(position: number) {
    setReplayProgress(position);
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
      await fetch(`${apiUrl}/api/replay/seek?position=${position}`, { method: "POST" });
    } catch {
      // Silently ignore — the local progress indicator still updates
    }
  }

  // Sync replay position broadcast from other clients via WebSocket
  useEffect(() => {
    if (replaySyncPosition !== null) {
      setReplayProgress(replaySyncPosition);
    }
  }, [replaySyncPosition]);

  const toggleLeft = (panel: LeftPanel) => {
    setLeftPanel((p) => {
      const next = p === panel ? null : panel;
      persist.saveLeftPanel(next);
      return next;
    });
  };
  const toggleRight = (panel: RightPanel) => {
    setRightPanel((p) => {
      const next = p === panel ? null : panel;
      persist.saveRightPanel(next);
      return next;
    });
  };

  const currentTheme = THEMES[theme];

  return (
    <>
      <Head>
        <title>Global Intelligence Dashboard</title>
        <meta name="description" content="Real-time global intelligence — cyber, news, finance, geopolitics" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <link rel="icon" href="/favicon.ico" />
      </Head>

      <div className="relative w-screen h-screen overflow-hidden" style={{ background: currentTheme.globe.backgroundColor }}>

        {/* ── Map background ─────────────────────────────── */}
        <div className="absolute inset-0 z-0">
          {mapView === "globe" ? (
            <Globe attacks={attacks} theme={currentTheme} onCountryClick={setDrilldownCountry} />
          ) : (
            <FlatMap
              attacks={attacks}
              enabledLayers={layers.enabledLayers}
              layerDefinitions={layers.availableLayers}
              layerData={layers.layerData}
              riskScores={intelligence.riskScores}
              onCountryClick={setDrilldownCountry}
              onMapClick={bboxCaptureCallback ? (lat, lng) => {
                bboxCaptureCallback(lat, lng);
                setBboxCaptureCallback(null);
              } : undefined}
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
                <button key={v} onClick={() => { setMapView(v); persist.saveMapView(v); }}
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

            {/* Desktop-only panel + action buttons */}
            {!isMobile && (<>
            {[
              { key: "intel" as RightPanel, icon: "📰", label: "INTEL" },
              { key: "risk" as RightPanel, icon: "🌡️", label: "RISK" },
            ].map(({ key, icon, label }) => (
              <button key={label} onClick={() => toggleRight(key)}
                className={`px-2 py-1 text-xs border rounded transition-colors ${rightPanel === key ? "border-[var(--color-accent)] text-[var(--color-accent)]" : "border-white/20 text-gray-400 hover:text-white"}`}>
                {icon} {label}
              </button>
            ))}

            <button onClick={() => { setShowFinancial((v) => { persist.saveShowFinancial(!v); return !v; }); }}
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

            <button onClick={() => { setShowAlerts(true); markAllRead(); }}
              className="relative px-2 py-1 text-xs border border-white/20 text-gray-400 hover:text-white rounded transition-colors"
              title="Manage alert rules">
              🚨 ALERTS
              {unreadNotifCount > 0 && (
                <span className="absolute -top-1.5 -right-1.5 flex items-center justify-center w-4 h-4 rounded-full bg-red-600 text-white text-[9px] font-bold leading-none">
                  {unreadNotifCount > 9 ? "9+" : unreadNotifCount}
                </span>
              )}
            </button>

            <button
              onClick={() => setShowOllamaSettings(true)}
              className={`px-2 py-1 text-xs border rounded transition-colors ${
                intelligence.ollamaStatus?.available
                  ? "border-green-800 text-green-500 hover:text-green-300"
                  : "border-white/20 text-gray-400 hover:text-white"
              }`}
              title="Ollama model settings"
            >
              🤖 AI
            </button>

            {/* Export / Share */}
            <button
              onClick={handleExportPng}
              className="px-2 py-1 text-xs border border-white/20 text-gray-400 hover:text-white rounded transition-colors"
              title="Download map as PNG"
            >
              💾 PNG
            </button>
            <button
              onClick={handleCopyShareLink}
              className="px-2 py-1 text-xs border border-white/20 text-gray-400 hover:text-white rounded transition-colors"
              title="Copy share link"
            >
              🔗 SHARE
            </button>

            {/* Notification tray */}
            <NotificationTray notifications={notifications} onClear={clearNotifications} />
            </>)}
          </div>
        </div>

        {/* ── Left panel ─────────────────────────────────── */}
        <AnimatePresence>
          {leftPanel && (
            <motion.div key={`left-${leftPanel}`}
              initial={isMobile ? { y: "100%", opacity: 0 } : { x: -320, opacity: 0 }}
              animate={isMobile ? { y: 0, opacity: 1 } : { x: 0, opacity: 1 }}
              exit={isMobile ? { y: "100%", opacity: 0 } : { x: -320, opacity: 0 }}
              transition={{ type: "spring", damping: 25, stiffness: 200 }}
              className="absolute z-20 side-panel overflow-hidden"
              style={isMobile
                ? { left: 0, right: 0, bottom: 0, height: "60vh", borderTopLeftRadius: 12, borderTopRightRadius: 12 }
                : { top: 10, left: 0, bottom: 0, width: 320 }
              }>
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
        {!leftPanel && !isMobile && (
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
              initial={isMobile ? { y: "100%", opacity: 0 } : { x: 320, opacity: 0 }}
              animate={isMobile ? { y: 0, opacity: 1 } : { x: 0, opacity: 1 }}
              exit={isMobile ? { y: "100%", opacity: 0 } : { x: 320, opacity: 0 }}
              transition={{ type: "spring", damping: 25, stiffness: 200 }}
              className="absolute z-20 side-panel-right overflow-hidden"
              style={isMobile
                ? { left: 0, right: 0, bottom: 0, height: "65vh", borderTopLeftRadius: 12, borderTopRightRadius: 12 }
                : { top: 10, right: 0, bottom: 0, width: 320 }
              }>
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

        {/* Attack feed (right, when right panel closed, desktop only) */}
        {!rightPanel && !isMobile && (
          <div className="absolute top-10 right-0 bottom-16 z-10 overflow-hidden" onClick={handleViewFeed}>
            {newAttackCount > 0 && (
              <div className="absolute top-0 left-0 right-0 z-10 flex justify-center py-1 pointer-events-none">
                <span className="px-3 py-0.5 rounded-full bg-red-700/80 text-white text-xs font-bold border border-red-500/50 backdrop-blur-sm">
                  +{newAttackCount} new {newAttackCount === 1 ? "attack" : "attacks"}
                </span>
              </div>
            )}
            <AttackFeed attacks={attacks} />
          </div>
        )}

        {/* ── Mobile bottom navigation bar ───────────────────── */}
        {isMobile && (
          <div className="absolute bottom-0 left-0 right-0 z-30 flex items-center justify-around px-2 py-2 bg-black/80 border-t border-white/10 backdrop-blur-md">
            <button onClick={() => toggleLeft("dashboard")}
              className={`flex flex-col items-center gap-0.5 text-xs ${leftPanel === "dashboard" ? "text-[var(--color-accent)]" : "text-gray-400"}`}>
              <span>📊</span>
              <span className="text-[10px]">Stats</span>
            </button>
            <button onClick={() => toggleLeft("layers")}
              className={`flex flex-col items-center gap-0.5 text-xs ${leftPanel === "layers" ? "text-[var(--color-accent)]" : "text-gray-400"}`}>
              <span>🗂️</span>
              <span className="text-[10px]">Layers</span>
            </button>
            <button onClick={() => toggleRight("intel")}
              className={`flex flex-col items-center gap-0.5 text-xs ${rightPanel === "intel" ? "text-[var(--color-accent)]" : "text-gray-400"}`}>
              <span>📰</span>
              <span className="text-[10px]">Intel</span>
            </button>
            <button onClick={() => toggleRight("risk")}
              className={`flex flex-col items-center gap-0.5 text-xs ${rightPanel === "risk" ? "text-[var(--color-accent)]" : "text-gray-400"}`}>
              <span>🌡️</span>
              <span className="text-[10px]">Risk</span>
            </button>
            <button onClick={() => { setShowAlerts(true); markAllRead(); }}
              className="relative flex flex-col items-center gap-0.5 text-xs text-gray-400">
              <span>🚨</span>
              <span className="text-[10px]">Alerts</span>
              {unreadNotifCount > 0 && (
                <span className="absolute -top-1 -right-1 flex items-center justify-center w-4 h-4 rounded-full bg-red-600 text-white text-[9px] font-bold leading-none">
                  {unreadNotifCount > 9 ? "9+" : unreadNotifCount}
                </span>
              )}
            </button>
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
                  onPlay={handlePlay} onStop={handleStop} onSpeedChange={handleSpeedChange} onSeek={handleSeek}
                />
              </div>
            )}
          </AnimatePresence>
        </div>

        {/* ── Country drill-down modal ─────────────────────── */}
        {drilldownCountry && (
          <CountryDrilldown
            iso2={drilldownCountry}
            onClose={() => setDrilldownCountry(null)}
            riskScores={intelligence.riskScores}
            news={intelligence.news}
            attacks={attacks}
            financialSummary={financial.market}
          />
        )}

        {/* ── Alert rule manager modal ─────────────────────── */}
        {showAlerts && (
          <AlertRuleManager
            onClose={() => setShowAlerts(false)}
            onBboxCapture={(cb) => setBboxCaptureCallback(() => cb)}
          />
        )}

        {/* ── Ollama model management drawer ───────────────── */}
        {showOllamaSettings && (
          <OllamaSettings
            onClose={() => setShowOllamaSettings(false)}
            initialStatus={intelligence.ollamaStatus}
          />
        )}

        {/* ── WebSocket reconnect toast ─────────────────────── */}
        <AnimatePresence>
          {showReconnectToast && (
            <motion.div
              key="reconnect-toast"
              initial={{ opacity: 0, y: 40 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 40 }}
              transition={{ duration: 0.3 }}
              className="absolute bottom-16 left-1/2 -translate-x-1/2 z-50 flex items-center gap-2 px-4 py-2 rounded-lg border border-green-600/60 bg-black/80 backdrop-blur-sm shadow-lg pointer-events-none"
            >
              <span className="w-2 h-2 rounded-full bg-green-400" style={{ boxShadow: "0 0 6px #4ade80" }} />
              <span className="text-xs text-green-300 font-mono tracking-wide">Reconnected to live feed</span>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </>
  );
}
