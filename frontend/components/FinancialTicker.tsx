/**
 * FinancialTicker – scrolling financial market data panel.
 *
 * Shows stocks, crypto, commodities, and forex rates with
 * color-coded change indicators and live sparkline simulation.
 */
import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { MarketSummary, TickerQuote, AssetClass } from "../types/financial";

type Tab = "indices" | "stocks" | "crypto" | "commodities" | "forex";

const TABS: { id: Tab; label: string; icon: string }[] = [
  { id: "indices", label: "Indices", icon: "📊" },
  { id: "stocks", label: "Stocks", icon: "🏢" },
  { id: "crypto", label: "Crypto", icon: "₿" },
  { id: "commodities", label: "Commodities", icon: "🛢️" },
  { id: "forex", label: "FX", icon: "💱" },
];

interface FinancialTickerProps {
  market: MarketSummary | null;
  isLoading: boolean;
  onClose: () => void;
}

export default function FinancialTicker({
  market,
  isLoading,
  onClose,
}: FinancialTickerProps) {
  const [activeTab, setActiveTab] = useState<Tab>("indices");

  const quotes: TickerQuote[] = market
    ? (market[activeTab] as TickerQuote[]) ?? []
    : [];

  return (
    <div className="flex flex-col h-full w-72 text-sm">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/10 shrink-0">
        <div>
          <span className="text-xs uppercase tracking-widest text-[var(--color-accent)] font-bold">
            Markets
          </span>
          {market && (
            <div className="text-xs text-gray-600 mt-0.5">
              Updated {formatTimeAgo(market.last_updated)}
            </div>
          )}
        </div>
        <button
          onClick={onClose}
          className="text-gray-500 hover:text-white text-lg leading-none p-1"
          aria-label="Close financial panel"
        >
          ×
        </button>
      </div>

      {/* Market summary bar */}
      {market && (
        <div className="flex items-center gap-2 px-3 py-2 border-b border-white/10 overflow-x-auto scrollbar-hide shrink-0">
          {market.indices.slice(0, 4).map((q) => (
            <div key={q.symbol} className="shrink-0 text-center">
              <div className="text-xs text-gray-500 font-mono">{q.symbol.replace("^", "")}</div>
              <div className="text-xs font-mono font-bold text-white">
                {formatPrice(q)}
              </div>
              <ChangeTag pct={q.change_pct} />
            </div>
          ))}
        </div>
      )}

      {/* Tabs */}
      <div className="flex border-b border-white/10 shrink-0">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex-1 text-xs py-2 transition-colors ${
              activeTab === tab.id
                ? "border-b-2 border-[var(--color-accent)] text-[var(--color-accent)] font-bold"
                : "text-gray-500 hover:text-gray-300"
            }`}
          >
            <span className="hidden sm:inline">{tab.icon} </span>
            {tab.label}
          </button>
        ))}
      </div>

      {/* Quote list */}
      <div className="flex-1 overflow-y-auto">
        {isLoading && !market ? (
          <div className="p-3 space-y-2.5">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="flex justify-between items-center">
                <div className="space-y-1">
                  <div className="h-3 bg-white/5 rounded animate-pulse w-16" />
                  <div className="h-2 bg-white/5 rounded animate-pulse w-24" />
                </div>
                <div className="h-4 bg-white/5 rounded animate-pulse w-14" />
              </div>
            ))}
          </div>
        ) : quotes.length === 0 ? (
          <div className="p-4 text-center text-gray-600 text-xs">
            No data available
          </div>
        ) : (
          <div>
            {quotes.map((q) => (
              <QuoteRow key={q.symbol} quote={q} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Quote row
// ---------------------------------------------------------------------------

function QuoteRow({ quote }: { quote: TickerQuote }) {
  const isPositive = quote.change_pct >= 0;
  const absChgPct = Math.abs(quote.change_pct);
  // Intensity bar width (0–20% → 0–100%)
  const barWidth = Math.min(100, (absChgPct / 5) * 100);

  return (
    <div className="relative flex items-center justify-between px-3 py-2.5 border-b border-white/5 hover:bg-white/5 transition-colors group overflow-hidden">
      {/* Intensity background bar */}
      <div
        className="absolute inset-0 opacity-5 pointer-events-none"
        style={{
          background: isPositive ? "#00ff88" : "#ff4444",
          width: `${barWidth}%`,
        }}
      />

      <div className="flex-1 min-w-0 relative">
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-mono font-bold text-white truncate">
            {quote.symbol}
          </span>
          {quote.asset_class === "crypto" && (
            <span className="text-xs text-yellow-500">₿</span>
          )}
        </div>
        <div className="text-xs text-gray-500 truncate max-w-[140px]">
          {quote.name}
        </div>
      </div>

      <div className="text-right relative">
        <div className="text-xs font-mono font-bold text-white">
          {formatPrice(quote)}
        </div>
        <ChangeTag pct={quote.change_pct} abs={quote.change} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Change tag
// ---------------------------------------------------------------------------

function ChangeTag({
  pct,
  abs,
}: {
  pct: number;
  abs?: number;
}) {
  const isPositive = pct >= 0;
  return (
    <div
      className={`text-xs font-mono ${
        isPositive ? "text-green-400" : "text-red-400"
      }`}
    >
      {isPositive ? "▲" : "▼"} {Math.abs(pct).toFixed(2)}%
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatPrice(quote: TickerQuote): string {
  const p = quote.price;
  if (p === null || p === undefined) return "—";
  if (p >= 10000) return p.toLocaleString(undefined, { maximumFractionDigits: 0 });
  if (p >= 100) return p.toFixed(2);
  if (p >= 1) return p.toFixed(3);
  return p.toFixed(4);
}

function formatTimeAgo(ts: number): string {
  const diff = Date.now() - ts * 1000;
  if (diff < 10_000) return "just now";
  if (diff < 60_000) return `${Math.round(diff / 1000)}s ago`;
  return `${Math.round(diff / 60_000)}m ago`;
}
