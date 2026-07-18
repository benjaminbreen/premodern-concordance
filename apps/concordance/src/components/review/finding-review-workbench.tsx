"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { appPath } from "@/config/app-path";
import type {
  ClaimVerdict,
  EvidenceSupport,
  FailureMode,
  FindingReviewItem,
  ResearchValue,
  SavedFindingReview
} from "@/contracts/review";
import styles from "./finding-review-workbench.module.css";

const evidenceOptions: Array<[EvidenceSupport, string, string]> = [
  ["SUPPORTED", "Supported", "The claims and quotations support the finding as written."],
  ["PARTLY_SUPPORTED", "Partly supported", "The underlying pattern is real but materially overstated or incomplete."],
  ["UNSUPPORTED", "Unsupported", "The linked evidence does not establish the proposed finding."],
  ["UNCLEAR", "Unclear", "The available passages are insufficient for a responsible judgment."]
];

const valueOptions: Array<[ResearchValue, string, string]> = [
  ["FOOTNOTE_WORTHY", "Footnote-worthy", "Potentially usable in historical research with normal source checking."],
  ["PROMISING_LEAD", "Promising lead", "Worth following, but not yet a usable conclusion."],
  ["KNOWN_OR_EXPECTED", "Known or expected", "Accurate enough, but confirms something unsurprising."],
  ["BANAL", "Banal", "Technically present but not historically productive."],
  ["IRRELEVANT", "Irrelevant", "Not useful for this entry or research question."],
  ["UNCLEAR", "Unclear", "Historical value cannot yet be assessed."]
];

const failureOptions: Array<[FailureMode, string]> = [
  ["RETRIEVAL", "Wrong or weak passage retrieval"],
  ["ENTRY_RESOLUTION", "Wrong entry resolution"],
  ["CLAIM_EXTRACTION", "Claim was misread"],
  ["INVALID_COMPARISON", "Comparison does not follow"],
  ["OVERSTATED_SUMMARY", "Summary overstates the evidence"],
  ["MISSING_COUNTEREVIDENCE", "Important counterevidence is missing"],
  ["OCR_OR_PARATEXT_NOISE", "OCR, index, title, or paratext noise"],
  ["DUPLICATE_EVIDENCE", "Duplicate or non-independent evidence"]
];

const claimOptions: Array<[ClaimVerdict, string]> = [
  ["ACCURATE", "Accurate"],
  ["PARTLY_ACCURATE", "Partial"],
  ["INACCURATE", "Inaccurate"],
  ["UNCLEAR", "Unclear"]
];

interface Draft {
  evidenceSupport: EvidenceSupport | null;
  researchValue: ResearchValue | null;
  failureModes: FailureMode[];
  claimVerdicts: Record<string, ClaimVerdict>;
  note: string;
  correctedSummary: string;
}

const emptyDraft: Draft = {
  evidenceSupport: null,
  researchValue: null,
  failureModes: [],
  claimVerdicts: {},
  note: "",
  correctedSummary: ""
};

function draftFromReview(review?: SavedFindingReview): Draft {
  return review ? {
    evidenceSupport: review.evidenceSupport,
    researchValue: review.researchValue,
    failureModes: review.failureModes,
    claimVerdicts: review.claimVerdicts,
    note: review.note,
    correctedSummary: review.correctedSummary
  } : { ...emptyDraft, failureModes: [], claimVerdicts: {} };
}

function label(value: string) {
  return value.replaceAll("_", " ").toLocaleLowerCase();
}

export function FindingReviewWorkbench({
  items,
  initialReviews,
  initialIndex
}: {
  items: FindingReviewItem[];
  initialReviews: SavedFindingReview[];
  initialIndex: number;
}) {
  const [reviews, setReviews] = useState<Record<string, SavedFindingReview>>(
    Object.fromEntries(initialReviews.map((review) => [review.findingId, review]))
  );
  const [index, setIndex] = useState(Math.min(initialIndex, Math.max(0, items.length - 1)));
  const current = items[index];
  const [draft, setDraft] = useState<Draft>(() => draftFromReview(current ? reviews[current.finding.id] : undefined));
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const reviewedCount = Object.keys(reviews).length;
  const assessedCount = Object.values(reviews).filter((review) => review.reviewState === "ASSESSED").length;
  const selectedOriginal = useMemo(
    () => draftFromReview(current ? reviews[current.finding.id] : undefined),
    [current, reviews]
  );
  const dirty = JSON.stringify(draft) !== JSON.stringify(selectedOriginal);

  if (!current) return <p>No candidate findings are available for review.</p>;

  function navigate(nextIndex: number) {
    if (dirty && !window.confirm("Discard the unsaved changes to this assessment?")) return;
    const bounded = Math.min(Math.max(nextIndex, 0), items.length - 1);
    setIndex(bounded);
    setDraft(draftFromReview(reviews[items[bounded].finding.id]));
    setMessage("");
    window.history.replaceState(null, "", `${appPath("/review/findings")}?finding=${items[bounded].finding.id}`);
  }

  function toggleFailure(mode: FailureMode) {
    setDraft((value) => ({
      ...value,
      failureModes: value.failureModes.includes(mode)
        ? value.failureModes.filter((item) => item !== mode)
        : [...value.failureModes, mode]
    }));
  }

  async function save(reviewState: "ASSESSED" | "DEFERRED") {
    if (reviewState === "ASSESSED" && (!draft.evidenceSupport || !draft.researchValue)) {
      setMessage("Choose both an evidence judgment and a research-value judgment.");
      return;
    }
    setSaving(true);
    setMessage("");
    try {
      const response = await fetch(appPath("/review-data/findings"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          findingId: current.finding.id,
          reviewState,
          evidenceSupport: reviewState === "ASSESSED" ? draft.evidenceSupport : null,
          researchValue: reviewState === "ASSESSED" ? draft.researchValue : null,
          failureModes: reviewState === "ASSESSED" ? draft.failureModes : [],
          claimVerdicts: reviewState === "ASSESSED" ? draft.claimVerdicts : {},
          note: draft.note,
          correctedSummary: reviewState === "ASSESSED" ? draft.correctedSummary : ""
        })
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error ?? "The assessment could not be saved");
      const saved = payload.review as SavedFindingReview;
      const nextReviews = { ...reviews, [saved.findingId]: saved };
      setReviews(nextReviews);
      setDraft(draftFromReview(saved));
      setMessage(reviewState === "ASSESSED" ? "Assessment saved." : "Finding deferred.");
      const nextUnreviewed = items.findIndex((item, itemIndex) => itemIndex > index && !nextReviews[item.finding.id]);
      if (nextUnreviewed >= 0) {
        setTimeout(() => {
          setIndex(nextUnreviewed);
          setDraft(draftFromReview(nextReviews[items[nextUnreviewed].finding.id]));
          setMessage("");
          window.history.replaceState(null, "", `${appPath("/review/findings")}?finding=${items[nextUnreviewed].finding.id}`);
        }, 350);
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "The assessment could not be saved");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className={styles.workbench}>
      <aside className={styles.queue}>
        <div className={styles.progress}>
          <strong>{assessedCount} assessed</strong>
          <span>{reviewedCount - assessedCount} deferred · {items.length - reviewedCount} remaining</span>
          <div aria-hidden><span style={{ width: `${items.length ? reviewedCount / items.length * 100 : 0}%` }} /></div>
        </div>
        <a className={styles.export} href={appPath("/review-data/export")}>Export current judgments ↓</a>
        <ol>
          {items.map((item, itemIndex) => {
            const review = reviews[item.finding.id];
            return (
              <li key={item.finding.id}>
                <button
                  type="button"
                  className={itemIndex === index ? styles.currentQueueItem : ""}
                  onClick={() => navigate(itemIndex)}
                >
                  <span>{item.entry.preferredLabel}</span>
                  <strong>{item.finding.title}</strong>
                  <small>{review ? (review.reviewState === "DEFERRED" ? "Deferred" : "Assessed") : "Unreviewed"}</small>
                </button>
              </li>
            );
          })}
        </ol>
      </aside>

      <section className={styles.review} aria-live="polite">
        <header className={styles.findingHeader}>
          <div>
            <span>{index + 1} of {items.length} · {label(current.finding.findingType)}</span>
            <Link href={`/entry/${current.entry.slug}`} target="_blank">{current.entry.preferredLabel} ↗</Link>
          </div>
          <h2>{current.finding.title}</h2>
          <p>{current.finding.summary}</p>
          <small><strong>Entry scope:</strong> {current.entry.scopeNote}</small>
        </header>

        <div className={styles.evidenceList}>
          {current.finding.evidence.map((evidence) => (
            <article key={evidence.claimId}>
              <header>
                <span>{label(evidence.role)} · {evidence.sourceAuthor ? `${evidence.sourceAuthor}, ` : ""}{evidence.publicationYear}</span>
                <div><Link href={`/passage/${evidence.passageId}`} target="_blank">Passage ↗</Link><a href={evidence.scanUrl} target="_blank" rel="noreferrer">Scan ↗</a></div>
              </header>
              <p className={styles.claim}>{evidence.summary}</p>
              <blockquote className="passage-text">{evidence.evidenceText}</blockquote>
              <fieldset className={styles.claimVerdict}>
                <legend>Is this extracted claim faithful to the quotation?</legend>
                {claimOptions.map(([value, text]) => (
                  <label key={value}>
                    <input
                      type="radio"
                      name={`claim-${evidence.claimId}`}
                      checked={draft.claimVerdicts[evidence.claimId] === value}
                      onChange={() => setDraft((state) => ({
                        ...state,
                        claimVerdicts: { ...state.claimVerdicts, [evidence.claimId]: value }
                      }))}
                    />
                    {text}
                  </label>
                ))}
              </fieldset>
            </article>
          ))}
        </div>

        <fieldset className={styles.judgment}>
          <legend>Does the evidence support the finding?</legend>
          <div className={styles.optionGrid}>
            {evidenceOptions.map(([value, title, description]) => (
              <label key={value} className={draft.evidenceSupport === value ? styles.selectedOption : ""}>
                <input type="radio" name="evidence-support" checked={draft.evidenceSupport === value} onChange={() => setDraft((state) => ({ ...state, evidenceSupport: value }))} />
                <strong>{title}</strong><span>{description}</span>
              </label>
            ))}
          </div>
        </fieldset>

        <fieldset className={styles.judgment}>
          <legend>Is it historically useful?</legend>
          <div className={styles.optionGrid}>
            {valueOptions.map(([value, title, description]) => (
              <label key={value} className={draft.researchValue === value ? styles.selectedOption : ""}>
                <input type="radio" name="research-value" checked={draft.researchValue === value} onChange={() => setDraft((state) => ({ ...state, researchValue: value }))} />
                <strong>{title}</strong><span>{description}</span>
              </label>
            ))}
          </div>
        </fieldset>

        <fieldset className={styles.failures}>
          <legend>What failed? <span>Select any that apply.</span></legend>
          <div>
            {failureOptions.map(([value, text]) => (
              <label key={value}><input type="checkbox" checked={draft.failureModes.includes(value)} onChange={() => toggleFailure(value)} />{text}</label>
            ))}
          </div>
        </fieldset>

        <div className={styles.textFields}>
          <label>
            <span>Correction or better summary <small>Optional; useful as a supervised example.</small></span>
            <textarea value={draft.correctedSummary} onChange={(event) => setDraft((state) => ({ ...state, correctedSummary: event.target.value }))} rows={3} />
          </label>
          <label>
            <span>Diagnostic note <small>One concrete sentence is more useful than a long review.</small></span>
            <textarea value={draft.note} onChange={(event) => setDraft((state) => ({ ...state, note: event.target.value }))} rows={4} />
          </label>
        </div>

        <footer className={styles.actions}>
          <button type="button" onClick={() => navigate(index - 1)} disabled={index === 0 || saving}>← Previous</button>
          <div>
            {message && <span className={styles.message}>{message}</span>}
            <button type="button" className={styles.defer} onClick={() => save("DEFERRED")} disabled={saving}>Defer</button>
            <button type="button" className={styles.save} onClick={() => save("ASSESSED")} disabled={saving}>{saving ? "Saving…" : "Save and continue"}</button>
          </div>
        </footer>
      </section>
    </div>
  );
}
