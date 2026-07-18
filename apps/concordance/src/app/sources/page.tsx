import type { Metadata } from "next";
import Link from "next/link";
import { listSources } from "@/server/repositories/sources";
import styles from "./page.module.css";

export const metadata: Metadata = { title: "Sources" };
export const dynamic = "force-dynamic";

export default async function SourcesPage() {
  const sources = await listSources();
  return (
    <div className={`shell ${styles.page}`}>
      <header><p className="eyebrow">The corpus</p><h1>Sources</h1><p>Indexed editions with stable citations, passage mappings, and archival scans.</p></header>
      <div className={styles.list}>{sources.map((source) => <Link href={`/source/${source.id}`} key={source.id}><time>{source.publicationYear}</time><div><h2>{source.title}</h2><p>{source.author ? `${source.author} · ` : ""}{source.languageLabel}</p></div><span>{source.passageCount} indexed passages</span></Link>)}</div>
    </div>
  );
}
