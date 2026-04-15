// Financial market type definitions

export type AssetClass = "stock" | "crypto" | "commodity" | "index" | "forex";

export interface TickerQuote {
  symbol: string;
  name: string;
  price: number;
  change: number;
  change_pct: number;
  volume: number | null;
  market_cap: number | null;
  high_24h: number | null;
  low_24h: number | null;
  asset_class: AssetClass;
  exchange: string | null;
  last_updated: number; // Unix timestamp
  is_real: boolean;     // true = backed by a live API, false = simulated
}

export interface MarketSummary {
  indices: TickerQuote[];
  stocks: TickerQuote[];
  crypto: TickerQuote[];
  commodities: TickerQuote[];
  forex: TickerQuote[];
  last_updated: number;
}
