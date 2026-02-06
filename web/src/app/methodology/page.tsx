"use client";

import { useState, useEffect, useRef } from "react";

// ── Section definitions for the floating nav ──────────────────────────

const SECTIONS = [
  { id: "overview", label: "Overview" },
  { id: "corpus", label: "Corpus" },
  { id: "pipeline", label: "Pipeline" },
  { id: "extraction", label: "1. Entity Extraction" },
  { id: "deduplication", label: "2. Deduplication" },
  { id: "finetuning", label: "3. Model Fine-Tuning" },
  { id: "matching", label: "4. Cross-Book Matching" },
  { id: "clustering", label: "5. Concordance Clustering" },
  { id: "verification", label: "6. LLM Verification" },
  { id: "enrichment", label: "7. Enrichment" },
  { id: "search-index", label: "8. Search Index" },
  { id: "edge-cases", label: "Edge Cases" },
  { id: "models", label: "Models & APIs" },
];

// ── Inset box components ──────────────────────────────────────────────

function InfoBox({ children }: { children: React.ReactNode }) {
  return (
    <div className="my-6 border-l-2 border-[var(--accent)] bg-[var(--accent)]/5 rounded-r-lg px-5 py-4 text-sm leading-relaxed">
      {children}
    </div>
  );
}

function ParamTable({ rows }: { rows: [string, string, string][] }) {
  return (
    <div className="my-5 overflow-x-auto">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="border-b border-[var(--border)]">
            <th className="text-left py-2 pr-4 text-xs uppercase tracking-widest text-[var(--muted)] font-medium">Parameter</th>
            <th className="text-left py-2 pr-4 text-xs uppercase tracking-widest text-[var(--muted)] font-medium">Value</th>
            <th className="text-left py-2 text-xs uppercase tracking-widest text-[var(--muted)] font-medium">Notes</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([param, value, note], i) => (
            <tr key={i} className="border-b border-[var(--border)]/50">
              <td className="py-2.5 pr-4 font-mono text-xs">{param}</td>
              <td className="py-2.5 pr-4 font-semibold">{value}</td>
              <td className="py-2.5 text-[var(--muted)]">{note}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CodeBlock({ children }: { children: string }) {
  return (
    <pre className="my-4 px-4 py-3 rounded-lg bg-[var(--foreground)]/5 border border-[var(--border)] overflow-x-auto text-xs font-mono leading-relaxed">
      {children}
    </pre>
  );
}

function StepNumber({ n }: { n: number }) {
  return (
    <span className="inline-flex items-center justify-center w-7 h-7 rounded-full bg-[var(--foreground)] text-[var(--background)] text-xs font-bold mr-3 flex-shrink-0">
      {n}
    </span>
  );
}

// ── Main page ─────────────────────────────────────────────────────────

export default function MethodologyPage() {
  const [activeSection, setActiveSection] = useState("overview");
  const [navCollapsed, setNavCollapsed] = useState(false);
  const observerRef = useRef<IntersectionObserver | null>(null);

  // Intersection observer for active section tracking
  useEffect(() => {
    const targets = SECTIONS.map((s) => document.getElementById(s.id)).filter(Boolean) as HTMLElement[];
    if (!targets.length) return;

    observerRef.current = new IntersectionObserver(
      (entries) => {
        // Find the topmost visible section
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible.length > 0) {
          setActiveSection(visible[0].target.id);
        }
      },
      { rootMargin: "-80px 0px -60% 0px", threshold: 0 }
    );

    targets.forEach((t) => observerRef.current?.observe(t));
    return () => observerRef.current?.disconnect();
  }, []);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
      <div className="grid grid-cols-1 lg:grid-cols-[220px_1fr] gap-12 lg:gap-16">

        {/* ── Floating navigation ─────────────────────────── */}
        <aside className="hidden lg:block">
          <nav className="sticky top-24">
            <h2 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-4">
              Contents
            </h2>
            <ul className="space-y-1">
              {SECTIONS.map((s) => {
                const isStep = s.label.match(/^\d\./);
                return (
                  <li key={s.id}>
                    <a
                      href={`#${s.id}`}
                      onClick={(e) => {
                        e.preventDefault();
                        document.getElementById(s.id)?.scrollIntoView({ behavior: "smooth" });
                      }}
                      className={`block py-1 text-sm transition-colors duration-150 ${
                        isStep ? "pl-4" : ""
                      } ${
                        activeSection === s.id
                          ? "text-[var(--foreground)] font-medium"
                          : "text-[var(--muted)] hover:text-[var(--foreground)]"
                      }`}
                    >
                      {activeSection === s.id && (
                        <span className="inline-block w-1.5 h-1.5 rounded-full bg-[var(--accent)] mr-2 -ml-3.5 align-middle" />
                      )}
                      {s.label}
                    </a>
                  </li>
                );
              })}
            </ul>
          </nav>
        </aside>

        {/* ── Main content ────────────────────────────────── */}
        <article className="min-w-0">

          {/* OVERVIEW */}
          <section id="overview" className="mb-20 animate-fade-up delay-0">
            <h1 className="text-3xl md:text-4xl font-bold tracking-tight mb-3">
              Methodology
            </h1>
            <p className="text-lg text-[var(--muted)] leading-relaxed max-w-2xl mb-8">
              How the Premodern Concordance extracts, matches, verifies, and enriches
              named entities across multilingual early modern texts.
            </p>

            <div className="border-t border-[var(--border)]" />

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-8 py-8">
              <div>
                <h3 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-2">
                  Approach
                </h3>
                <p className="text-sm leading-relaxed">
                  A hybrid pipeline combining large language models for entity extraction
                  and verification with fine-tuned multilingual embeddings for cross-lingual
                  matching. Each step is designed to be incremental, auditable, and resumable.
                </p>
              </div>
              <div>
                <h3 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-2">
                  Scale
                </h3>
                <p className="text-sm leading-relaxed">
                  Six texts spanning 1552&ndash;1825 in five languages (English, Portuguese,
                  Spanish, French, Italian), producing approximately 1,400 concordance clusters
                  from thousands of extracted entities with over 40,000 total mentions.
                </p>
              </div>
              <div>
                <h3 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-2">
                  Challenges
                </h3>
                <p className="text-sm leading-relaxed">
                  Early modern texts present unstable orthography, OCR artifacts, cross-lingual
                  naming conventions (Galeno/Galen/Galien), lost long-s characters, and
                  ambiguous referents that resist standard NER approaches.
                </p>
              </div>
            </div>

            <div className="border-t border-[var(--border)]" />
          </section>

          {/* CORPUS */}
          <section id="corpus" className="mb-20 animate-fade-up delay-1">
            <h2 className="text-2xl font-bold tracking-tight mb-6">Corpus</h2>
            <p className="text-[var(--muted)] leading-relaxed mb-6 max-w-2xl">
              The concordance currently draws on six early modern texts concerned with
              natural knowledge &mdash; materia medica, botany, pharmacy, natural history,
              and exploration. These were selected for their overlapping subject matter
              and linguistic diversity.
            </p>

            <div className="grid grid-cols-1 gap-px bg-[var(--border)] border border-[var(--border)] rounded-lg overflow-hidden">
              {[
                { title: "Col\u00f3quios dos Simples e Drogas da \u00CDndia", author: "Garc\u00eda de Orta", year: 1563, lang: "Portuguese", desc: "A pioneering pharmacological dialogue cataloguing the drugs, spices, and medicinal plants of India based on Orta\u2019s decades of firsthand observation in Goa." },
                { title: "Historia Medicinal de las cosas que se traen de nuestras Indias Occidentales", author: "Nicol\u00e1s Monardes", year: 1574, lang: "Spanish", desc: "A catalogue of New World medicinal substances\u2014tobacco, sassafras, guaiacum, bezoardstones\u2014written by a Seville physician who never crossed the Atlantic." },
                { title: "Ricettario Fiorentino", author: "Collegio Medico di Firenze", year: 1597, lang: "Italian", desc: "The official pharmacopoeia of Florence, standardising compound drug recipes and ingredient terminology for the city\u2019s apothecaries." },
                { title: "The English Physitian", author: "Nicholas Culpeper", year: 1652, lang: "English", desc: "A vernacular herbal linking plants to astrological governance and Galenic humoral medicine, written to make pharmaceutical knowledge accessible beyond Latin." },
                { title: "Polyanthea Medicinal", author: "Jo\u00e3o Curvo Semedo", year: 1741, lang: "Portuguese", desc: "An encyclopaedic medical compendium blending Galenic, chemical, and empirical approaches, reflecting the eclectic pharmacy of early eighteenth-century Portugal." },
                { title: "Relation historique du voyage, Tome III", author: "Alexander von Humboldt", year: 1825, lang: "French", desc: "The third volume of Humboldt\u2019s narrative of his American expedition, rich with observations on geography, botany, indigenous knowledge, and natural phenomena." },
              ].map((book) => (
                <div key={book.year} className="bg-[var(--card)] p-5 grid grid-cols-[1fr_auto] gap-4 items-start">
                  <div>
                    <h3 className="font-semibold mb-0.5" style={{ fontFamily: "'EB Garamond', serif" }}>
                      {book.title}
                    </h3>
                    <p className="text-sm text-[var(--muted)] mb-2">
                      {book.author}, {book.year} &middot; {book.lang}
                    </p>
                    <p className="text-sm text-[var(--muted)] leading-relaxed">{book.desc}</p>
                  </div>
                  <span className="text-3xl font-bold tracking-tight text-[var(--border)] tabular-nums">
                    {book.year}
                  </span>
                </div>
              ))}
            </div>
          </section>

          {/* PIPELINE OVERVIEW */}
          <section id="pipeline" className="mb-20 animate-fade-up delay-2">
            <h2 className="text-2xl font-bold tracking-tight mb-6">Pipeline Overview</h2>
            <p className="text-[var(--muted)] leading-relaxed mb-8 max-w-2xl">
              The concordance is built through an eight-stage pipeline. Each stage is a
              standalone Python script that reads from and writes to JSON, making the
              process fully auditable and individually re-runnable.
            </p>

            {/* Visual pipeline */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-px bg-[var(--border)] border border-[var(--border)] rounded-lg overflow-hidden mb-8">
              {[
                { n: 1, title: "Extract", desc: "LLM-based NER on chunked source text", model: "Gemini" },
                { n: 2, title: "Deduplicate", desc: "Within-book entity merging via embeddings", model: "BGE-M3" },
                { n: 3, title: "Fine-Tune", desc: "Contrastive learning on historical name pairs", model: "BGE-M3" },
                { n: 4, title: "Match", desc: "Pairwise cross-book entity matching", model: "BGE-M3" },
                { n: 5, title: "Cluster", desc: "Connected-component concordance groups", model: "BGE-M3" },
                { n: 6, title: "Verify", desc: "LLM review of suspicious clusters", model: "Gemini" },
                { n: 7, title: "Enrich", desc: "Ground truth identification + Wikidata", model: "Gemini" },
                { n: 8, title: "Index", desc: "Semantic search embeddings for the web", model: "OpenAI" },
              ].map((step) => (
                <a
                  key={step.n}
                  href={`#${["extraction", "deduplication", "finetuning", "matching", "clustering", "verification", "enrichment", "search-index"][step.n - 1]}`}
                  onClick={(e) => {
                    e.preventDefault();
                    document.getElementById(
                      ["extraction", "deduplication", "finetuning", "matching", "clustering", "verification", "enrichment", "search-index"][step.n - 1]
                    )?.scrollIntoView({ behavior: "smooth" });
                  }}
                  className="bg-[var(--card)] p-4 hover:bg-[var(--border)]/30 transition-colors block"
                >
                  <div className="flex items-center gap-2 mb-2">
                    <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-[var(--foreground)] text-[var(--background)] text-xs font-bold flex-shrink-0">
                      {step.n}
                    </span>
                    <span className="font-semibold text-sm">{step.title}</span>
                  </div>
                  <p className="text-xs text-[var(--muted)] leading-relaxed">{step.desc}</p>
                  <span className="inline-block mt-2 text-[10px] font-mono px-1.5 py-0.5 rounded bg-[var(--foreground)]/5 text-[var(--muted)]">
                    {step.model}
                  </span>
                </a>
              ))}
            </div>

            <InfoBox>
              <strong>Incremental design.</strong> Every script supports checkpointing and
              can skip already-processed items on re-run. This means a single failed API call
              doesn&rsquo;t require restarting the entire pipeline &mdash; just re-run the script
              and it picks up where it left off.
            </InfoBox>
          </section>

          {/* ── STEP 1: EXTRACTION ────────────────────────── */}
          <section id="extraction" className="mb-20">
            <div className="flex items-center mb-4">
              <StepNumber n={1} />
              <h2 className="text-2xl font-bold tracking-tight">Entity Extraction</h2>
            </div>
            <p className="text-[var(--muted)] leading-relaxed mb-6 max-w-2xl">
              Each source text is chunked and passed through a large language model
              for structured named entity recognition. The LLM identifies entities and
              classifies them into a controlled taxonomy of eight categories and
              thirty-eight subcategories.
            </p>

            <h3 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-3 mt-8">
              Chunking strategy
            </h3>
            <p className="text-sm leading-relaxed mb-4 max-w-2xl">
              Source texts are split into 2,500-character chunks with 200-character overlap.
              Breaks are paragraph-aware: the chunker looks for paragraph boundaries near
              the target split point to avoid cutting mid-sentence. EEBO-specific artifacts
              (page markers, marginal references) and OCR noise are cleaned before chunking.
            </p>

            <h3 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-3 mt-8">
              LLM extraction
            </h3>
            <p className="text-sm leading-relaxed mb-4 max-w-2xl">
              Each chunk is sent to Gemini 2.5 Flash Lite with a structured prompt asking
              for entities in JSON format. The model operates at temperature 0.1 for
              near-deterministic output.
            </p>

            <ParamTable rows={[
              ["Model", "Gemini 2.5 Flash Lite", "Fast, cost-effective structured extraction"],
              ["Temperature", "0.1", "Near-deterministic for consistent NER"],
              ["Chunk size", "2,500 chars", "With 200-char overlap"],
              ["Max output tokens", "4,000", "Per chunk response"],
              ["Rate limit", "0.3s between calls", "Avoids API throttling"],
              ["Checkpoint interval", "Every 25 chunks", "Resumable processing"],
            ]} />

            <h3 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-3 mt-8">
              Entity taxonomy
            </h3>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-px bg-[var(--border)] border border-[var(--border)] rounded-lg overflow-hidden my-4">
              {[
                { cat: "PERSON", subs: "Authority, Scholar, Practitioner, Historical Figure, Mythological" },
                { cat: "PLANT", subs: "Herb, Tree, Root, Fruit, Seed, Flower, Bark, Resin" },
                { cat: "ANIMAL", subs: "Mammal, Bird, Fish, Insect, Reptile, Marine" },
                { cat: "SUBSTANCE", subs: "Mineral, Chemical, Preparation, Metal, Earth, Oil" },
                { cat: "PLACE", subs: "City, Region, Country, Body of Water, Mountain" },
                { cat: "DISEASE", subs: "Fever, Infection, Humoral, Chronic, Acute, Symptom" },
                { cat: "CONCEPT", subs: "Quality, Process, Humoral Concept, Medical Term" },
                { cat: "OBJECT", subs: "Instrument, Vessel, Textile, Tool, Book" },
              ].map((c) => (
                <div key={c.cat} className="bg-[var(--card)] p-3">
                  <span className="text-xs font-bold uppercase tracking-wide">{c.cat}</span>
                  <p className="text-[10px] text-[var(--muted)] mt-1 leading-relaxed">{c.subs}</p>
                </div>
              ))}
            </div>

            <h3 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-3 mt-8">
              Per-entity output
            </h3>
            <p className="text-sm leading-relaxed mb-4 max-w-2xl">
              For each entity the model returns: the surface form name, category, subcategory,
              a short context string (up to 10 words), and variant spellings found in the same chunk.
              After extraction, a separate script locates full-text excerpts (150 characters of
              surrounding context per mention) using regex-based string matching across the source text.
            </p>
          </section>

          {/* ── STEP 2: DEDUPLICATION ────────────────────── */}
          <section id="deduplication" className="mb-20">
            <div className="flex items-center mb-4">
              <StepNumber n={2} />
              <h2 className="text-2xl font-bold tracking-tight">Within-Book Deduplication</h2>
            </div>
            <p className="text-[var(--muted)] leading-relaxed mb-6 max-w-2xl">
              LLM extraction produces many duplicate or near-duplicate entities within a
              single text (e.g. &ldquo;Galeno,&rdquo; &ldquo;galeno,&rdquo;
              &ldquo;GALENO&rdquo;). These are merged using embedding similarity and
              graph-based clustering.
            </p>

            <h3 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-3 mt-8">
              Process
            </h3>
            <ol className="text-sm leading-relaxed space-y-2 max-w-2xl mb-6 list-decimal list-inside">
              <li>Embed all entities within a book using the fine-tuned BGE-M3 model with category context appended to each name</li>
              <li>Compute pairwise cosine similarity between all entity embeddings</li>
              <li>Build a graph where edges connect entities above the merge threshold</li>
              <li>Find connected components via BFS &mdash; each component becomes a merged entity</li>
              <li>Validate each component: check that every member has sufficient similarity to the primary entity (highest-count member)</li>
            </ol>

            <ParamTable rows={[
              ["Merge threshold", "0.88", "General entities"],
              ["Person threshold", "0.85", "Lower for person name variants"],
              ["String similarity boost", "\u22120.05", "If string similarity > 0.5"],
              ["Minimum string similarity", "0.3", "Hard floor to prevent false merges"],
            ]} />

            <InfoBox>
              <strong>Safety checks.</strong> Short words (June/July, Body/Bones) receive
              extra scrutiny via edit-distance guards. For PERSON entities, a surname
              compatibility check prevents merging &ldquo;Duarte Barbosa&rdquo; with
              &ldquo;Duarte Pacheco&rdquo; just because both share a first name.
            </InfoBox>
          </section>

          {/* ── STEP 3: FINE-TUNING ──────────────────────── */}
          <section id="finetuning" className="mb-20">
            <div className="flex items-center mb-4">
              <StepNumber n={3} />
              <h2 className="text-2xl font-bold tracking-tight">Model Fine-Tuning</h2>
            </div>
            <p className="text-[var(--muted)] leading-relaxed mb-6 max-w-2xl">
              Off-the-shelf multilingual embeddings struggle with early modern naming
              conventions. We fine-tune BAAI/bge-m3 on curated pairs of historically
              equivalent names using contrastive learning.
            </p>

            <h3 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-3 mt-8">
              Training data
            </h3>
            <p className="text-sm leading-relaxed mb-4 max-w-2xl">
              Approximately 500 hand-verified pairs of cross-lingual entity equivalences
              drawn from the corpus &mdash; Latin scholarly names and their vernacular
              forms (Riverius/Lazzaro Riviera, Sylvius/Giacomo Silvio), plant names across
              languages (canela/cannelle/cinnamon), and spelling variants (e&#x17F;tomago/estomago).
            </p>

            <ParamTable rows={[
              ["Base model", "BAAI/bge-m3", "State-of-the-art multilingual embeddings"],
              ["Loss function", "MultipleNegativesRankingLoss", "Contrastive learning"],
              ["Epochs", "3", ""],
              ["Batch size", "16", "With hard negatives from same category"],
              ["Warmup steps", "100", ""],
            ]} />

            <h3 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-3 mt-8">
              Impact
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-px bg-[var(--border)] border border-[var(--border)] rounded-lg overflow-hidden my-4">
              <div className="bg-[var(--card)] p-4 text-center">
                <span className="text-2xl font-bold">26.7%</span>
                <p className="text-xs text-[var(--muted)] mt-1">Base BGE-M3 pairs &ge; 0.8</p>
              </div>
              <div className="bg-[var(--card)] p-4 text-center">
                <span className="text-2xl font-bold text-[var(--accent)]">91.1%</span>
                <p className="text-xs text-[var(--muted)] mt-1">Fine-tuned pairs &ge; 0.8</p>
              </div>
              <div className="bg-[var(--card)] p-4 text-center">
                <span className="text-2xl font-bold">+64.4%</span>
                <p className="text-xs text-[var(--muted)] mt-1">Improvement</p>
              </div>
            </div>

            <InfoBox>
              <strong>Key insight.</strong> The fine-tuned model learns domain-specific
              patterns invisible to general-purpose embeddings: Latin scholarly naming
              conventions (<em>-ius</em> &rarr; <em>-o</em>, <em>-e</em>), cross-linguistic
              botanical terminology, and early modern abbreviation practices. The biggest
              single improvement was +0.66 on the pair &ldquo;Riverius&rdquo; / &ldquo;Lazzaro
              Riviera.&rdquo;
            </InfoBox>
          </section>

          {/* ── STEP 4: CROSS-BOOK MATCHING ──────────────── */}
          <section id="matching" className="mb-20">
            <div className="flex items-center mb-4">
              <StepNumber n={4} />
              <h2 className="text-2xl font-bold tracking-tight">Cross-Book Matching</h2>
            </div>
            <p className="text-[var(--muted)] leading-relaxed mb-6 max-w-2xl">
              With entities deduplicated and the embedding model fine-tuned, every entity
              across all books is embedded and compared pairwise. This is the core operation
              that discovers cross-lingual correspondences.
            </p>

            <h3 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-3 mt-8">
              Matching rules
            </h3>
            <ul className="text-sm leading-relaxed space-y-2 max-w-2xl mb-6 list-disc list-inside">
              <li><strong>Same category only:</strong> PERSON matches PERSON, PLANT matches PLANT &mdash; no cross-category matches</li>
              <li><strong>Subcategory compatibility:</strong> when both entities have valid subcategories, they must match</li>
              <li><strong>One-to-one constraint:</strong> each entity can match at most one entity per book, preventing &ldquo;attractor&rdquo; entities</li>
              <li><strong>String similarity integration:</strong> lexical similarity provides a &plusmn;0.03 bonus/penalty to the embedding score</li>
            </ul>

            <ParamTable rows={[
              ["Auto-accept threshold", "0.85", "Direct match, no further checks"],
              ["Candidate threshold", "0.65", "Requires string/category validation"],
              ["Same-language orthographic", "0.90", "Higher bar for same-language pairs"],
              ["Cross-language same referent", "0.80", "Lower bar for translations"],
              ["Person minimum string sim", "0.35", "Prevents semantically-similar but different people"],
              ["OTHER_CONCEPT minimum", "0.92", "Abstract concepts require higher confidence"],
            ]} />

            <h3 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-3 mt-8">
              Link classification
            </h3>
            <p className="text-sm leading-relaxed mb-4 max-w-2xl">
              Each match is classified into one of five types:
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-px bg-[var(--border)] border border-[var(--border)] rounded-lg overflow-hidden my-4">
              {[
                { type: "orthographic_variant", desc: "Spelling differences within or across languages (e\u017Ftomago / estomago)" },
                { type: "same_referent", desc: "Translation equivalents (canela / cinnamon)" },
                { type: "conceptual_overlap", desc: "Related but not identical concepts" },
                { type: "derivation", desc: "Substance-to-preparation relationships" },
                { type: "contested_identity", desc: "Disputed or uncertain matches" },
              ].map((t) => (
                <div key={t.type} className="bg-[var(--card)] p-3">
                  <span className="text-xs font-mono font-semibold">{t.type}</span>
                  <p className="text-xs text-[var(--muted)] mt-1">{t.desc}</p>
                </div>
              ))}
            </div>
          </section>

          {/* ── STEP 5: CLUSTERING ───────────────────────── */}
          <section id="clustering" className="mb-20">
            <div className="flex items-center mb-4">
              <StepNumber n={5} />
              <h2 className="text-2xl font-bold tracking-tight">Concordance Clustering</h2>
            </div>
            <p className="text-[var(--muted)] leading-relaxed mb-6 max-w-2xl">
              Pairwise matches are assembled into concordance clusters using connected
              component analysis. Each cluster represents a single real-world referent
              as it appears across multiple books and languages.
            </p>

            <h3 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-3 mt-8">
              Cluster construction
            </h3>
            <ol className="text-sm leading-relaxed space-y-2 max-w-2xl mb-6 list-decimal list-inside">
              <li>All cross-book matches form a graph; connected components become candidate clusters</li>
              <li>The <em>primary entity</em> (highest mention count) becomes the canonical name</li>
              <li>Every other member must have a direct edge (similarity &ge; 0.84) to the primary &mdash; this prevents chaining artifacts where A&rarr;B&rarr;C creates a false A&rarr;C link</li>
              <li>Substring matching serves as an additional confirmation signal (one name containing the other)</li>
              <li>Members failing validation are removed; clusters shrinking to a single book are dissolved</li>
            </ol>

            <h3 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-3 mt-8">
              Near-duplicate merging
            </h3>
            <p className="text-sm leading-relaxed mb-4 max-w-2xl">
              A post-processing step merges clusters that were split due to subcategory
              noise or minor orthographic differences. This catches splits like
              &ldquo;cheiro&rdquo; (categorized as QUALITY) vs &ldquo;cheyro&rdquo;
              (categorized as OTHER_CONCEPT) that should be one cluster.
            </p>

            <ParamTable rows={[
              ["Levenshtein threshold", "\u2265 0.83", "Normalized similarity between canonical names"],
              ["PLACE threshold", "\u2265 0.85", "Higher bar for places (Africa/Arica problem)"],
              ["Shared books", "\u2265 1 required", "Unless names are identical"],
              ["Same category", "Required", "No cross-category merges"],
            ]} />

            <InfoBox>
              <strong>Why shared books matter.</strong> Requiring at least one shared book
              is the primary safeguard against false merges. Two entities that appear in
              the same text and were <em>not</em> matched during cross-book matching are
              likely genuinely different. This single criterion eliminated false positives
              like cabras/cobras and Africa/Arica.
            </InfoBox>
          </section>

          {/* ── STEP 6: VERIFICATION ─────────────────────── */}
          <section id="verification" className="mb-20">
            <div className="flex items-center mb-4">
              <StepNumber n={6} />
              <h2 className="text-2xl font-bold tracking-tight">LLM Verification</h2>
            </div>
            <p className="text-[var(--muted)] leading-relaxed mb-6 max-w-2xl">
              Embedding-based matching inevitably produces some false positives.
              A verification pass uses an LLM to review &ldquo;suspicious&rdquo; clusters
              and remove members that don&rsquo;t belong.
            </p>

            <h3 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-3 mt-8">
              Suspicion heuristics
            </h3>
            <p className="text-sm leading-relaxed mb-4 max-w-2xl">
              Rather than reviewing all 1,400+ clusters, the system flags those that
              exhibit patterns correlated with false matches:
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-px bg-[var(--border)] border border-[var(--border)] rounded-lg overflow-hidden my-4">
              {[
                { flag: "Multi-entry from same book", desc: "\u2265 3 entities from one source text in a single cluster" },
                { flag: "Low average string similarity", desc: "Mean Levenshtein to canonical name < 0.4" },
                { flag: "Outlier member", desc: "Any member with string similarity < 0.15 to canonical" },
                { flag: "Large cluster", desc: "\u2265 6 members may contain unrelated entities" },
                { flag: "Divergent contexts", desc: "Unique context words > 4\u00d7 context count" },
                { flag: "Short low-similarity names", desc: "Short names (< 5 chars) with similarity < 0.55" },
              ].map((h) => (
                <div key={h.flag} className="bg-[var(--card)] p-3">
                  <span className="text-xs font-semibold">{h.flag}</span>
                  <p className="text-[10px] text-[var(--muted)] mt-1">{h.desc}</p>
                </div>
              ))}
            </div>

            <h3 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-3 mt-8">
              LLM review
            </h3>
            <p className="text-sm leading-relaxed mb-4 max-w-2xl">
              Flagged clusters are sent to Gemini 2.5 Flash Lite, which receives the
              cluster&rsquo;s canonical name, all members with their book of origin and
              context excerpts, and must return a verdict: which members to keep, which
              to remove, and a brief justification. When the LLM identifies sub-groups
              within a cluster, it can split the cluster rather than simply removing members.
            </p>
          </section>

          {/* ── STEP 7: ENRICHMENT ───────────────────────── */}
          <section id="enrichment" className="mb-20">
            <div className="flex items-center mb-4">
              <StepNumber n={7} />
              <h2 className="text-2xl font-bold tracking-tight">Enrichment &amp; Identification</h2>
            </div>
            <p className="text-[var(--muted)] leading-relaxed mb-6 max-w-2xl">
              Verified clusters are enriched with modern identifications using a two-stage
              process: LLM identification followed by Wikidata entity linking.
            </p>

            <h3 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-3 mt-8">
              LLM identification
            </h3>
            <p className="text-sm leading-relaxed mb-4 max-w-2xl">
              Clusters are batched (8 per API call) and sent to Gemini with their canonical
              name, category, top members, and context excerpts. The model returns a structured
              identification including: modern name, Linnaean binomial (for biological entities),
              type classification, temporal data, geographic associations, and a confidence level.
            </p>

            <h3 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-3 mt-8">
              Wikidata linking
            </h3>
            <p className="text-sm leading-relaxed mb-4 max-w-2xl">
              The LLM also suggests a Wikidata search term. This term is used to query the
              Wikidata API, and results are scored by domain relevance:
            </p>
            <div className="grid grid-cols-2 gap-4 my-4 text-sm">
              <div className="border border-[var(--accent)]/30 rounded-lg p-3 bg-[var(--accent)]/5">
                <span className="text-xs uppercase tracking-widest text-[var(--accent)] font-medium block mb-2">Good signals (+1 each)</span>
                <p className="text-xs text-[var(--muted)]">
                  disease, medical, plant, species, physician, explorer, city, mineral, drug, herb
                </p>
              </div>
              <div className="border border-red-500/30 rounded-lg p-3 bg-red-500/5">
                <span className="text-xs uppercase tracking-widest text-red-500 font-medium block mb-2">Bad signals (&minus;5 each)</span>
                <p className="text-xs text-[var(--muted)]">
                  album, song, film, football, rapper, video game, TV series
                </p>
              </div>
            </div>

            <InfoBox>
              <strong>Why domain scoring matters.</strong> &ldquo;Mercury&rdquo; should
              resolve to the alchemical element, not the rock band or the planet.
              &ldquo;Sapa&rdquo; should find the lead-based sweetener, not the modern
              Indonesian city. Heavy negative penalties for pop-culture descriptions keep
              the results anchored in early modern natural knowledge.
            </InfoBox>

            <h3 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-3 mt-8">
              Semantic glosses
            </h3>
            <p className="text-sm leading-relaxed mb-4 max-w-2xl">
              A separate enrichment pass generates a 2&ndash;3 sentence &ldquo;semantic
              gloss&rdquo; for each cluster &mdash; a thematic description grounded in
              how the entity appears in the source texts. Unlike the Wikidata description
              (which is modern and encyclopedic), the semantic gloss captures the early
              modern context: &ldquo;Venomous snakes considered extremely dangerous in
              early modern medicine. Associated with poison, antidotes, theriac
              preparations, and fear.&rdquo;
            </p>

            <h3 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-3 mt-8">
              Enrichment coverage
            </h3>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-px bg-[var(--border)] border border-[var(--border)] rounded-lg overflow-hidden my-4">
              {[
                { val: "99.9%", label: "Clusters identified" },
                { val: "66%", label: "With Wikidata ID" },
                { val: "35%", label: "With Wikipedia URL" },
                { val: "16%", label: "With Linnaean name" },
              ].map((s) => (
                <div key={s.label} className="bg-[var(--card)] p-4 text-center">
                  <span className="text-xl font-bold">{s.val}</span>
                  <p className="text-[10px] text-[var(--muted)] mt-1">{s.label}</p>
                </div>
              ))}
            </div>
          </section>

          {/* ── STEP 8: SEARCH INDEX ─────────────────────── */}
          <section id="search-index" className="mb-20">
            <div className="flex items-center mb-4">
              <StepNumber n={8} />
              <h2 className="text-2xl font-bold tracking-tight">Search Index</h2>
            </div>
            <p className="text-[var(--muted)] leading-relaxed mb-6 max-w-2xl">
              The final stage generates a semantic search index for the web interface.
              Each cluster&rsquo;s identity is compressed into a rich text representation
              and embedded using a fast, general-purpose model.
            </p>

            <h3 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-3 mt-8">
              Embedding text composition
            </h3>
            <p className="text-sm leading-relaxed mb-4 max-w-2xl">
              The embedding text is constructed from multiple fields to maximize
              search recall:
            </p>
            <ol className="text-sm leading-relaxed space-y-1 max-w-2xl mb-6 list-decimal list-inside">
              <li>Canonical name (highest weight)</li>
              <li>Category and subcategory</li>
              <li>Semantic gloss (thematic description)</li>
              <li>Variant names from all members (up to 20)</li>
              <li>Modern name from ground truth</li>
              <li>Linnaean binomial</li>
              <li>Wikidata description</li>
              <li>Botanical family</li>
              <li>Source text context excerpts</li>
            </ol>

            <ParamTable rows={[
              ["Model", "OpenAI text-embedding-3-small", "Fast, affordable semantic search"],
              ["Dimensions", "512", "Matryoshka truncation from 1,536"],
              ["Batch size", "100", "Per API call"],
              ["Index size", "~16 MB", "1,422 entries"],
            ]} />

            <h3 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-3 mt-8">
              Hybrid search
            </h3>
            <p className="text-sm leading-relaxed mb-4 max-w-2xl">
              The web search combines semantic similarity (cosine distance between query
              and cluster embeddings) with lexical matching (Levenshtein distance, substring
              matching, fuzzy matching against canonical names, variant names, modern names,
              and semantic glosses). This ensures that both conceptual queries
              (&ldquo;exotic spice&rdquo;) and exact-name queries (&ldquo;Galeno&rdquo;)
              return good results.
            </p>
          </section>

          {/* ── EDGE CASES ───────────────────────────────── */}
          <section id="edge-cases" className="mb-20">
            <h2 className="text-2xl font-bold tracking-tight mb-6">Edge Cases &amp; Known Challenges</h2>
            <p className="text-[var(--muted)] leading-relaxed mb-8 max-w-2xl">
              Early modern texts present problems that rarely arise in modern NLP.
              Below are the most significant challenges and how the pipeline addresses them.
            </p>

            <div className="space-y-8">
              {/* Edge case 1 */}
              <div className="border border-[var(--border)] rounded-lg overflow-hidden">
                <div className="bg-[var(--foreground)]/5 px-5 py-3 border-b border-[var(--border)]">
                  <h3 className="font-semibold text-sm">Long-s and OCR artifacts</h3>
                </div>
                <div className="px-5 py-4 text-sm leading-relaxed">
                  <p className="mb-3">
                    Many digitized texts preserve the long-s character (&lsquo;&#x17F;&rsquo;), producing
                    surface forms like &ldquo;e&#x17F;tomago&rdquo; for &ldquo;estomago&rdquo; and
                    &ldquo;empla&#x17F;tro&rdquo; for &ldquo;emplastro.&rdquo; OCR sometimes
                    renders long-s as &lsquo;f&rsquo;, creating forms like &ldquo;fangue&rdquo;
                    for &ldquo;sangue&rdquo; (blood).
                  </p>
                  <p className="text-[var(--muted)]">
                    <strong className="text-[var(--foreground)]">Solution:</strong> The fine-tuned
                    embedding model learns to map these variants close together. The
                    near-duplicate merge (Levenshtein &ge; 0.83 + shared books) catches
                    residual splits. The pipeline preserves original surface forms while
                    linking them to normalized clusters.
                  </p>
                </div>
              </div>

              {/* Edge case 2 */}
              <div className="border border-[var(--border)] rounded-lg overflow-hidden">
                <div className="bg-[var(--foreground)]/5 px-5 py-3 border-b border-[var(--border)]">
                  <h3 className="font-semibold text-sm">Cross-lingual scholarly names</h3>
                </div>
                <div className="px-5 py-4 text-sm leading-relaxed">
                  <p className="mb-3">
                    Pre-modern scholars were known by Latinized names that vary dramatically
                    across languages: Avicenna / Avicena / Auicena / Ibn Sina; Galen /
                    Galeno / Galien / Galenus. Standard NER and string matching fail entirely
                    on these.
                  </p>
                  <p className="text-[var(--muted)]">
                    <strong className="text-[var(--foreground)]">Solution:</strong> The PERSON
                    category uses a lower matching threshold (0.80 vs 0.84) and the fine-tuned
                    model specifically learns Latin-to-vernacular name transformations. The
                    training set includes approximately 100 such scholarly name pairs.
                  </p>
                </div>
              </div>

              {/* Edge case 3 */}
              <div className="border border-[var(--border)] rounded-lg overflow-hidden">
                <div className="bg-[var(--foreground)]/5 px-5 py-3 border-b border-[var(--border)]">
                  <h3 className="font-semibold text-sm">Ambiguous referents</h3>
                </div>
                <div className="px-5 py-4 text-sm leading-relaxed">
                  <p className="mb-3">
                    &ldquo;Mercury&rdquo; could mean the planet, the Roman god, or the
                    alchemical element (quicksilver). &ldquo;Sapa&rdquo; could be the
                    ancient lead-sweetened grape must or a South American place name.
                    The same word can have genuinely different referents in different texts.
                  </p>
                  <p className="text-[var(--muted)]">
                    <strong className="text-[var(--foreground)]">Solution:</strong> Category
                    and subcategory constraints prevent cross-domain confusion (Mercury the
                    SUBSTANCE won&rsquo;t merge with Mercury the PLACE). The LLM extraction prompt
                    is tuned for historical database context (1500&ndash;1800), and Wikidata
                    scoring heavily penalizes modern pop-culture matches. When identification
                    is genuinely contested, the enrichment system preserves a &ldquo;note&rdquo;
                    field explaining the ambiguity.
                  </p>
                </div>
              </div>

              {/* Edge case 4 */}
              <div className="border border-[var(--border)] rounded-lg overflow-hidden">
                <div className="bg-[var(--foreground)]/5 px-5 py-3 border-b border-[var(--border)]">
                  <h3 className="font-semibold text-sm">Subcategory-driven cluster splitting</h3>
                </div>
                <div className="px-5 py-4 text-sm leading-relaxed">
                  <p className="mb-3">
                    The embedding model appends subcategory to each entity name before
                    embedding. This means &ldquo;cheiro (quality)&rdquo; and &ldquo;cheyro
                    (other_concept)&rdquo; produce different embeddings even though they refer
                    to the same thing &mdash; smell/scent in Portuguese.
                  </p>
                  <p className="text-[var(--muted)]">
                    <strong className="text-[var(--foreground)]">Solution:</strong> The
                    post-processing near-duplicate merge detects these splits by comparing
                    canonical names with normalized Levenshtein distance while requiring
                    shared books as confirmation. This corrected 29 such splits in the
                    current dataset.
                  </p>
                </div>
              </div>

              {/* Edge case 5 */}
              <div className="border border-[var(--border)] rounded-lg overflow-hidden">
                <div className="bg-[var(--foreground)]/5 px-5 py-3 border-b border-[var(--border)]">
                  <h3 className="font-semibold text-sm">Short similar place names</h3>
                </div>
                <div className="px-5 py-4 text-sm leading-relaxed">
                  <p className="mb-3">
                    Place names like Africa/Arica or Goa/Gao are short, lexically similar,
                    and may appear in the same texts &mdash; but refer to entirely different
                    locations. Standard Levenshtein thresholds would merge them.
                  </p>
                  <p className="text-[var(--muted)]">
                    <strong className="text-[var(--foreground)]">Solution:</strong> The PLACE
                    category receives a +0.02 threshold bump (0.85 effective vs 0.83 for
                    other categories) in the near-duplicate merge. Combined with the shared-books
                    requirement, this prevents all known false place merges while still
                    catching legitimate variants like Mozambique/Mo&ccedil;ambique.
                  </p>
                </div>
              </div>

              {/* Edge case 6 */}
              <div className="border border-[var(--border)] rounded-lg overflow-hidden">
                <div className="bg-[var(--foreground)]/5 px-5 py-3 border-b border-[var(--border)]">
                  <h3 className="font-semibold text-sm">Attractor entities</h3>
                </div>
                <div className="px-5 py-4 text-sm leading-relaxed">
                  <p className="mb-3">
                    Without constraints, very common entities (like &ldquo;water&rdquo; or
                    &ldquo;fever&rdquo;) can attract dozens of only vaguely related
                    entities from other books, creating bloated, incoherent clusters.
                  </p>
                  <p className="text-[var(--muted)]">
                    <strong className="text-[var(--foreground)]">Solution:</strong> The
                    one-to-one matching constraint ensures each entity can match at most
                    one entity per book. Cluster validation then requires every member to
                    have a direct similarity edge to the primary entity &mdash; transitive
                    chains (A&rarr;B&rarr;C without A&rarr;C) are broken.
                  </p>
                </div>
              </div>
            </div>
          </section>

          {/* ── MODELS & APIS ────────────────────────────── */}
          <section id="models" className="mb-20">
            <h2 className="text-2xl font-bold tracking-tight mb-6">Models &amp; APIs</h2>

            <div className="grid grid-cols-1 gap-px bg-[var(--border)] border border-[var(--border)] rounded-lg overflow-hidden">
              {[
                { model: "BAAI/bge-m3 (fine-tuned)", purpose: "Cross-lingual entity matching, deduplication, concordance building", stages: "2, 4, 5", note: "Fine-tuned on ~500 historical name pairs. Open-source, runs locally." },
                { model: "Gemini 2.5 Flash Lite", purpose: "Entity extraction, cluster verification, ground truth identification, semantic glosses", stages: "1, 6, 7", note: "Used for all LLM tasks. Low cost, fast, good at structured output." },
                { model: "OpenAI text-embedding-3-small", purpose: "Semantic search index for the web interface", stages: "8", note: "512-dimensional Matryoshka embeddings. Used only for search, not matching." },
                { model: "Wikidata API", purpose: "Entity linking, descriptions, identifiers", stages: "7", note: "Free API with domain-relevance scoring to avoid modern pop-culture matches." },
                { model: "Wikipedia REST API", purpose: "Thumbnail images, article links", stages: "Web UI", note: "Used at display time for entity detail pages." },
              ].map((m) => (
                <div key={m.model} className="bg-[var(--card)] p-5 grid grid-cols-[1fr_auto] gap-4 items-start">
                  <div>
                    <h3 className="font-semibold text-sm mb-1">{m.model}</h3>
                    <p className="text-sm text-[var(--muted)] mb-1">{m.purpose}</p>
                    <p className="text-xs text-[var(--muted)]">{m.note}</p>
                  </div>
                  <span className="text-xs font-mono px-2 py-1 rounded bg-[var(--foreground)]/5 text-[var(--muted)] whitespace-nowrap">
                    Stages {m.stages}
                  </span>
                </div>
              ))}
            </div>
          </section>

          {/* Bottom spacer */}
          <div className="h-20" />
        </article>
      </div>
    </div>
  );
}
