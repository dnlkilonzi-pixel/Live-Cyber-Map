import dynamic from "next/dynamic";
import Head from "next/head";
import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useWebSocket } from "../hooks/useWebSocket";
import Dashboard from "../components/Dashboard";
import AttackFeed from "../components/AttackFeed";
import ReplayControls from "../components/ReplayControls";

// Globe is browser-only — must skip SSR
const Globe = dynamic(() => import("../components/Globe"), { ssr: false });

export default function Home() {
  const { attacks, stats, isConnected, isAnomaly, anomalyScore, sendMessage } =
    useWebSocket();

  const [isReplaying, setIsReplaying] = useState(false);
  const [replayProgress, setReplayProgress] = useState(0);
  const [replayTotal, setReplayTotal] = useState(0);
  const [replaySpeed, setReplaySpeed] = useState(1);
  const [showReplay, setShowReplay] = useState(false);

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
    if (isReplaying) {
      sendMessage("set_replay_speed", { speed });
    }
  }

  return (
    <>
      <Head>
        <title>Live Cyber Map</title>
        <meta
          name="description"
          content="Real-time global cyber attack visualization"
        />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <link rel="icon" href="/favicon.ico" />
      </Head>

      {/* Root container — full screen */}
      <div className="relative w-screen h-screen overflow-hidden bg-[#000011]">
        {/* === Globe layer (background) === */}
        <div className="absolute inset-0 z-0">
          <Globe attacks={attacks} />
        </div>

        {/* === Top bar === */}
        <div className="absolute top-0 left-0 right-0 z-20 flex items-center justify-between px-4 py-2 bg-gradient-to-b from-black/70 to-transparent pointer-events-none">
          <div className="flex items-center gap-3 pointer-events-auto">
            <span className="blink-dot" />
            <span className="text-green-400 font-bold tracking-widest text-base uppercase glow-green">
              Live Cyber Map
            </span>
            <span className="text-gray-600 text-xs hidden sm:block">
              Real-time threat intelligence
            </span>
          </div>

          <div className="flex items-center gap-3 pointer-events-auto">
            <AnimatePresence>
              {isAnomaly && (
                <motion.div
                  key="anomaly-banner"
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.9 }}
                  className="flex items-center gap-2 bg-red-900/60 border border-red-500 rounded px-3 py-1 animate-pulse"
                >
                  <span className="text-red-400 text-xs font-bold tracking-widest uppercase">
                    ⚠ Anomaly Detected
                  </span>
                  <span className="text-red-300 text-xs font-mono">
                    {anomalyScore.toFixed(3)}
                  </span>
                </motion.div>
              )}
            </AnimatePresence>

            <div className="flex items-center gap-2">
              <span
                className={`w-2 h-2 rounded-full ${
                  isConnected ? "bg-green-400 shadow-green-400" : "bg-red-500"
                }`}
                style={
                  isConnected
                    ? { boxShadow: "0 0 6px #4ade80" }
                    : undefined
                }
              />
              <span
                className={`text-xs font-mono ${
                  isConnected ? "text-green-400" : "text-red-400"
                }`}
              >
                {isConnected ? "CONNECTED" : "OFFLINE"}
              </span>
            </div>

            {/* Replay toggle */}
            <button
              onClick={() => setShowReplay((v) => !v)}
              className="text-gray-400 hover:text-gray-200 text-xs border border-gray-700 hover:border-gray-500 rounded px-2 py-1 transition-colors"
            >
              REPLAY
            </button>
          </div>
        </div>

        {/* === Left panel — Dashboard === */}
        <div className="absolute top-12 left-0 bottom-16 z-10 overflow-hidden">
          <Dashboard
            stats={stats}
            isConnected={isConnected}
            isAnomaly={isAnomaly}
            anomalyScore={anomalyScore}
          />
        </div>

        {/* === Right panel — Attack Feed === */}
        <div className="absolute top-12 right-0 bottom-16 z-10 overflow-hidden">
          <AttackFeed attacks={attacks} />
        </div>

        {/* === Bottom center — Replay Controls === */}
        <div className="absolute bottom-4 left-0 right-0 z-20 flex justify-center pointer-events-none">
          <AnimatePresence>
            {showReplay && (
              <div className="pointer-events-auto">
                <ReplayControls
                  isReplaying={isReplaying}
                  replayProgress={replayProgress}
                  replayTotal={replayTotal}
                  replaySpeed={replaySpeed}
                  onPlay={handlePlay}
                  onStop={handleStop}
                  onSpeedChange={handleSpeedChange}
                />
              </div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </>
  );
}
