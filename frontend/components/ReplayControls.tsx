import { motion } from "framer-motion";
import { useCallback, useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface ReplayControlsProps {
  isReplaying: boolean;
  replayProgress: number;
  replayTotal: number;
  replaySpeed: number;
  onPlay: () => void;
  onStop: () => void;
  onSpeedChange: (speed: number) => void;
  onSeek?: (position: number) => void;
}

interface IntelEvent {
  type: "risk" | "financial";
  ts: number;
  [key: string]: unknown;
}

const SPEED_OPTIONS = [0.5, 1, 2, 5];

export default function ReplayControls({
  isReplaying,
  replayProgress,
  replayTotal,
  replaySpeed,
  onPlay,
  onStop,
  onSpeedChange,
  onSeek,
}: ReplayControlsProps) {
  const progressPct =
    replayTotal > 0 ? Math.round((replayProgress / replayTotal) * 100) : 0;

  // Intelligence event timeline state
  const [intelEvents, setIntelEvents] = useState<IntelEvent[]>([]);
  const [intelIndex, setIntelIndex] = useState(0);
  const [intelLoading, setIntelLoading] = useState(false);
  const [hoursBack, setHoursBack] = useState(24);

  const loadIntelTimeline = useCallback(async () => {
    setIntelLoading(true);
    try {
      const from = (Date.now() / 1000 - hoursBack * 3600).toFixed(0);
      const resp = await fetch(
        `${API_URL}/api/replay/intelligence?from=${from}&limit=500`
      );
      if (resp.ok) {
        const json = await resp.json();
        setIntelEvents(json.events ?? []);
        setIntelIndex(0);
      }
    } catch {
      // Silently ignore
    } finally {
      setIntelLoading(false);
    }
  }, [hoursBack]);

  // Load on mount and when hoursBack changes
  useEffect(() => {
    loadIntelTimeline();
  }, [loadIntelTimeline]);

  // Advance intel index while replaying (at ~1 event per second scaled by speed)
  useEffect(() => {
    if (!isReplaying || intelEvents.length === 0) return;
    const interval = setInterval(() => {
      setIntelIndex((prev) => Math.min(prev + 1, intelEvents.length - 1));
    }, 1000 / replaySpeed);
    return () => clearInterval(interval);
  }, [isReplaying, intelEvents.length, replaySpeed]);

  const currentEvent = intelEvents[intelIndex] ?? null;
  const riskCount = intelEvents.filter((e) => e.type === "risk").length;
  const finCount = intelEvents.filter((e) => e.type === "financial").length;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 20 }}
      transition={{ duration: 0.3 }}
      className="glass-panel rounded-xl px-5 py-3 flex flex-col gap-2 min-w-[480px]"
    >
      {/* Top row: controls */}
      <div className="flex items-center gap-5">
        {/* Play / Stop button */}
        <button
          onClick={isReplaying ? onStop : onPlay}
          className="flex items-center justify-center w-9 h-9 rounded-full border border-green-500/60 bg-green-900/30 hover:bg-green-700/40 transition-colors shrink-0"
          aria-label={isReplaying ? "Stop replay" : "Start replay"}
        >
          {isReplaying ? (
            <svg className="w-4 h-4 text-green-400" fill="currentColor" viewBox="0 0 20 20">
              <rect x="4" y="4" width="4" height="12" rx="1" />
              <rect x="12" y="4" width="4" height="12" rx="1" />
            </svg>
          ) : (
            <svg className="w-4 h-4 text-green-400 ml-0.5" fill="currentColor" viewBox="0 0 20 20">
              <path d="M6 4l12 6-12 6V4z" />
            </svg>
          )}
        </button>

        {/* Progress scrubber */}
        <div className="flex-1">
          <div className="flex justify-between text-[10px] text-gray-500 font-mono mb-1">
            <span>REPLAY</span>
            <span>
              {replayProgress}/{replayTotal} ({progressPct}%)
            </span>
          </div>
          {replayTotal > 0 && onSeek ? (
            <input
              type="range"
              min={0}
              max={replayTotal}
              value={replayProgress}
              onChange={(e) => onSeek(parseInt(e.target.value, 10))}
              className="w-full h-1.5 accent-green-500 cursor-pointer bg-gray-800 rounded-full"
              aria-label="Replay scrubber"
            />
          ) : (
            <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
              <motion.div
                className="h-full bg-green-500 rounded-full"
                animate={{ width: `${progressPct}%` }}
                transition={{ duration: 0.4 }}
              />
            </div>
          )}
        </div>

        {/* Speed selector */}
        <div className="flex items-center gap-1 shrink-0">
          {SPEED_OPTIONS.map((s) => (
            <button
              key={s}
              onClick={() => onSpeedChange(s)}
              className={`text-xs px-2 py-1 rounded font-mono transition-colors ${
                replaySpeed === s
                  ? "bg-green-700/60 text-green-300 border border-green-500/50"
                  : "text-gray-500 hover:text-gray-300 border border-transparent"
              }`}
            >
              {s}x
            </button>
          ))}
        </div>
      </div>

      {/* Intelligence timeline row */}
      <div className="flex items-center gap-3">
        {/* Time range selector */}
        <div className="flex items-center gap-1">
          <span className="text-[10px] text-gray-600 font-mono">RANGE</span>
          {[6, 12, 24, 48].map((h) => (
            <button
              key={h}
              onClick={() => setHoursBack(h)}
              className={`text-[10px] px-1.5 py-0.5 rounded font-mono transition-colors ${
                hoursBack === h
                  ? "bg-blue-800/60 text-blue-300 border border-blue-600/50"
                  : "text-gray-600 hover:text-gray-400 border border-transparent"
              }`}
            >
              {h}h
            </button>
          ))}
        </div>

        {/* Intel event counts */}
        <div className="flex items-center gap-2 text-[10px] font-mono">
          <span className="text-gray-600">
            {intelLoading ? (
              <span className="animate-pulse">Loading…</span>
            ) : (
              <>
                <span className="text-blue-400">{riskCount}</span>
                <span className="text-gray-600"> risk · </span>
                <span className="text-green-400">{finCount}</span>
                <span className="text-gray-600"> financial</span>
              </>
            )}
          </span>
        </div>

        {/* Current intel event preview */}
        {currentEvent && isReplaying && (
          <div className="ml-auto text-[10px] font-mono text-gray-400 truncate max-w-[200px]">
            {currentEvent.type === "risk" ? (
              <span>
                🌡️{" "}
                {(currentEvent.iso2 as string) ?? "??"}:{" "}
                {(currentEvent.risk_score as number)?.toFixed(0) ?? "--"}
              </span>
            ) : (
              <span>
                📈{" "}
                {(currentEvent.symbol as string) ?? "??"}:{" "}
                {(currentEvent.price as number)?.toFixed(2) ?? "--"}
              </span>
            )}
          </div>
        )}

        {/* Refresh button */}
        <button
          onClick={loadIntelTimeline}
          disabled={intelLoading}
          className="text-[10px] text-gray-600 hover:text-gray-400 font-mono border border-gray-700 rounded px-1.5 py-0.5 transition-colors shrink-0"
          title="Refresh intelligence timeline"
        >
          ↺
        </button>
      </div>
    </motion.div>
  );
}
