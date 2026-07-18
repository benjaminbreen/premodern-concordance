import Link from "next/link";
import type { ResearchFinding } from "@/contracts/domain";
import styles from "./finding-card.module.css";

function label(value: string) {
  return value.replaceAll("_", " ").toLocaleLowerCase();
}

export function FindingCard({ finding }: { finding: ResearchFinding }) {
  return (
    <article className={styles.card}>
      <header>
        <span>{label(finding.findingType)}</span>
        <h3>{finding.title}</h3>
      </header>
      <p className={styles.summary}>{finding.summary}</p>
      <div className={styles.evidence}>
        {finding.evidence.map((item) => (
          <div key={item.claimId}>
            <small>{label(item.role)} · {item.sourceAuthor ? `${item.sourceAuthor}, ` : ""}{item.publicationYear}</small>
            <blockquote className="passage-text">{item.evidenceText}</blockquote>
            <Link href={`/passage/${item.passageId}`}>{item.sourceTitle} →</Link>
          </div>
        ))}
      </div>
    </article>
  );
}
