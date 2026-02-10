"use client";

import { useState, useRef, useEffect, useMemo } from "react";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useBookContext } from "../BookContext";
import { CAT_BADGE } from "@/lib/colors";
import {
  buildEntityNameIndex,
  buildSlugMap,
  linkifyChildren,
  type ClusterPreview,
} from "@/components/EntityHoverCard";

// ── Types ──────────────────────────────────────────────────────────────

interface EvidenceItem {
  entity_id: string;
  entity_name: string;
  category: string;
  relevance: "direct" | "analogical";
  reasoning: string;
}

interface ConsultMeta {
  book_id: string;
  persona: string;
  entities_retrieved: number;
  entities_in_book: number;
  frameworks_available?: number;
  evidence_used_count?: number;
  evidence_entities: {
    id: string;
    slug: string;
    name: string;
    category: string;
    count: number;
    score: number;
  }[];
}

interface ConsultResult {
  response: string;
  evidence_used: EvidenceItem[];
  confidence: "high" | "moderate" | "low" | "speculative";
  confidence_explanation: string;
  frameworks_applied: string[];
  modern_note: string;
  _meta: ConsultMeta;
}

// ── Book-specific example questions ────────────────────────────────────

const EXAMPLE_QUESTIONS: Record<string, string[]> = {
  english_physician_1652: [
    "How would you treat a persistent cough?",
    "What is the role of Mars in governing herbs?",
    "Why do you distrust the College of Physicians?",
    "How do you explain the cause of fevers?",
  ],
  polyanthea_medicinal: [
    "How do you treat a high fever?",
    "What is the role of bloodletting in your practice?",
    "Tell me about the virtues of bezoar stone.",
    "How do you treat dropsy?",
  ],
  coloquios_da_orta_1563: [
    "What can you tell me about the properties of cinnamon?",
    "How do Indian physicians differ from European ones?",
    "What are the medicinal uses of opium?",
    "Tell me about the drugs of Goa.",
  ],
  historia_medicinal_monardes_1574: [
    "What are the medicinal virtues of tobacco?",
    "Tell me about the properties of sassafras.",
    "How do New World remedies compare to European ones?",
    "What is guaiacum used for?",
  ],
  ricettario_fiorentino_1597: [
    "How do you prepare theriac?",
    "What is the proper way to distill aqua vitae?",
    "Tell me about compound medicines for plague.",
    "What ingredients are most important for an apothecary?",
  ],
  relation_historique_humboldt_vol3_1825: [
    "Describe the geography of the Orinoco region.",
    "What plants did you observe in the tropics?",
    "How do the indigenous peoples use quinine?",
    "Tell me about the volcanoes you studied.",
  ],
  origin_of_species_darwin_1859: [
    "How does natural selection work?",
    "What evidence supports the transmutation of species?",
    "How do you explain the geographic distribution of species?",
    "What role does variation play in evolution?",
  ],
  principles_of_psychology_james_1890: [
    "What is the stream of consciousness?",
    "How do habits form in the brain?",
    "What is the relationship between emotion and bodily sensation?",
    "How does attention work?",
  ],
};

const DEFAULT_QUESTIONS = [
  "What do you consider the most important topic in your work?",
  "How do you approach understanding the natural world?",
  "What authorities do you most rely on?",
  "Tell me about a remedy or concept you find particularly interesting.",
];

// ── Confidence display ─────────────────────────────────────────────────

const CONFIDENCE_CONFIG: Record<
  string,
  { dots: number; label: string; colorClass: string }
> = {
  high: { dots: 4, label: "High", colorClass: "text-emerald-600 dark:text-emerald-400" },
  moderate: { dots: 3, label: "Moderate", colorClass: "text-amber-600 dark:text-amber-400" },
  low: { dots: 2, label: "Low", colorClass: "text-orange-600 dark:text-orange-400" },
  speculative: { dots: 1, label: "Speculative", colorClass: "text-red-600 dark:text-red-400" },
};

// ── Component ──────────────────────────────────────────────────────────

export default function ConsultPage() {
  const { bookData } = useBookContext();
  const book = bookData.book;
  const bookId = book.id;

  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ConsultResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showAllEvidence, setShowAllEvidence] = useState(false);
  const [history, setHistory] = useState<
    { question: string; result: ConsultResult }[]
  >([]);

  const inputRef = useRef<HTMLTextAreaElement>(null);
  const resultRef = useRef<HTMLDivElement>(null);

  // Load concordance clusters for entity hover cards
  const [concordanceClusters, setConcordanceClusters] = useState<
    { id: number; canonical_name: string; category: string; subcategory: string; book_count: number; total_mentions: number; members: { entity_id: string; book_id: string; name: string; category: string; subcategory: string; count: number; variants: string[]; contexts: string[] }[]; ground_truth?: { modern_name: string; confidence: "high" | "medium" | "low"; type: string; linnaean?: string; description?: string; wikidata_description?: string; semantic_gloss?: string } }[]
  >([]);

  useEffect(() => {
    fetch("/data/concordance.json")
      .then((r) => r.json())
      .then((d) => {
        if (d?.clusters) setConcordanceClusters(d.clusters);
      })
      .catch(() => {});
  }, []);

  const nameIndex = useMemo(() => {
    if (concordanceClusters.length === 0) return new Map<string, ClusterPreview>();
    const slugMap = buildSlugMap(concordanceClusters);
    return buildEntityNameIndex(concordanceClusters, slugMap);
  }, [concordanceClusters]);

  const examples = EXAMPLE_QUESTIONS[bookId] || DEFAULT_QUESTIONS;

  // Auto-scroll to result when it arrives
  useEffect(() => {
    if (result && resultRef.current) {
      resultRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [result]);

  async function handleSubmit(q?: string) {
    const text = (q || question).trim();
    if (!text || loading) return;

    setLoading(true);
    setError(null);
    setResult(null);
    setShowAllEvidence(false);

    try {
      const res = await fetch("/api/consult", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ book_id: bookId, question: text }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.error || "Consultation failed");
      }

      const data: ConsultResult = await res.json();
      setResult(data);
      // Save to history
      setHistory((prev) => [...prev, { question: text, result: data }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }

  const confidence = result
    ? CONFIDENCE_CONFIG[result.confidence] || CONFIDENCE_CONFIG.moderate
    : null;

  const rankedEvidence = result
    ? [...result._meta.evidence_entities].sort((a, b) => {
        const aUsed = result.evidence_used.some((eu) => eu.entity_id === a.id);
        const bUsed = result.evidence_used.some((eu) => eu.entity_id === b.id);
        return Number(bUsed) - Number(aUsed) || b.score - a.score || b.count - a.count;
      })
    : [];
  const visibleEvidence = showAllEvidence
    ? rankedEvidence
    : rankedEvidence.slice(0, 6);

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">
          Consult {book.author.split(" ").pop()}
        </h1>
        <p className="mt-1 text-[var(--muted)] text-sm max-w-2xl">
          Ask a question and receive an answer grounded in the epistemological
          framework and entity data of{" "}
          <span className="italic">{book.title}</span> ({book.year}). Responses
          are generated in the voice of {book.author}, drawing only on knowledge
          available in their era and text.
        </p>
      </div>

      {/* Input area */}
      <div className="border border-[var(--border)] rounded-lg p-4 bg-[var(--background)]">
        <div className="flex gap-3">
          <div className="flex-1">
            <textarea
              ref={inputRef}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={`Ask ${book.author.split(" ").pop()} a question...`}
              className="w-full resize-none bg-transparent text-[var(--foreground)] placeholder:text-[var(--muted)] focus:outline-none text-base leading-relaxed"
              rows={2}
              maxLength={500}
              disabled={loading}
            />
          </div>
          <button
            onClick={() => handleSubmit()}
            disabled={loading || !question.trim()}
            className="self-end px-5 py-2.5 rounded-md bg-[var(--foreground)] text-[var(--background)] font-medium text-sm disabled:opacity-40 hover:opacity-90 transition-opacity shrink-0"
          >
            {loading ? "Consulting..." : "Ask"}
          </button>
        </div>

        {/* Example questions */}
        {!result && !loading && (
          <div className="mt-3 pt-3 border-t border-[var(--border)]">
            <p className="text-xs text-[var(--muted)] mb-2">
              Example questions:
            </p>
            <div className="flex flex-wrap gap-2">
              {examples.map((q) => (
                <button
                  key={q}
                  onClick={() => {
                    setQuestion(q);
                    handleSubmit(q);
                  }}
                  className="text-xs px-3 py-1.5 rounded-full border border-[var(--border)] text-[var(--muted)] hover:text-[var(--foreground)] hover:border-[var(--foreground)] transition-colors"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Loading state */}
      {loading && (
        <div className="border border-[var(--border)] rounded-lg p-8 text-center">
          <div className="inline-flex items-center gap-3 text-[var(--muted)]">
            <svg
              className="animate-spin h-5 w-5"
              viewBox="0 0 24 24"
              fill="none"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
              />
            </svg>
            <span className="text-sm italic">
              {book.author.split(" ").pop()} is consulting their writings...
            </span>
          </div>
        </div>
      )}

      {/* Error state */}
      {error && (
        <div className="border border-red-300 dark:border-red-800 rounded-lg p-4 bg-red-50 dark:bg-red-950/30">
          <p className="text-sm text-red-700 dark:text-red-400">{error}</p>
        </div>
      )}

      {/* Response */}
      {result && (
        <div ref={resultRef} className="space-y-5">
          {/* Main response */}
          <div className="border border-[var(--border)] rounded-lg overflow-hidden">
            <div className="px-5 py-3 border-b border-[var(--border)] bg-[var(--background)] flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold">
                  {result._meta.persona}
                </span>
              </div>
              {confidence && (
                <div
                  className={`flex items-center gap-1.5 text-xs ${confidence.colorClass}`}
                >
                  <span className="flex gap-0.5">
                    {[1, 2, 3, 4].map((i) => (
                      <span
                        key={i}
                        className={`inline-block w-1.5 h-1.5 rounded-full ${
                          i <= confidence.dots
                            ? "bg-current"
                            : "bg-current opacity-20"
                        }`}
                      />
                    ))}
                  </span>
                  <span>{confidence.label} confidence</span>
                </div>
              )}
            </div>
            <div className="px-5 py-5">
              <div className="max-w-none text-[1.02rem] leading-8 text-[var(--foreground)]">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    h2: ({ children }) => (
                      <h2 className="text-xl font-bold mt-6 mb-3 tracking-tight">
                        {nameIndex.size > 0 ? linkifyChildren(children, nameIndex) : children}
                      </h2>
                    ),
                    h3: ({ children }) => (
                      <h3 className="text-lg font-semibold mt-5 mb-2 tracking-tight">
                        {nameIndex.size > 0 ? linkifyChildren(children, nameIndex) : children}
                      </h3>
                    ),
                    p: ({ children }) => (
                      <p className="mb-4 leading-8">
                        {nameIndex.size > 0 ? linkifyChildren(children, nameIndex) : children}
                      </p>
                    ),
                    ul: ({ children }) => (
                      <ul className="mb-4 list-disc pl-6 space-y-1">{children}</ul>
                    ),
                    ol: ({ children }) => (
                      <ol className="mb-4 list-decimal pl-6 space-y-1">{children}</ol>
                    ),
                    li: ({ children }) => (
                      <li>
                        {nameIndex.size > 0 ? linkifyChildren(children, nameIndex) : children}
                      </li>
                    ),
                    table: ({ children }) => (
                      <div className="my-5 overflow-x-auto">
                        <table className="min-w-full border border-[var(--border)] text-sm">
                          {children}
                        </table>
                      </div>
                    ),
                    thead: ({ children }) => (
                      <thead className="bg-[var(--card)]">{children}</thead>
                    ),
                    th: ({ children }) => (
                      <th className="text-left px-3 py-2 border-b border-[var(--border)] font-semibold">
                        {children}
                      </th>
                    ),
                    td: ({ children }) => (
                      <td className="px-3 py-2 border-b border-[var(--border)] align-top">
                        {nameIndex.size > 0 ? linkifyChildren(children, nameIndex) : children}
                      </td>
                    ),
                    blockquote: ({ children }) => (
                      <blockquote className="border-l-2 border-[var(--border)] pl-4 italic text-[var(--muted)] my-4">
                        {nameIndex.size > 0 ? linkifyChildren(children, nameIndex) : children}
                      </blockquote>
                    ),
                    code: ({ children }) => (
                      <code className="px-1.5 py-0.5 rounded bg-[var(--card)] text-sm">
                        {children}
                      </code>
                    ),
                  }}
                >
                  {result.response}
                </ReactMarkdown>
              </div>
              {result.confidence_explanation && (
                <p className="mt-3 text-xs text-[var(--muted)] italic">
                  {result.confidence_explanation}
                </p>
              )}
            </div>
          </div>

          {/* Frameworks applied */}
          {result.frameworks_applied?.length > 0 && (
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs text-[var(--muted)] font-medium">
                Frameworks applied:
              </span>
              {result.frameworks_applied.map((fw) => (
                <span
                  key={fw}
                  className="text-xs px-2.5 py-1 rounded-full border border-[var(--border)] text-[var(--foreground)]"
                >
                  {fw}
                </span>
              ))}
            </div>
          )}

          {/* Evidence panel */}
          {rankedEvidence.length > 0 && (
            <div className="border border-[var(--border)] rounded-lg overflow-hidden">
              <div className="px-5 py-3 border-b border-[var(--border)] bg-[var(--background)]">
                <span className="text-sm font-semibold">
                  Evidence from the text
                </span>
                <span className="text-xs text-[var(--muted)] ml-2">
                  Showing {visibleEvidence.length} of {rankedEvidence.length} retrieved entities
                </span>
              </div>
              <div className="divide-y divide-[var(--border)]">
                {visibleEvidence.map((ent) => {
                  const evidenceEntry = result.evidence_used.find(
                    (eu) =>
                      eu.entity_id === ent.id ||
                      eu.entity_name?.toLowerCase() ===
                        ent.name.toLowerCase()
                  );
                  const badgeClass =
                    CAT_BADGE[ent.category as keyof typeof CAT_BADGE] ||
                    "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200";

                  return (
                    <div key={ent.id} className="px-5 py-3 flex items-start gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-0.5">
                          <Link
                            href={`/books/${bookId}/entity/${ent.id}`}
                            className="text-sm font-medium hover:underline"
                          >
                            {ent.name}
                          </Link>
                          <span
                            className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${badgeClass}`}
                          >
                            {ent.category}
                          </span>
                          {evidenceEntry && (
                            <span
                              className={`text-[10px] px-1.5 py-0.5 rounded ${
                                evidenceEntry.relevance === "direct"
                                  ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400"
                                  : "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400"
                              }`}
                            >
                              {evidenceEntry.relevance}
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-[var(--muted)]">
                          {ent.count} mentions
                          {evidenceEntry?.reasoning &&
                            ` · ${evidenceEntry.reasoning}`}
                        </p>
                      </div>
                      <Link
                        href={`/books/${bookId}/entity/${ent.id}`}
                        className="text-xs text-[var(--muted)] hover:text-[var(--foreground)] shrink-0"
                      >
                        View &rarr;
                      </Link>
                    </div>
                  );
                })}
              </div>
              {rankedEvidence.length > 6 && (
                <div className="px-5 py-3 border-t border-[var(--border)] bg-[var(--background)]">
                  <button
                    onClick={() => setShowAllEvidence((v) => !v)}
                    className="text-xs text-[var(--muted)] hover:text-[var(--foreground)] transition-colors"
                  >
                    {showAllEvidence
                      ? "Show fewer evidence items"
                      : `Show all evidence items (${rankedEvidence.length})`}
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Modern context note */}
          {result.modern_note && (
            <div className="border border-[var(--border)] rounded-lg px-5 py-4 bg-blue-50/50 dark:bg-blue-950/20">
              <div className="flex items-start gap-2">
                <span className="text-sm mt-0.5 shrink-0">*</span>
                <div>
                  <p className="text-xs font-medium text-[var(--foreground)] mb-1">
                    Modern context
                  </p>
                  <p className="text-xs text-[var(--muted)] leading-relaxed">
                    {result.modern_note}
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* How this answer was built */}
          <details className="text-xs text-[var(--muted)]">
            <summary className="cursor-pointer hover:text-[var(--foreground)] transition-colors">
              How this answer was built
            </summary>
            <div className="mt-2 pl-4 space-y-1">
              <p>
                Question matched against {result._meta.entities_in_book.toLocaleString()}{" "}
                entities in this book via keyword retrieval.
              </p>
              <p>
                {result._meta.entities_retrieved} relevant entities selected as
                evidence context.
              </p>
              <p>
                Response synthesized via Gemini 2.5 Flash with epistemological
                persona context ({result._meta.frameworks_available ?? 0} available;{" "}
                {result.frameworks_applied?.length || 0} explicitly applied).
              </p>
              <p>
                Citations validated against retrieved entity set. Confidence
                assessed by the model based on evidence coverage.
              </p>
            </div>
          </details>

          {/* Ask another question */}
          <div className="pt-2">
            <button
              onClick={() => {
                setResult(null);
                setError(null);
                setQuestion("");
                inputRef.current?.focus();
              }}
              className="text-sm text-[var(--muted)] hover:text-[var(--foreground)] transition-colors"
            >
              Ask another question &rarr;
            </button>
          </div>
        </div>
      )}

      {/* Conversation history */}
      {history.length > 1 && !loading && result && (
        <div className="border-t border-[var(--border)] pt-6">
          <h3 className="text-xs font-medium text-[var(--muted)] mb-3 uppercase tracking-wider">
            Previous questions in this session
          </h3>
          <div className="space-y-2">
            {history.slice(0, -1).map((entry, i) => (
              <button
                key={i}
                onClick={() => {
                  setResult(entry.result);
                  setQuestion(entry.question);
                }}
                className="block text-left w-full text-sm text-[var(--muted)] hover:text-[var(--foreground)] transition-colors"
              >
                <span className="mr-2 opacity-50">{i + 1}.</span>
                {entry.question}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
