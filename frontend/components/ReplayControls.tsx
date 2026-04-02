import { motion } from "framer-motion";

interface ReplayControlsProps {
  isReplaying: boolean;
  replayProgress: number;
  replayTotal: number;
  replaySpeed: number;
  onPlay: () => void;
  onStop: () => void;
  onSpeedChange: (speed: number) => void;
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
}: ReplayControlsProps) {
  const progressPct =
    replayTotal > 0 ? Math.round((replayProgress / replayTotal) * 100) : 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 20 }}
      transition={{ duration: 0.3 }}
      className="glass-panel rounded-xl px-5 py-3 flex items-center gap-5 min-w-[420px]"
    >
      {/* Play / Stop button */}
      <button
        onClick={isReplaying ? onStop : onPlay}
        className="flex items-center justify-center w-9 h-9 rounded-full border border-green-500/60 bg-green-900/30 hover:bg-green-700/40 transition-colors"
        aria-label={isReplaying ? "Stop replay" : "Start replay"}
      >
        {isReplaying ? (
          <svg
            className="w-4 h-4 text-green-400"
            fill="currentColor"
            viewBox="0 0 20 20"
          >
            <rect x="4" y="4" width="4" height="12" rx="1" />
            <rect x="12" y="4" width="4" height="12" rx="1" />
          </svg>
        ) : (
          <svg
            className="w-4 h-4 text-green-400 ml-0.5"
            fill="currentColor"
            viewBox="0 0 20 20"
          >
            <path d="M6 4l12 6-12 6V4z" />
          </svg>
        )}
      </button>

      {/* Progress bar */}
      <div className="flex-1">
        <div className="flex justify-between text-[10px] text-gray-500 font-mono mb-1">
          <span>REPLAY</span>
          <span>
            {replayProgress}/{replayTotal} ({progressPct}%)
          </span>
        </div>
        <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
          <motion.div
            className="h-full bg-green-500 rounded-full"
            animate={{ width: `${progressPct}%` }}
            transition={{ duration: 0.4 }}
          />
        </div>
      </div>

      {/* Speed selector */}
      <div className="flex items-center gap-1">
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
    </motion.div>
  );
}
