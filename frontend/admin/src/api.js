import { useEffect, useRef, useState } from "react";

const REFRESH_MS = 15000;

async function request(path, options) {
  const res = await fetch(path, options);
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail || body.error || detail;
    } catch {
      /* ignore - not JSON */
    }
    throw new Error(detail);
  }
  return res.json();
}

export const api = {
  get: (path) => request(path),
  postJSON: (path, body) =>
    request(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  postForm: (path, formData) => request(path, { method: "POST", body: formData }),
};

/**
 * Polls GET /pipeline1/dashboard/overview. Real backend data only - no
 * mocked/fabricated numbers. Keeps the last successful payload on screen if
 * a poll fails, rather than flashing an empty dashboard.
 */
export function useDashboardOverview() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const timerRef = useRef(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const json = await api.get("/pipeline1/dashboard/overview");
        if (!cancelled) {
          setData(json);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) setError(err.message || "Erreur de chargement");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    timerRef.current = setInterval(load, REFRESH_MS);
    return () => {
      cancelled = true;
      clearInterval(timerRef.current);
    };
  }, []);

  return { data, error, loading };
}

/** Generic one-shot fetch-on-mount hook with a manual refetch() escape hatch. */
export function useFetch(path, deps = []) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  async function refetch() {
    setLoading(true);
    try {
      const json = await api.get(path);
      setData(json);
      setError(null);
    } catch (err) {
      setError(err.message || "Erreur de chargement");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (path) refetch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, error, loading, refetch };
}
