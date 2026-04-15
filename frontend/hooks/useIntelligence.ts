import { useCallback, useEffect, useRef, useState } from "react";
import {
  CountryRisk,
  IntelligenceBrief,
  NewsItem,
  OllamaStatus,
} from "../types/intelligence";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const POLL_INTERVAL_MS = 60_000; // re-fetch every 60 seconds

interface UseIntelligenceOptions {
  category?: string;
  region?: string;
  autoPoll?: boolean;
}

interface UseIntelligenceReturn {
  news: NewsItem[];
  brief: IntelligenceBrief | null;
  riskScores: CountryRisk[];
  ollamaStatus: OllamaStatus | null;
  isLoadingNews: boolean;
  isLoadingBrief: boolean;
  isLoadingRisk: boolean;
  newsError: string | null;
  fetchBrief: (category?: string) => Promise<void>;
  refetch: () => void;
}

export function useIntelligence({
  category = "world",
  region,
  autoPoll = true,
}: UseIntelligenceOptions = {}): UseIntelligenceReturn {
  const [news, setNews] = useState<NewsItem[]>([]);
  const [brief, setBrief] = useState<IntelligenceBrief | null>(null);
  const [riskScores, setRiskScores] = useState<CountryRisk[]>([]);
  const [ollamaStatus, setOllamaStatus] = useState<OllamaStatus | null>(null);
  const [isLoadingNews, setIsLoadingNews] = useState(false);
  const [isLoadingBrief, setIsLoadingBrief] = useState(false);
  const [isLoadingRisk, setIsLoadingRisk] = useState(false);
  const [newsError, setNewsError] = useState<string | null>(null);

  const mountedRef = useRef(true);
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchNews = useCallback(async () => {
    if (!mountedRef.current) return;
    setIsLoadingNews(true);
    setNewsError(null);
    try {
      const params = new URLSearchParams({ limit: "40" });
      if (category) params.set("category", category);
      if (region) params.set("region", region);
      const resp = await fetch(`${API_URL}/api/intelligence/news?${params}`);
      if (resp.ok && mountedRef.current) {
        setNews(await resp.json());
      }
    } catch {
      if (mountedRef.current) setNewsError("Failed to load news");
    } finally {
      if (mountedRef.current) setIsLoadingNews(false);
    }
  }, [category, region]);

  const fetchRisk = useCallback(async () => {
    if (!mountedRef.current) return;
    setIsLoadingRisk(true);
    try {
      const resp = await fetch(`${API_URL}/api/intelligence/risk`);
      if (resp.ok && mountedRef.current) {
        setRiskScores(await resp.json());
      }
    } catch {
      // Silently fail – risk scores are non-critical
    } finally {
      if (mountedRef.current) setIsLoadingRisk(false);
    }
  }, []);

  const fetchOllamaStatus = useCallback(async () => {
    try {
      const resp = await fetch(`${API_URL}/api/intelligence/ollama/status`);
      if (resp.ok && mountedRef.current) {
        setOllamaStatus(await resp.json());
      }
    } catch {
      if (mountedRef.current) {
        setOllamaStatus({ available: false, models: [] });
      }
    }
  }, []);

  const fetchBrief = useCallback(
    async (cat?: string) => {
      if (!mountedRef.current) return;
      setIsLoadingBrief(true);
      try {
        const resp = await fetch(
          `${API_URL}/api/intelligence/brief/${encodeURIComponent(cat ?? category)}`
        );
        if (resp.ok && mountedRef.current) {
          setBrief(await resp.json());
        }
      } catch {
        // Silently fail
      } finally {
        if (mountedRef.current) setIsLoadingBrief(false);
      }
    },
    [category]
  );

  const refetch = useCallback(() => {
    fetchNews();
    fetchRisk();
    fetchOllamaStatus();
  }, [fetchNews, fetchRisk, fetchOllamaStatus]);

  // Initial fetch
  useEffect(() => {
    mountedRef.current = true;
    refetch();
    fetchBrief();

    if (autoPoll) {
      pollTimerRef.current = setInterval(refetch, POLL_INTERVAL_MS);
    }

    return () => {
      mountedRef.current = false;
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    };
  }, [refetch, fetchBrief, autoPoll]);

  return {
    news,
    brief,
    riskScores,
    ollamaStatus,
    isLoadingNews,
    isLoadingBrief,
    isLoadingRisk,
    newsError,
    fetchBrief,
    refetch,
  };
}
