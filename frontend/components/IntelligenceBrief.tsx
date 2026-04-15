/**
 * IntelligenceBrief – AI-synthesized news briefs panel.
 *
 * Displays AI-generated summaries from the local Ollama model alongside
 * recent headlines from the news aggregator.
 */
import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { NewsCategory, NewsItem, IntelligenceBrief as BriefType, OllamaStatus } from "../types/intelligence";

const CATEGORIES: { id: NewsCategory; label: string; icon: string }[] = [
  { id: "world", label: "World", icon: "🌍" },
  { id: "security", label: "Security", icon: "🛡️" },
  { id: "technology", label: "Tech", icon: "💻" },
  { id: "finance", label: "Finance", icon: "📈" },
  { id: "geopolitics", label: "Geopolitics", icon: "⚔️" },
  { id: "energy", label: "Energy", icon: "⚡" },
  { id: "health", label: "Health", icon: "🏥" },
];

interface IntelligenceBriefProps {
  news: NewsItem[];
  brief: BriefType | null;
  ollamaStatus: OllamaStatus | null;
  isLoadingNews: boolean;
  isLoadingBrief: boolean;
  onCategoryChange: (cat: NewsCategory) => void;
  onRefreshBrief: (cat?: string) => void;
  onClose: () => void;
}

export default function IntelligenceBriefPanel({
  news,
  brief,
  ollamaStatus,
  isLoadingNews,
  isLoadingBrief,
  onCategoryChange,
  onRefreshBrief,
  onClose,
}: IntelligenceBriefProps) {
  const [activeCategory, setActiveCategory] = useState<NewsCategory>("world");
  const [expanded, setExpanded] = useState<string | null>(null);

  const handleCategoryClick = (cat: NewsCategory) => {
    setActiveCategory(cat);
    onCategoryChange(cat);
  };

  const formatTime = (ts: number) => {
    const d = new Date(ts * 1000);
    const now = Date.now();
    const diff = now - d.getTime();
    if (diff < 3600_000) return `${Math.round(diff / 60_000)}m ago`;
    if (diff < 86400_000) return `${Math.round(diff / 3600_000)}h ago`;
    return d.toLocaleDateString();
  };

  const sentimentColor = (score: number) => {
    if (score > 0.1) return "text-green-400";
    if (score < -0.1) return "text-red-400";
    return "text-gray-400";
  };

  return (
    <div className="flex flex-col h-full w-80 text-sm">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/10 shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-[var(--color-accent)] font-bold text-xs uppercase tracking-widest">
            Intelligence
          </span>
          {ollamaStatus && (
            <span
              className={`text-xs px-1.5 py-0.5 rounded font-mono ${
                ollamaStatus.available
                  ? "bg-green-900/50 text-green-400"
                  : "bg-gray-800 text-gray-500"
              }`}
              title={
                ollamaStatus.available
                  ? `AI: ${ollamaStatus.models[0]?.name ?? "ready"}`
                  : "Ollama not running – plain summaries only"
              }
            >
              {ollamaStatus.available ? "AI ●" : "AI ○"}
            </span>
          )}
        </div>
        <button
          onClick={onClose}
          className="text-gray-500 hover:text-white text-lg leading-none p-1"
          aria-label="Close intelligence panel"
        >
          ×
        </button>
      </div>

      {/* Category tabs */}
      <div className="flex overflow-x-auto gap-1 px-2 py-2 border-b border-white/10 shrink-0 scrollbar-hide">
        {CATEGORIES.map((cat) => (
          <button
            key={cat.id}
            onClick={() => handleCategoryClick(cat.id)}
            className={`shrink-0 text-xs px-2 py-1 rounded transition-colors whitespace-nowrap ${
              activeCategory === cat.id
                ? "bg-[var(--color-accent)] text-black font-bold"
                : "text-gray-400 hover:text-white hover:bg-white/10"
            }`}
          >
            {cat.icon} {cat.label}
          </button>
        ))}
      </div>

      {/* AI Brief */}
      <div className="px-3 py-3 border-b border-white/10 shrink-0">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-gray-500 uppercase tracking-wider">
            AI Brief
          </span>
          <button
            onClick={() => onRefreshBrief(activeCategory)}
            disabled={isLoadingBrief}
            className="text-xs text-[var(--color-accent)] hover:opacity-70 disabled:opacity-40 transition-opacity"
          >
            {isLoadingBrief ? "Generating…" : "↻ Refresh"}
          </button>
        </div>

        {isLoadingBrief ? (
          <div className="space-y-1.5">
            {[3, 5, 4].map((w, i) => (
              <div
                key={i}
                className="h-3 bg-white/5 rounded animate-pulse"
                style={{ width: `${w * 20}%` }}
              />
            ))}
          </div>
        ) : brief ? (
          <div className="text-xs text-gray-300 leading-relaxed">
            {brief.brief}
            <div className="flex items-center justify-between mt-2 text-gray-600">
              <span>{brief.source_count} sources</span>
              <span
                className={
                  brief.ai_generated ? "text-green-500" : "text-gray-600"
                }
              >
                {brief.ai_generated ? "✦ AI-synthesized" : "Text summary"}
              </span>
            </div>
          </div>
        ) : (
          <div className="text-xs text-gray-600 italic">
            Click refresh to generate an AI brief
          </div>
        )}
      </div>

      {/* News feed */}
      <div className="flex-1 overflow-y-auto">
        {isLoadingNews ? (
          <div className="p-3 space-y-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="space-y-1.5">
                <div className="h-3 bg-white/5 rounded animate-pulse w-full" />
                <div className="h-3 bg-white/5 rounded animate-pulse w-4/5" />
                <div className="h-2 bg-white/5 rounded animate-pulse w-1/3" />
              </div>
            ))}
          </div>
        ) : news.length === 0 ? (
          <div className="p-4 text-center text-gray-600 text-xs">
            No news available. Backend may be starting up…
          </div>
        ) : (
          <div>
            {news.map((item) => (
              <div key={item.id} className="border-b border-white/5">
                <button
                  className="w-full text-left px-3 py-2.5 hover:bg-white/5 transition-colors"
                  onClick={() =>
                    setExpanded(expanded === item.id ? null : item.id)
                  }
                >
                  <div className="flex items-start gap-2">
                    <div className="flex-1 min-w-0">
                      <p className="text-xs text-gray-200 leading-snug line-clamp-2 text-left">
                        {item.title}
                      </p>
                      <div className="flex items-center gap-2 mt-1">
                        <span className="text-gray-600 text-xs truncate max-w-[100px]">
                          {item.source}
                        </span>
                        <span className="text-gray-700 text-xs">·</span>
                        <span className="text-gray-600 text-xs">
                          {formatTime(item.published_at)}
                        </span>
                        <span
                          className={`text-xs ml-auto ${sentimentColor(item.sentiment_score)}`}
                          title={`Sentiment: ${item.sentiment_score > 0 ? "+" : ""}${item.sentiment_score.toFixed(2)}`}
                        >
                          {item.sentiment_score > 0.1
                            ? "▲"
                            : item.sentiment_score < -0.1
                            ? "▼"
                            : "—"}
                        </span>
                      </div>
                    </div>
                  </div>
                </button>

                {/* Expanded summary */}
                <AnimatePresence initial={false}>
                  {expanded === item.id && item.summary && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.2 }}
                      className="overflow-hidden"
                    >
                      <div className="px-3 pb-2.5">
                        <p className="text-xs text-gray-400 leading-relaxed">
                          {item.summary}
                        </p>
                        <a
                          href={item.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs text-[var(--color-accent)] hover:opacity-70 mt-1 inline-block"
                          onClick={(e) => e.stopPropagation()}
                        >
                          Read full article →
                        </a>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
