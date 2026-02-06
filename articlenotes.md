# Article Notes: Synonym Chains and the Limits of Automated Entity Extraction in Early Modern Texts

## Working Title Ideas

- "The Pompholige Problem: Why LLMs Miss the Most Interesting Entities in Historical Texts"
- "Synonym Chains as Hidden Concordances: Recovering Cross-Linguistic Entity Networks from Early Modern Natural Knowledge"
- "From Extraction to Enrichment: A Multi-Layered Approach to Entity Resolution in Multilingual Historical Corpora"

---

## Core Argument

Large language models used for named entity extraction systematically under-extract the most historically valuable category of entity mentions in early modern scientific and medical texts: **explicit synonym chains**, where authors deliberately list equivalent terms across languages, traditions, and nomenclatural systems. These synonym chains are effectively concordance entries embedded in the source texts themselves — precisely the material a cross-linguistic concordance project exists to surface. The irony is that current LLM-based extraction pipelines, which perform salience-based extraction (identifying the 5-10 "most important" entities per passage), are structurally biased against exhaustive extraction of these chains. We propose a multi-layered approach combining targeted second-pass extraction, user-driven annotation, and eventually fine-tuned models trained on the expert-reviewed data these processes generate.

---

## The Pompholige Case Study

### What Happened

In the Ricettario Fiorentino (Florence, 1597), the following passage appears in the entry on Spodio (spodium, a metalite oxide used in pharmacy):

> "fuori, ó il vero Spodio, ò la pompholige o vero la tuzia de gli Speziali preparata. Si è visto venuto da Goa dell'Indie orientali il vero Spodio detto la Tabaxir"

This single sentence contains a **four-way synonym chain**: Spodio = pompholige = tuzia = Tabaxir. The author is explicitly mapping equivalences across:

- **Italian pharmaceutical terminology** (Spodio, tuzia)
- **Greek-derived nomenclature** (pompholige, from Greek πομφόλυξ)
- **Arabic/Indic trade terminology** (Tabaxir, from Sanskrit *tvakkṣīra*)
- **Geographic provenance** ("venuto da Goa dell'Indie orientali")

The entity extraction pipeline (Gemini 2.5 Flash Lite) correctly extracted **Spodio** (9 mentions across the Ricettario) and **Tabaxir** (2 mentions) as standalone entities, which were then assigned to their respective clusters in the concordance. But it **missed "pompholige" entirely** — treating it as part of the descriptive context rather than as a distinct extractable entity.

### Why This Matters

Meanwhile, in two Portuguese texts — Garcia de Orta's Colóquios (1563) and the Polyanthea Medicinal (c. 1700) — the same substance appears as **pompholix** and **pompholigos** respectively, forming their own cluster (id: 899, identified as zinc oxide). The concordance thus contains three separate clusters that the Ricettario passage explicitly connects:

| Cluster | Entity | Books | Modern ID |
|---------|--------|-------|-----------|
| 248 | tabaschir / Tabaxir | Orta, Ricettario | Tabasheer (bamboo concretion) |
| 588 | Spodio / espodio | Ricettario, Polyanthea | Spodium (metalite oxide) |
| 899 | pompholix / pompholigos | Orta, Polyanthea | Zinc oxide |

A historian browsing the concordance can find each of these individually but has no automated way to discover that the Ricettario author considered them equivalent — a historically significant claim, since the identity of Spodio/Tabaxir was actively debated in early modern pharmacy. Was tabaxir (a siliceous concretion from bamboo nodes) truly the same as spodium (a metallic oxide collected from furnace flues)? Garcia de Orta argued they were different; the Ricettario conflates them; Semedo's Polyanthea treats them as related but distinct. This is exactly the kind of contested identification that the concordance is designed to surface.

### The Structural Problem

The extraction gap is not random. It reveals a systematic bias in how LLMs process text for entity extraction.

**Salience-based extraction vs. exhaustive extraction.** When given a passage and asked to "extract all entities," LLMs consistently perform *salience-based* extraction — identifying the entities that are most topically central to the passage. In the Ricettario passage, Spodio and Tabaxir are the topic; pompholige and tuzia appear as glosses, parenthetical equivalences, secondary references. The LLM correctly identifies what the passage is *about* but misses what makes it *interesting to a historian*.

**The gloss paradox.** In early modern texts, the most information-dense entity mentions are often glosses — parenthetical translations, synonym lists, etymological notes, and cross-references to other nomenclatural traditions. These are precisely the mentions that carry the richest cross-linguistic signal, and precisely the ones most likely to be treated as "context" rather than "entity" by an LLM trained on modern text where glosses are less common and less significant.

**Synonym chains as embedded concordances.** Early modern natural philosophers were doing their own concordance work. When Orta writes "aqual em Malabar chamam Casturi e em Persia Mushque" (which in Malabar they call Kasturi and in Persia Musk), he is creating a three-language concordance entry in a single sentence. When the Ricettario lists "Spodio, ò la pompholige o vero la tuzia," it maps across pharmaceutical traditions. These embedded concordances are the gold standard for entity resolution — they represent *explicit authorial claims* about equivalence — but current extraction pipelines systematically overlook them.

---

## Proposed Multi-Layered Solution

### Layer 1: Targeted Second-Pass Extraction (Automated, Immediate)

The most cost-effective intervention. The concordance already stores **context strings** for every extracted entity — the text excerpts in which each entity was mentioned. These contexts are exactly where synonym chains live.

**Method:** For each entity's context strings, run a focused LLM pass: "Here are the entities already known in this concordance. Here is an excerpt where entity X was found. Are there any substance, plant, disease, place, or person names mentioned in this excerpt that are NOT in the entity list?"

**Why this is easier than open-ended extraction:**
- The task is closer to NER with a known vocabulary than to open extraction
- The search space is constrained to ~35K saved excerpts, not entire books
- The existing entity list provides strong priors — the model can check candidates against known terms
- Synonym chains typically appear *alongside* already-extracted entities, so this method targets exactly the right passages

**Expected yield:** Based on the pompholige case and similar patterns observed during manual review, we estimate 5-15% of existing context strings contain at least one unextracted entity mention that would be valuable for the concordance. At ~35K contexts, this could surface 1,750-5,250 new entity-cluster links.

**Cost:** At Gemini 2.5 Flash Lite rates, processing 35K short excerpts would cost approximately $1-3.

### Layer 2: User-Driven Annotation (Human-in-the-Loop, Medium-Term)

A historian discovering the pompholige connection *is doing the core scholarly work the concordance exists to support.* Building this into the user interface turns every research session into a data improvement loop.

**Proposed UI mechanism:**
1. When viewing an entity's context excerpts, users can select any word or phrase
2. A popover offers: "Flag as entity" → optionally suggest an existing cluster → submit for review
3. Flagged entities enter a review queue visible to project editors
4. Approved flags become new cluster members with provenance metadata ("user-flagged," reviewer, date)

**Why this matters beyond data quality:**
- It generates expert-annotated training data for fine-tuning (Layer 3)
- It creates a scholarly contribution trail — user annotations are citable evidence of entity identification
- It surfaces historically contested identifications (a user might flag pompholige as zinc oxide while another flags it as bamboo sugar, revealing the historical debate)
- It aligns with established digital humanities practices of collaborative annotation (cf. Recogito, Hypothes.is, Pelagios)

**Scalability concern:** User engagement is unpredictable. Mitigation: make flagging frictionless (two clicks), provide immediate feedback (show the cluster the entity would join), and consider gamification elements (contribution counts, leaderboards) without compromising scholarly rigor.

### Layer 3: Fine-Tuned Entity Mention Detection (Specialized, Long-Term)

Once Layers 1 and 2 have generated sufficient labeled data (estimated 1,000+ expert-reviewed examples), fine-tune a small model specifically for the task of entity mention detection in early modern text excerpts.

**Key insight:** This is NOT the same task as open-ended entity extraction (which the 0.6B Qwen3 attempt failed at with F1=1.74%). It is a much simpler task: given a text excerpt and a vocabulary of known entities, identify additional mentions of entities from that vocabulary. This is essentially token classification / NER with a dynamic label set, which small models handle well.

**Training data sources:**
- `data/training/membership_decisions.jsonl` — 491 expert-reviewed membership verdicts (90 negative, 401 positive) with cross-linguistic pattern labels
- `data/training_pairs.json` — 347 positive pairs and 63 hard negatives for embedding fine-tuning
- User-flagged entities from Layer 2 (once accumulated)
- Synthetically augmented examples: apply OCR corruption patterns (ſ→s, ligatures, abbreviation marks) to generate additional training pairs

**Model selection:** Start from a multilingual base (BGE-M3, multilingual-e5-large, or XLM-RoBERTa) and fine-tune with contrastive loss. The key capability is handling orthographic variation across Latin, Portuguese, Spanish, Italian, French, and English — with OCR artifacts — while distinguishing genuine cross-linguistic equivalence from superficial string similarity.

---

## Broader Methodological Implications

### For Digital Humanities

The synonym chain problem illustrates a general tension in computational approaches to historical texts: **the features that make a passage interesting to a humanist are often the features that make it difficult for automated systems.** Glosses, digressions, parenthetical asides, and lists of alternative names are where early modern authors did their most sophisticated comparative and cross-cultural thinking. These are also the textual structures most likely to be flattened or overlooked by NLP pipelines trained on modern prose.

This suggests that DH projects should design their pipelines with explicit attention to the *genre conventions* of their source texts. Early modern scientific and medical writing has characteristic structures — the synonym chain, the authority citation, the recipe, the case history — that carry different information types. A pipeline tuned to recognize and exhaustively process synonym chains would dramatically improve entity coverage for this genre, even if it added no value for, say, diplomatic correspondence or legal records.

### For NLP/AI

The training data generated by this project — particularly the expert-reviewed membership decisions and user-flagged entity annotations — represents a novel benchmark for **cross-linguistic entity resolution in low-resource, high-noise settings.** Current NER benchmarks (CoNLL, OntoNotes) use modern, well-edited text in major languages. The premodern concordance task adds:

- **OCR noise** (ſ for s, ct ligatures, broken words, missing diacritics)
- **Unstable orthography** (no standardized spelling in any of the source languages)
- **Cross-script synonymy** (Arabic, Sanskrit, Persian, and Malay terms transcribed into Latin script with varying conventions)
- **Historically contingent semantics** (is tabaxir the same as spodium? The answer changed between 1563 and 1700)
- **Six-language coverage** with code-switching within passages

These challenges are not unique to early modern pharmacy — they appear in any historical NLP task, in indigenous language documentation, in analysis of social media code-switching, and in biomedical NER where the same compound has different names across national pharmacopeias. A model that learns to handle pompholige/pompholix/pompholigos would generalize to many analogous problems.

### For History of Science and Medicine

The ability to systematically surface synonym chains and contested identifications has direct applications for research on:

1. **Knowledge circulation:** Tracking which terms traveled between linguistic communities reveals trade routes, scholarly networks, and translation practices. The fact that tabaxir (Sanskrit → Arabic → Portuguese) and pompholige (Greek → Italian) converge on the same substance in the Ricettario tells us something about how Indian Ocean trade goods were integrated into European pharmaceutical knowledge via multiple channels.

2. **Contested identification:** When the concordance shows that Spodio, pompholige, and tabaxir are sometimes equated and sometimes distinguished, it surfaces an active early modern debate about substance identity — a debate that maps onto deeper questions about the relationship between classical authorities (who knew pompholix) and empirical observation of new materials arriving from Asia (tabaxir).

3. **Pharmacological standardization:** The Ricettario Fiorentino was an *official* pharmacopeia — a prescriptive text that aimed to standardize drug nomenclature. Its synonym chains are not casual observations but deliberate acts of terminological legislation. Tracking how these official equivalences were adopted, modified, or rejected in later texts would illuminate the history of pharmaceutical regulation.

---

## Data Assets Generated

| Asset | Location | Description |
|-------|----------|-------------|
| Expert membership decisions | `data/training/membership_decisions.jsonl` | 491 labeled examples (KEEP/SPLIT) with reasoning |
| Cross-lingual training pairs | `data/training_pairs.json` | 347 positive + 63 hard negative pairs across 6 languages |
| Concordance (cleaned) | `web/public/data/concordance.json` | 1,283 clusters after 3-phase cleanup + 90 expert splits |
| Search embeddings | `web/public/data/search_index.json` | 512-dim text-embedding-3-small vectors for all clusters |

---

## Next Steps (Research)

1. **Quantify the gap.** Run the second-pass extraction on all existing context strings. How many new entity mentions are found? What percentage are synonym-chain members vs. isolated references?
2. **Characterize synonym chain patterns.** Do they cluster by book? By category? By language combination? Are some authors (Orta? the Ricettario compilers?) more prone to explicit synonym listing than others?
3. **Build the flagging UI.** Even a minimal version (select text → flag → review queue) would begin generating user annotation data.
4. **Evaluate embedding model on synonym chain members.** Once new entities are extracted from synonym chains, test whether the existing BGE-M3 embeddings correctly cluster them with their synonyms. If so, the embedding model is fine and the bottleneck is purely extraction. If not, the training data from Layers 1-2 becomes the basis for re-fine-tuning.
5. **Write up the pompholige case** as a detailed worked example for the methods section of the article.

---

## Key References (to look up)

- Recogito / Pelagios for collaborative historical annotation models
- Recent work on NER in historical texts (especially non-English)
- Literature on early modern pharmaceutical synonymy (Findlen? Leong? Ragland?)
- The historiography of spodium/tabaxir/pompholix identification specifically (this is a known puzzle in history of pharmacy — Dioscorides vs. Arabic pharmacy vs. Indian materia medica)
- Benchmark papers for cross-lingual entity linking (TAC-KBP, MEWSLI-X)
