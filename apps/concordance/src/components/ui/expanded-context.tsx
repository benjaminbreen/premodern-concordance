"use client";

import { useState } from "react";
import { appPath } from "@/config/app-path";
import styles from "./expanded-context.module.css";

type ContextResponse = {
  excerpt?: string;
  expanded?: boolean;
  error?: string;
};

export function ExpandedContext({ passageId }: { passageId: string }) {
  const [context, setContext] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function expand() {
    if (context || notice) {
      setContext(null);
      setNotice(null);
      return;
    }
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const response = await fetch(appPath(`/api/passages/${encodeURIComponent(passageId)}/context?window=1000`));
      const payload = await response.json() as ContextResponse;
      if (!response.ok || !payload.excerpt) throw new Error(payload.error || "Expanded context is unavailable");
      if (payload.expanded === false) {
        setNotice("This release includes the complete citable passage but no wider source text. Use the scan link for more context.");
        return;
      }
      setContext(payload.excerpt);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Expanded context is unavailable");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className={styles.container}>
      <button type="button" onClick={expand} disabled={loading} aria-expanded={context !== null || notice !== null}>
        {loading ? "Loading context…" : context ? "Hide expanded context" : notice ? "Hide context note" : "Show more context"}
      </button>
      {context && <div className={`passage-text ${styles.context}`}>{context}</div>}
      {notice && <p className={styles.notice}>{notice}</p>}
      {error && <p role="alert" className={styles.error}>{error}</p>}
    </div>
  );
}
