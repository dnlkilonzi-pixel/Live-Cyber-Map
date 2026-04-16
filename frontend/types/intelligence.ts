// Intelligence and news type definitions

export interface NewsItem {
  id: string;
  title: string;
  summary: string;
  url: string;
  source: string;
  category: NewsCategory;
  region: string;
  published_at: number; // Unix timestamp
  sentiment_score: number; // -1 to +1
  tags: string[];
  country_codes: string[];
}

export type NewsCategory =
  | "world"
  | "technology"
  | "finance"
  | "security"
  | "geopolitics"
  | "energy"
  | "health";

export interface IntelligenceBrief {
  brief: string;
  source_count: number;
  category: string;
  ai_generated: boolean;
}

export interface CountryRisk {
  iso2: string;
  iso3: string;
  name: string;
  risk_score: number;   // 0–100
  cyber_score: number;
  news_score: number;
  stability_baseline: number;
  attack_count_24h: number;
  lat: number;
  lng: number;
  last_updated: number;
}

export interface OllamaStatus {
  available: boolean;
  models: Array<{ name: string; size: number }>;
}
