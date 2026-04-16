import { motion, AnimatePresence } from "framer-motion";
import CountUp from "react-countup";
import { AttackType, Stats } from "../types/attack";

const ATTACK_COLORS: Record<string, string> = {
  [AttackType.DDoS]: "#ff4444",
  [AttackType.Malware]: "#ff8800",
  [AttackType.Phishing]: "#ffff00",
  [AttackType.Ransomware]: "#ff0088",
  [AttackType.Intrusion]: "#00ffff",
  [AttackType.BruteForce]: "#ff00ff",
  [AttackType.SQLInjection]: "#00ff88",
  [AttackType.XSS]: "#8888ff",
  [AttackType.ZeroDay]: "#ffffff",
};

interface DashboardProps {
  stats: Stats | null;
  isConnected: boolean;
  isAnomaly: boolean;
  anomalyScore: number;
}

function BarRow({
  label,
  value,
  max,
  color,
}: {
  label: string;
  value: number;
  max: number;
  color?: string;
}) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div className="mb-1">
      <div className="flex justify-between text-xs mb-0.5">
        <span className="text-gray-300 truncate max-w-[140px]">{label}</span>
        <span className="text-gray-400 ml-1">{value}</span>
      </div>
      <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
        <motion.div
          className="h-full rounded-full"
          style={{ backgroundColor: color ?? "#00ff88" }}
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.6, ease: "easeOut" }}
        />
      </div>
    </div>
  );
}

export default function Dashboard({
  stats,
  isConnected,
  isAnomaly,
  anomalyScore,
}: DashboardProps) {
  const eps = stats?.events_per_second ?? 0;
  const total = stats?.total_events ?? 0;
  const topAttackers = stats?.top_attackers?.slice(0, 5) ?? [];
  const topTargets = stats?.top_targets?.slice(0, 5) ?? [];
  const typeStats = stats?.attack_type_stats ?? {};

  const maxAttackerCount = topAttackers.reduce(
    (m, a) => Math.max(m, a.count),
    1
  );
  const maxTargetCount = topTargets.reduce((m, t) => Math.max(m, t.count), 1);
  const maxTypeCount = Math.max(...Object.values(typeStats), 1);

  return (
    <div className="flex flex-col gap-3 w-80 p-4 h-full overflow-y-auto dashboard-scroll">
      {/* Header */}
      <div className="glass-panel p-3 rounded-lg">
        <div className="flex items-center gap-2 mb-1">
          <span className="blink-dot" />
          <span className="text-green-400 font-bold tracking-widest text-sm uppercase">
            Live Cyber Map
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`w-2 h-2 rounded-full ${
              isConnected ? "bg-green-400" : "bg-red-500"
            }`}
          />
          <span
            className={`text-xs font-mono ${
              isConnected ? "text-green-400" : "text-red-400"
            }`}
          >
            {isConnected ? "CONNECTED" : "DISCONNECTED"}
          </span>
        </div>
      </div>

      {/* Anomaly Alert */}
      <AnimatePresence>
        {isAnomaly && (
          <motion.div
            key="anomaly"
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            className="rounded-lg border border-red-500 bg-red-900/40 p-3"
          >
            <div className="flex items-center gap-2 mb-1">
              <span className="text-red-400 text-xs font-bold tracking-widest uppercase animate-pulse">
                ⚠ Anomaly Detected
              </span>
            </div>
            <div className="text-xs text-red-300 font-mono">
              Score:{" "}
              <span className="text-red-200 font-bold">
                {anomalyScore.toFixed(3)}
              </span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Events/sec + Total */}
      <div className="glass-panel p-3 rounded-lg grid grid-cols-2 gap-3">
        <div>
          <div className="text-gray-500 text-xs uppercase tracking-wider mb-1">
            Events/sec
          </div>
          <div className="text-green-400 font-mono font-bold text-2xl glow-green">
            <CountUp end={eps} decimals={1} duration={0.8} preserveValue />
          </div>
        </div>
        <div>
          <div className="text-gray-500 text-xs uppercase tracking-wider mb-1">
            Total Events
          </div>
          <div className="text-cyan-400 font-mono font-bold text-2xl glow-cyan">
            <CountUp end={total} duration={0.8} preserveValue separator="," />
          </div>
        </div>
        {stats?.rolling_avg != null && (
          <div className="col-span-2">
            <div className="text-gray-500 text-xs uppercase tracking-wider mb-1">
              Rolling Avg
            </div>
            <div className="text-yellow-400 font-mono text-sm">
              <CountUp
                end={stats.rolling_avg}
                decimals={2}
                duration={0.8}
                preserveValue
              />{" "}
              <span className="text-gray-500 text-xs">eps</span>
            </div>
          </div>
        )}
      </div>

      {/* Anomaly Score Gauge */}
      <div className="glass-panel p-3 rounded-lg">
        <div className="text-gray-500 text-xs uppercase tracking-wider mb-2">
          Anomaly Score
        </div>
        <AnomalyGauge score={anomalyScore} isAnomaly={isAnomaly} />
      </div>

      {/* Top Attackers */}
      <div className="glass-panel p-3 rounded-lg">
        <div className="text-gray-500 text-xs uppercase tracking-wider mb-2">
          Top Attackers
        </div>
        {topAttackers.length > 0 ? (
          topAttackers.map((a) => (
            <BarRow
              key={a.ip}
              label={`${a.country} · ${a.ip}`}
              value={a.count}
              max={maxAttackerCount}
              color="#ff4444"
            />
          ))
        ) : (
          <p className="text-gray-600 text-xs">Awaiting data…</p>
        )}
      </div>

      {/* Top Targets */}
      <div className="glass-panel p-3 rounded-lg">
        <div className="text-gray-500 text-xs uppercase tracking-wider mb-2">
          Top Targets
        </div>
        {topTargets.length > 0 ? (
          topTargets.map((t) => (
            <BarRow
              key={t.country}
              label={t.country}
              value={t.count}
              max={maxTargetCount}
              color="#00ffff"
            />
          ))
        ) : (
          <p className="text-gray-600 text-xs">Awaiting data…</p>
        )}
      </div>

      {/* Attack Type Breakdown */}
      <div className="glass-panel p-3 rounded-lg">
        <div className="text-gray-500 text-xs uppercase tracking-wider mb-2">
          Attack Types
        </div>
        {Object.entries(typeStats).length > 0 ? (
          Object.entries(typeStats)
            .sort((a, b) => b[1] - a[1])
            .map(([type, count]) => (
              <BarRow
                key={type}
                label={type}
                value={count}
                max={maxTypeCount}
                color={ATTACK_COLORS[type] ?? "#00ff88"}
              />
            ))
        ) : (
          <p className="text-gray-600 text-xs">Awaiting data…</p>
        )}
      </div>
    </div>
  );
}

/** Semi-circular arc gauge showing anomaly score 0–max. */
function AnomalyGauge({ score, isAnomaly }: { score: number; isAnomaly: boolean }) {
  const W = 120;
  const H = 70;
  const CX = W / 2;
  const CY = H - 10;
  const R = 48;
  // Cap display at 3.0 for the gauge arc
  const MAX_SCORE = 3.0;
  const clampedScore = Math.min(score, MAX_SCORE);
  const fraction = clampedScore / MAX_SCORE;

  // Arc spans from 180° (left) to 0° (right), i.e. a semi-circle
  const startAngle = Math.PI;
  const endAngle = 0;
  const sweepAngle = startAngle - endAngle; // π radians
  const fillAngle = startAngle - fraction * sweepAngle;

  const toXY = (angle: number) => ({
    x: CX + R * Math.cos(angle),
    y: CY - R * Math.sin(angle),
  });

  const arcStart = toXY(startAngle);
  const arcEnd = toXY(endAngle);
  const needleEnd = toXY(fillAngle);

  const trackPath = `M ${arcStart.x} ${arcStart.y} A ${R} ${R} 0 0 1 ${arcEnd.x} ${arcEnd.y}`;
  const fillPath = fraction > 0
    ? `M ${arcStart.x} ${arcStart.y} A ${R} ${R} 0 ${fraction > 0.5 ? 1 : 0} 1 ${needleEnd.x} ${needleEnd.y}`
    : "";

  const color = isAnomaly ? "#f87171" : score > 0.5 ? "#fbbf24" : "#4ade80";

  return (
    <div className="flex flex-col items-center">
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} aria-label="Anomaly score gauge">
        {/* Track */}
        <path d={trackPath} fill="none" stroke="#1f2937" strokeWidth={8} strokeLinecap="round" />
        {/* Fill */}
        {fillPath && (
          <path d={fillPath} fill="none" stroke={color} strokeWidth={8} strokeLinecap="round" />
        )}
        {/* Centre dot */}
        <circle cx={CX} cy={CY} r={4} fill={color} />
        {/* Score text */}
        <text x={CX} y={CY - 14} textAnchor="middle" fill={color} fontSize={13} fontFamily="monospace" fontWeight="bold">
          {score.toFixed(2)}
        </text>
      </svg>
      <div className="flex justify-between w-full px-1 -mt-1">
        <span className="text-[10px] text-gray-600 font-mono">0</span>
        <span className="text-[10px] font-mono" style={{ color }}>{isAnomaly ? "ANOMALY" : "normal"}</span>
        <span className="text-[10px] text-gray-600 font-mono">{MAX_SCORE}+</span>
      </div>
    </div>
  );
}
