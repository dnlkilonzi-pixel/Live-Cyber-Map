import { useCallback, useEffect, useRef, useState } from "react";
import { MarketSummary, TickerQuote } from "../types/financial";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const POLL_INTERVAL_MS = 30_000; // refresh every 30 seconds

interface UseFinancialReturn {
  market: MarketSummary | null;
  isLoading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useFinancial(): UseFinancialReturn {
  const [market, setMarket] = useState<MarketSummary | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const mountedRef = useRef(true);
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchMarket = useCallback(async () => {
    if (!mountedRef.current) return;
    setIsLoading(true);
    setError(null);
    try {
      const resp = await fetch(`${API_URL}/api/financial/summary`);
      if (resp.ok && mountedRef.current) {
        setMarket(await resp.json());
      } else if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}`);
      }
    } catch (err) {
      if (mountedRef.current) {
        setError("Market data unavailable");
      }
    } finally {
      if (mountedRef.current) setIsLoading(false);
    }
  }, []);

  const refetch = useCallback(() => {
    fetchMarket();
  }, [fetchMarket]);

  useEffect(() => {
    mountedRef.current = true;
    fetchMarket();
    pollTimerRef.current = setInterval(fetchMarket, POLL_INTERVAL_MS);

    return () => {
      mountedRef.current = false;
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    };
  }, [fetchMarket]);

  return { market, isLoading, error, refetch };
}
