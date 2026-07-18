import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { EntryKindBadge } from "@/components/ui/entry-kind";
import { FindingCard } from "@/components/ui/finding-card";
import { PassageCard } from "@/components/ui/passage-card";
import { StatusNote } from "@/components/ui/status-note";
import { UsageCard } from "@/components/ui/usage-card";
import { getEntryBySlug, getEntryFindings, getEntryPassages, getEntrySenses, getEntryUsages } from "@/server/repositories/entries";
import type { EntryRelation } from "@/contracts/domain";
import { firstQueryValue, type QueryValue } from "@/config/query";
import styles from "./page.module.css";

export const dynamic = "force-dynamic";

function RelationCard({ relation }: { relation: EntryRelation }) {
  const relationship = relation.relationType.replaceAll("_", " ").toLocaleLowerCase();
  return (
    <article className={styles.relationCard}>
      <div className={styles.relationHeading}>
        <small>{relation.direction === "INCOMING" ? `${relation.target.preferredLabel} → this entry` : `This entry → ${relation.target.preferredLabel}`} · {relationship}</small>
        <StatusNote status={relation.status} />
      </div>
      <Link className={styles.relationTarget} href={`/entry/${relation.target.slug}`}>{relation.target.preferredLabel}</Link>
      <p>{relation.rationale}</p>
      {relation.nonClaim && <p className={styles.nonClaim}>{relation.nonClaim}</p>}
      <div className={styles.evidence}><span>Evidence:</span>{relation.evidencePassageIds.map((passageId, index) => <Link key={passageId} href={`/passage/${passageId}`}>passage {index + 1}</Link>)}</div>
    </article>
  );
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const entry = await getEntryBySlug(slug);
  return entry ? { title: entry.preferredLabel, description: entry.scopeNote } : {};
}

export default async function EntryPage({ params, searchParams }: { params: Promise<{ slug: string }>; searchParams: Promise<{ offset?: QueryValue }> }) {
  const { slug } = await params;
  const query = await searchParams;
  const parsedOffset = Number.parseInt(firstQueryValue(query.offset, "0"), 10);
  const offset = Number.isFinite(parsedOffset) ? Math.max(parsedOffset, 0) : 0;
  const pageSize = 10;
  const [entry, passages, usages, senses, findings] = await Promise.all([
    getEntryBySlug(slug),
    getEntryPassages(slug, pageSize, offset),
    getEntryUsages(slug),
    getEntrySenses(slug),
    getEntryFindings(slug)
  ]);
  if (!entry) notFound();
  const precise = entry.relations.filter((relation) => relation.layer === "PRECISE");
  const exploratory = entry.relations.filter((relation) => relation.layer === "EXPLORATORY");
  const directUsages = usages.filter((usage) => usage.resolution === "SAME_ENTRY");
  const relatedUsages = usages.filter((usage) => usage.resolution === "RELATED_DISTINCT");
  return (
    <div className={`shell ${styles.page}`}>
      <header className={styles.header}>
        <div className={styles.badges}><EntryKindBadge kind={entry.kind} /><StatusNote status={entry.status} /></div>
        <h1>{entry.preferredLabel}</h1>
        <p className={styles.scope}>{entry.scopeNote}</p>
        <dl className={styles.stats}>
          <div><dt>Sources</dt><dd>{entry.sourceCount}</dd></div>
          <div><dt>Passages</dt><dd>{entry.passageCount}</dd></div>
          <div><dt>In this corpus</dt><dd>{entry.earliestYear ?? "—"}–{entry.latestYear ?? "—"}</dd></div>
        </dl>
      </header>

      {findings.length > 0 && (
        <section className={styles.findings} aria-labelledby="findings-heading">
          <p className="eyebrow">Candidate findings</p>
          <h2 id="findings-heading">What the corpus suggests</h2>
          <p className={styles.sectionIntro}>Patterns synthesized only from the linked claims below. Each remains a research lead, not a substitute for reading the passages.</p>
          {findings.map((finding) => <FindingCard key={finding.id} finding={finding} />)}
        </section>
      )}

      <section className={styles.terms} aria-labelledby="terms-heading">
        <p className="eyebrow">Names and forms</p>
        <h2 id="terms-heading">Term history</h2>
        <div className={styles.termList}>
          {entry.terms.map((term) => (
            <div key={term.id}><strong>{term.displayForm}</strong><span>{term.relationType.replaceAll("_", " ").toLocaleLowerCase()}</span><StatusNote status={term.status} /></div>
          ))}
        </div>
      </section>

      {senses.length > 0 && (
        <section className={styles.senses} aria-labelledby="senses-heading">
          <p className="eyebrow">Meanings in context</p>
          <h2 id="senses-heading">Senses in this corpus</h2>
          <div className={styles.senseList}>
            {senses.map((sense) => (
              <article key={sense.id}>
                <h3>{sense.label}</h3>
                <p>{sense.definition}</p>
                <small>{sense.usageIds.length} {sense.usageIds.length === 1 ? "passage" : "passages"}</small>
              </article>
            ))}
          </div>
        </section>
      )}

      {precise.length > 0 && <section className={styles.relations}><p className="eyebrow">Precise relationships</p>{precise.map((relation) => <RelationCard key={relation.id} relation={relation} />)}</section>}

      {directUsages.length > 0 && (
        <section className={styles.usages} aria-labelledby="usages-heading">
          <p className="eyebrow">Analyzed source evidence</p>
          <h2 id="usages-heading">Historical usages and claims</h2>
          <p className={styles.sectionIntro}>Distinct local senses and assertions recovered from the corpus. Quotations retain the source OCR and link to the full passage and scan.</p>
          {directUsages.map((usage) => <UsageCard key={usage.id} usage={usage} entrySlug={entry.slug} />)}
        </section>
      )}

      {relatedUsages.length > 0 && (
        <section className={styles.adjacent} aria-labelledby="adjacent-heading">
          <p className="eyebrow">Related, not identical</p>
          <h2 id="adjacent-heading">Adjacent histories</h2>
          <p className={styles.sectionIntro}>Passages worth comparing without treating their subjects as names or senses of this entry.</p>
          {relatedUsages.map((usage) => <UsageCard key={usage.id} usage={usage} entrySlug={entry.slug} />)}
        </section>
      )}

      <section className={styles.passages} aria-labelledby="passages-heading">
        <p className="eyebrow">Primary-source evidence</p>
        <h2 id="passages-heading">Full passages, chronologically</h2>
        {passages.map((passage) => <PassageCard key={passage.id} passage={passage} entrySlug={entry.slug} />)}
        {(offset > 0 || offset + passages.length < entry.passageCount) && <nav className={styles.pagination} aria-label="Passage pages">
          {offset > 0 ? <Link href={`/entry/${entry.slug}?offset=${Math.max(0, offset - pageSize)}`}>← Earlier passages</Link> : <span />}
          {offset + passages.length < entry.passageCount && <Link href={`/entry/${entry.slug}?offset=${offset + pageSize}`}>Later passages →</Link>}
        </nav>}
      </section>

      {exploratory.length > 0 && <section className={styles.exploratory}><p className="eyebrow">Related histories</p><h2>Connections to investigate</h2>{exploratory.map((relation) => <RelationCard key={relation.id} relation={relation} />)}</section>}
    </div>
  );
}
