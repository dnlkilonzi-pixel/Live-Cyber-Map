import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { format } from "date-fns";
import { AttackEvent, AttackType } from "../types/attack";

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

const COUNTRY_FLAGS: Record<string, string> = {
  US: "🇺🇸",
  CN: "🇨🇳",
  RU: "🇷🇺",
  DE: "🇩🇪",
  GB: "🇬🇧",
  FR: "🇫🇷",
  BR: "🇧🇷",
  IN: "🇮🇳",
  JP: "🇯🇵",
  KR: "🇰🇷",
  AU: "🇦🇺",
  CA: "🇨🇦",
  NL: "🇳🇱",
  SG: "🇸🇬",
  UA: "🇺🇦",
  IR: "🇮🇷",
  KP: "🇰🇵",
  TR: "🇹🇷",
  PL: "🇵🇱",
  IT: "🇮🇹",
};

function countryFlag(country: string): string {
  return COUNTRY_FLAGS[country] ?? "🌐";
}

function severityColor(severity: number): string {
  if (severity >= 8) return "#ff4444";
  if (severity >= 5) return "#ffaa00";
  return "#00ff88";
}

function severityLabel(severity: number): string {
  if (severity >= 8) return "CRIT";
  if (severity >= 5) return "HIGH";
  if (severity >= 3) return "MED";
  return "LOW";
}

const PAGE_SIZE = 20;

interface AttackFeedProps {
  attacks: AttackEvent[];
}

export default function AttackFeed({ attacks }: AttackFeedProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [page, setPage] = useState(0);

  const totalPages = Math.max(1, Math.ceil(attacks.length / PAGE_SIZE));
  // Clamp page in case attacks shrink
  const safePage = Math.min(page, totalPages - 1);
  const pageItems = attacks.slice(safePage * PAGE_SIZE, (safePage + 1) * PAGE_SIZE);

  // Scroll to top when we're on page 0 and new events arrive
  const prevLengthRef = useRef(attacks.length);
  useEffect(() => {
    if (attacks.length > prevLengthRef.current && safePage === 0) {
      if (scrollRef.current) scrollRef.current.scrollTop = 0;
    }
    prevLengthRef.current = attacks.length;
  }, [attacks.length, safePage]);

  return (
    <div className="flex flex-col w-72 h-full">
      {/* Header */}
      <div className="glass-panel p-3 rounded-t-lg border-b border-gray-700/50">
        <div className="flex items-center justify-between">
          <span className="text-green-400 text-xs font-bold tracking-widest uppercase">
            Live Feed
          </span>
          <span className="text-gray-500 text-xs font-mono">
            {attacks.length} events
          </span>
        </div>
      </div>

      {/* Scrollable feed */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto dashboard-scroll glass-panel p-2 space-y-1"
      >
        {pageItems.length === 0 ? (
          <div className="flex items-center justify-center h-32 text-gray-600 text-xs">
            Waiting for attacks…
          </div>
        ) : (
          <AnimatePresence initial={false}>
            {pageItems.map((attack) => {
              const color = ATTACK_COLORS[attack.attack_type] ?? "#ffffff";
              const sColor = severityColor(attack.severity);
              const ts = (() => {
                try {
                  return format(new Date(attack.timestamp), "HH:mm:ss");
                } catch {
                  return "--:--:--";
                }
              })();

              return (
                <motion.div
                  key={attack.id}
                  layout
                  initial={{ opacity: 0, x: 24 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -24 }}
                  transition={{ duration: 0.25 }}
                  className="rounded-md p-2 border border-gray-700/60 bg-black/30 hover:bg-black/50 transition-colors"
                >
                  {/* Top row: timestamp + severity badge */}
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-gray-500 text-xs font-mono">
                      {ts}
                    </span>
                    <span
                      className="text-[10px] font-bold px-1.5 py-0.5 rounded"
                      style={{
                        color: sColor,
                        border: `1px solid ${sColor}`,
                        backgroundColor: `${sColor}18`,
                      }}
                    >
                      {severityLabel(attack.severity)}
                    </span>
                  </div>

                  {/* Source → Dest */}
                  <div className="flex items-center gap-1 text-xs mb-1">
                    <span>{countryFlag(attack.source_country)}</span>
                    <span className="text-gray-400 truncate max-w-[60px]">
                      {attack.source_country}
                    </span>
                    <span className="text-gray-600">→</span>
                    <span>{countryFlag(attack.dest_country)}</span>
                    <span className="text-gray-400 truncate max-w-[60px]">
                      {attack.dest_country}
                    </span>
                  </div>

                  {/* Attack type badge + IPs */}
                  <div className="flex items-center justify-between">
                    <span
                      className="text-[10px] font-bold px-1.5 py-0.5 rounded-sm"
                      style={{
                        color,
                        border: `1px solid ${color}40`,
                        backgroundColor: `${color}18`,
                      }}
                    >
                      {attack.attack_type}
                    </span>
                    <span className="text-[10px] text-gray-600 font-mono truncate ml-1">
                      {attack.source_ip}
                    </span>
                  </div>

                  {/* Severity bar */}
                  <div className="mt-1.5 h-1 bg-gray-800 rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all duration-300"
                      style={{
                        width: `${(attack.severity / 10) * 100}%`,
                        backgroundColor: sColor,
                      }}
                    />
                  </div>
                </motion.div>
              );
            })}
          </AnimatePresence>
        )}
      </div>

      {/* Pagination bar */}
      {totalPages > 1 && (
        <div className="glass-panel rounded-b-lg border-t border-gray-700/50 px-3 py-1.5 flex items-center justify-between">
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={safePage === 0}
            className="text-[10px] text-gray-500 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed px-1 transition-colors"
          >
            ◀
          </button>
          <span className="text-[10px] text-gray-500 font-mono">
            {safePage + 1} / {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            disabled={safePage >= totalPages - 1}
            className="text-[10px] text-gray-500 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed px-1 transition-colors"
          >
            ▶
          </button>
        </div>
      )}
    </div>
  );
}
