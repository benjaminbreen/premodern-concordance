import Link from "next/link";
import type { ContextualUsage } from "@/contracts/domain";
import styles from "./usage-card.module.css";

function label(value: string) {
  return value.replaceAll("_", " ").toLocaleLowerCase();
}

export function UsageCard({ usage, entrySlug }: { usage: ContextualUsage; entrySlug: string }) {
  const { passage } = usage;
  const location = passage.printedPage
    ? `p. ${passage.printedPage}`
    : passage.scanLeaf !== null
      ? `scan leaf ${passage.scanLeaf}`
      : null;
  const relation = usage.relationType ? label(usage.relationType) : "same entry";

  return (
    <article className={styles.card}>
      <header className={styles.header}>
        <div>
          <Link href={`/source/${passage.source.id}`}>{passage.source.title}</Link>
          <span>{passage.source.author ? `${passage.source.author}, ` : ""}{passage.source.publicationYear}</span>
        </div>
        <span className={usage.resolution === "RELATED_DISTINCT" ? styles.related : styles.resolution}>
          {relation}
        </span>
      </header>

      {usage.senseGloss && <h3>{usage.senseGloss}</h3>}
      <blockquote className="passage-text">{usage.evidenceText}</blockquote>

      {usage.claims.length > 0 && (
        <div className={styles.claims}>
          {usage.claims.map((claim) => (
            <div key={claim.id}>
              <p>{claim.summary}</p>
              <small>{label(claim.stance)} · {label(claim.evidenceBasis)} · {label(claim.claimType)}</small>
            </div>
          ))}
        </div>
      )}

      <footer>
        <span>{passage.source.languageLabel}{location ? ` · ${location}` : ""}</span>
        <div>
          <Link href={`/passage/${passage.id}?entry=${encodeURIComponent(entrySlug)}`}>Read and cite</Link>
          <a href={passage.scanUrl} target="_blank" rel="noreferrer">Open scan ↗</a>
        </div>
      </footer>
    </article>
  );
}
