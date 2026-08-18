import { useEffect, useState } from "react";
import { Unauthorized, api } from "./api";

export function useApi<T>(path: string, onAuthFail: () => void) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    api<T>(path)
      .then((d) => live && setData(d))
      .catch((e) => {
        if (!live) return;
        if (e instanceof Unauthorized) onAuthFail();
        else setError(String(e.message ?? e));
      });
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path]);
  return { data, error };
}

export function doneRatio(counts: Record<string, number>): { done: number; total: number } {
  const done = counts["done"] ?? 0;
  const total = Object.entries(counts)
    .filter(([s]) => s !== "cancelled")
    .reduce((n, [, c]) => n + c, 0);
  return { done, total };
}

export function ProgressBar({ counts }: { counts: Record<string, number> }) {
  const { done, total } = doneRatio(counts);
  const pct = total === 0 ? 0 : Math.round((done / total) * 100);
  return (
    <div className="progress" title={`${done}/${total} done`}>
      <div className="progress-fill" style={{ width: `${pct}%` }} />
      <span className="progress-text">
        {done}/{total} · {pct}%
      </span>
    </div>
  );
}
