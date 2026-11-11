"use client";

import { useCallback, useEffect, useState } from "react";
import { describeApiError, fetchSymbols, type SymbolInfo } from "@/lib/api";

/**
 * Load the tracked symbol list once and keep a selected ticker valid.
 * Returns the list, the selection, its setter, an error message and a retry.
 */
export function useSymbols(initialTicker: string = "") {
  const [symbols, setSymbols] = useState<SymbolInfo[]>([]);
  const [ticker, setTicker] = useState<string>(initialTicker);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchSymbols();
      setSymbols(data);
      setTicker((prev) => (prev && data.some((s) => s.ticker === prev) ? prev : data[0]?.ticker ?? ""));
    } catch (err) {
      setError(describeApiError(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const selected = symbols.find((s) => s.ticker === ticker);
  return { symbols, ticker, setTicker, selected, error, loading, reload };
}
