import type { Metadata } from "next";
import Link from "next/link";
import { EntryKindBadge } from "@/components/ui/entry-kind";
import { StatusNote } from "@/components/ui/status-note";
import { listEntries } from "@/server/repositories/entries";
import { getReleaseStats } from "@/server/repositories/release";
import { firstQueryValue, type QueryValue } from "@/config/query";
import styles from "./page.module.css";

export const metadata: Metadata = { title: "Entries" };
export const dynamic = "force-dynamic";

export default async function EntriesPage({ searchParams }: { searchParams: Promise<{ offset?: QueryValue }> }) {
  const query = await searchParams;
  const parsedOffset = Number.parseInt(firstQueryValue(query.offset, "0"), 10);
  const offset = Number.isFinite(parsedOffset) ? Math.max(parsedOffset, 0) : 0;
  const pageSize = 50;
  const [entries, stats] = await Promise.all([listEntries(pageSize, offset), getReleaseStats()]);
  return (
    <div className={`shell ${styles.page}`}>
      <header><p className="eyebrow">The concordance</p><h1>Concordance entries</h1><p>Historical terms, their attested forms, and the passages in which they appear.</p></header>
      <div className={styles.list}>
        {entries.map((entry) => (
          <Link href={`/entry/${entry.slug}`} className={styles.row} key={entry.id}>
            <div><EntryKindBadge kind={entry.kind} /><StatusNote status={entry.status} /></div>
            <h2>{entry.preferredLabel}</h2>
            <p>{entry.scopeNote}</p>
            <span>{entry.earliestYear ?? "—"}–{entry.latestYear ?? "—"} · {entry.passageCount} passages</span>
          </Link>
        ))}
      </div>
      {(offset > 0 || offset + entries.length < stats.entryCount) && <nav className={styles.pagination} aria-label="Entry pages">
        {offset > 0 ? <Link href={`/entries?offset=${Math.max(0, offset - pageSize)}`}>← Previous entries</Link> : <span />}
        {offset + entries.length < stats.entryCount && <Link href={`/entries?offset=${offset + pageSize}`}>More entries →</Link>}
      </nav>}
    </div>
  );
}
