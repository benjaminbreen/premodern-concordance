import { NextRequest, NextResponse } from "next/server";
import { GoogleGenerativeAI } from "@google/generative-ai";
import OpenAI from "openai";
import { readFileSync } from "fs";
import { join } from "path";
import {
  getEntityRegistry,
  type RegistryBook,
  type RegistryEntity,
  type RegistryAttestation,
} from "@/lib/entityRegistry";

// ── Types ──────────────────────────────────────────────────────────────

interface EpistemologicalProfile {
  persona_name: string;
  persona_description: string;
  voice_notes: string;
  frameworks: { name: string; role: string; description: string }[];
  authorities_trusted: string[];
  authorities_contested: string[];
  knowledge_sources: string;
  blind_spots: string;
  historical_context: string;
  sample_reasoning: string;
  top_substances: string;
  top_diseases: string;
  language: string;
  voice_anchors?: string[];
  private_facts_known?: string[];
  private_inferences_allowed?: string[];
  private_unknowns?: string[];
  persona_type?: "individual" | "institution";
}

interface RetrievedEvidence {
  entity: RegistryEntity;
  attestation: RegistryAttestation;
  score: number;
}

interface ConsultResponse {
  response: string;
  evidence_used: {
    entity_id: string;
    entity_name: string;
    category: string;
    relevance: "direct" | "analogical";
    reasoning: string;
  }[];
  confidence: "high" | "moderate" | "low" | "speculative";
  confidence_explanation: string;
  frameworks_applied: string[];
  modern_note: string;
}

const PROCEDURAL_QUERY_RE =
  /\b(cure|treat|treatment|remedy|recipe|receipt|dose|dosage|prepare|preparation|compound|how do you make|how to make)\b/i;
const GREETING_QUERY_RE =
  /^(hi|hello|hey|greetings|salve|ciao|good\s+(morning|afternoon|evening))[\s,!.?]*.*$/i;

interface BookPromptContext {
  book_id: string;
  book_title: string;
  publication_year: number;
}

function isGreeting(question: string): boolean {
  return GREETING_QUERY_RE.test(question.trim());
}

const EVIDENCE_LIMIT = 15;
const MAX_OUTPUT_TOKENS = 3072;

// ── Cached data ────────────────────────────────────────────────────────

let cachedProfiles: Record<string, EpistemologicalProfile> | null = null;

function getProfiles(): Record<string, EpistemologicalProfile> {
  if (cachedProfiles) return cachedProfiles;
  const filePath = join(
    process.cwd(),
    "public",
    "data",
    "book_epistemologies.json"
  );
  cachedProfiles = JSON.parse(readFileSync(filePath, "utf-8"));
  return cachedProfiles!;
}

function buildFallbackProfile(
  bookId: string,
  bookMeta: RegistryBook | undefined,
  publicationYear: number
): EpistemologicalProfile {
  const author = bookMeta?.author || "the author";
  const title = bookMeta?.title || bookId;
  const language = bookMeta?.language || "unknown";
  return {
    persona_name: author,
    persona_description: `Authorial voice grounded in "${title}" (${publicationYear}).`,
    voice_notes:
      "Answer cautiously in period-appropriate terms, citing uncertainty when evidence is weak.",
    frameworks: [
      {
        name: "Text-grounded reasoning",
        role: "primary",
        description:
          "Rely on attested entities and contexts from this book and related concordance evidence.",
      },
    ],
    authorities_trusted: [],
    authorities_contested: [],
    knowledge_sources:
      "Entity attestations and contextual excerpts from the concordance and the selected book.",
    blind_spots:
      "Modern scientific developments after publication and facts not attested in available evidence.",
    historical_context:
      `Interpretive frame: ${publicationYear} publication context, language=${language}.`,
    sample_reasoning:
      "I prioritize direct textual evidence, then analogical evidence; I mark speculation explicitly.",
    top_substances: "",
    top_diseases: "",
    language,
    voice_anchors: [],
    private_facts_known: [],
    private_inferences_allowed: [],
    private_unknowns: [],
    persona_type: "individual",
  };
}

// ── Search index for semantic retrieval ────────────────────────────────

interface SearchEntry {
  embedding: number[];
  metadata: {
    id: string;
    canonical_name: string;
    category: string;
    books: string[];
    names: string[];
    [key: string]: unknown;
  };
}

interface SearchIndex {
  model: string;
  dimensions: number;
  entries: SearchEntry[];
}

let cachedSearchIndex: SearchIndex | null = null;

function getSearchIndex(): SearchIndex | null {
  if (cachedSearchIndex) return cachedSearchIndex;
  try {
    const indexPath = join(
      process.cwd(),
      "public",
      "data",
      "search_index.json"
    );
    cachedSearchIndex = JSON.parse(readFileSync(indexPath, "utf-8"));
    return cachedSearchIndex;
  } catch {
    return null;
  }
}

function cosineSimilarity(a: number[], b: number[]): number {
  let dot = 0,
    normA = 0,
    normB = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i];
    normA += a[i] * a[i];
    normB += b[i] * b[i];
  }
  return dot / (Math.sqrt(normA) * Math.sqrt(normB) + 1e-10);
}

/**
 * Embed the question and find semantically similar entities in this book
 * from the pre-built search index (concordance clusters only).
 * Returns a Map of lowercase canonical_name → similarity score.
 */
async function getSemanticMatches(
  bookId: string,
  question: string,
  limit: number
): Promise<Map<string, number>> {
  const apiKey = process.env.OPENAI_API_KEY;
  const index = getSearchIndex();
  if (!apiKey || !index) return new Map();

  try {
    const openai = new OpenAI({ apiKey });
    const response = await openai.embeddings.create({
      model: index.model,
      input: question,
      dimensions: index.dimensions,
    });
    const queryEmb = response.data[0].embedding;

    // Filter to entries that appear in this book
    const bookEntries = index.entries.filter((e) =>
      e.metadata.books?.includes(bookId)
    );

    const scored = bookEntries.map((entry) => ({
      canonical_name: entry.metadata.canonical_name,
      names: entry.metadata.names || [],
      score: cosineSimilarity(queryEmb, entry.embedding),
    }));

    scored.sort((a, b) => b.score - a.score);

    const result = new Map<string, number>();
    for (const s of scored.slice(0, limit)) {
      if (s.score > 0.25) {
        // Index by canonical name and all variant names
        result.set(s.canonical_name.toLowerCase(), s.score);
        for (const name of s.names) {
          result.set(name.toLowerCase(), s.score);
        }
      }
    }
    return result;
  } catch (err) {
    console.warn("Semantic search failed, falling back to keyword-only:", err);
    return new Map();
  }
}

// ── Stop words for keyword matching ────────────────────────────────────
// NOTE: "treat", "cure", "remedy" etc. are NOT stop words — they are
// important signal words in a medical corpus and match therapeutic contexts.

const STOP_WORDS = new Set([
  "the", "a", "an", "is", "was", "are", "were", "be", "been", "being",
  "have", "has", "had", "do", "does", "did", "will", "would", "could",
  "should", "may", "might", "shall", "can", "to", "of", "in", "for",
  "on", "with", "at", "by", "from", "as", "into", "through", "during",
  "before", "after", "above", "below", "between", "out", "off", "over",
  "under", "again", "further", "then", "once", "here", "there", "when",
  "where", "why", "how", "all", "both", "each", "few", "more", "most",
  "other", "some", "such", "no", "nor", "not", "only", "own", "same",
  "so", "than", "too", "very", "just", "about", "also", "and", "but",
  "or", "if", "what", "which", "who", "whom", "this", "that", "these",
  "those", "it", "its", "you", "your", "he", "his", "she", "her", "we",
  "they", "them", "their", "my", "me", "i", "tell", "explain", "describe",
  "know", "think", "believe",
]);

// ── Stage 1: Hybrid retrieval (keyword + semantic) ─────────────────────

async function retrieveEntities(
  bookId: string,
  question: string
): Promise<RetrievedEvidence[]> {
  const registry = getEntityRegistry();
  const bookEntities = registry.entities.filter((e) =>
    e.books.includes(bookId)
  );
  // Semantic search (skip for greetings — not worth the latency)
  const semanticScores = !isGreeting(question)
    ? await getSemanticMatches(bookId, question, 25)
    : new Map<string, number>();

  // Tokenize question, remove stop words
  const tokens = question
    .toLowerCase()
    .replace(/[^\w\s]/g, "")
    .split(/\s+/)
    .filter((t) => t.length > 2 && !STOP_WORDS.has(t));

  const questionLower = question.toLowerCase();

  const scored: RetrievedEvidence[] = [];

  for (const entity of bookEntities) {
    const attestation = entity.attestations.find((a) => a.book_id === bookId);
    if (!attestation) continue;

    // Build search text from entity data
    const nameText = [
      entity.canonical_name,
      ...entity.names,
      ...(attestation.variants || []),
    ]
      .join(" ")
      .toLowerCase();

    const contextText = [
      ...(attestation.contexts || []),
      ...(attestation.excerpt_samples || []),
    ]
      .join(" ")
      .toLowerCase();

    let score = 0;

    // Keyword matching — name matches weighted higher than context matches
    for (const token of tokens) {
      if (nameText.includes(token)) {
        score += 2; // name/variant match is strong
      } else if (contextText.includes(token)) {
        score += 0.5; // context match is weaker
      }
    }

    // Strong bonus for exact name match within question
    const nameLower = entity.canonical_name.toLowerCase();
    if (questionLower.includes(nameLower) && nameLower.length > 3) {
      score += 4;
    }

    // Check variant names too
    for (const name of entity.names) {
      if (questionLower.includes(name.toLowerCase()) && name.length > 3) {
        score += 3;
        break;
      }
    }

    // Semantic boost from embedding search
    const semScore =
      semanticScores.get(nameLower) ||
      semanticScores.get(attestation.local_name.toLowerCase());
    if (semScore) {
      score += semScore * 4; // semantic match worth up to ~4 points
    }

    // Mild popularity boost (important entities score slightly higher)
    score += Math.log(attestation.count + 1) * 0.05;

    if (score > 0) {
      scored.push({ entity, attestation, score });
    }
  }

  scored.sort((a, b) => b.score - a.score);
  return scored.slice(0, EVIDENCE_LIMIT);
}

// ── Dynamic entity summaries from registry ─────────────────────────────

const CATEGORY_ORDER = [
  "SUBSTANCE",
  "DISEASE",
  "PLANT",
  "PERSON",
  "CONCEPT",
  "PLACE",
  "ANIMAL",
  "ANATOMY",
  "OBJECT",
];

function buildDynamicEntitySummary(bookId: string): string {
  const registry = getEntityRegistry();
  const bookEntities = registry.entities.filter((e) =>
    e.books.includes(bookId)
  );

  const byCat = new Map<string, { name: string; count: number }[]>();
  for (const e of bookEntities) {
    const att = e.attestations.find((a) => a.book_id === bookId);
    if (!att) continue;
    const list = byCat.get(e.category) || [];
    list.push({ name: att.local_name, count: att.count });
    byCat.set(e.category, list);
  }

  const parts: string[] = [];
  for (const cat of CATEGORY_ORDER) {
    const entities = byCat.get(cat);
    if (!entities || entities.length === 0) continue;
    entities.sort((a, b) => b.count - a.count);
    const top = entities
      .slice(0, 8)
      .map((e) => `${e.name} (${e.count})`)
      .join(", ");
    parts.push(`- ${cat} (${entities.length} total): ${top}`);
  }

  return parts.join("\n");
}

/**
 * Pick 2-3 representative excerpts from the book's entities
 * to calibrate the model's voice to the actual writing style.
 */
function getVoiceExcerpts(bookId: string): string[] {
  const registry = getEntityRegistry();
  const bookEntities = registry.entities.filter((e) =>
    e.books.includes(bookId)
  );

  // Sort by mention count to get excerpts from important entities
  const sorted = bookEntities
    .map((e) => ({
      entity: e,
      att: e.attestations.find((a) => a.book_id === bookId),
    }))
    .filter((x) => x.att && x.att.excerpt_samples && x.att.excerpt_samples.length > 0)
    .sort((a, b) => (b.att!.count || 0) - (a.att!.count || 0));

  const excerpts: string[] = [];
  const seen = new Set<string>();

  for (const { att } of sorted) {
    if (excerpts.length >= 3) break;
    for (const ex of att!.excerpt_samples!) {
      // Pick excerpts that are a reasonable length and aren't just lists
      if (
        ex.length >= 80 &&
        ex.length <= 250 &&
        !ex.includes("|") &&
        !seen.has(ex.slice(0, 40))
      ) {
        excerpts.push(ex);
        seen.add(ex.slice(0, 40));
        break; // one per entity
      }
    }
  }

  return excerpts;
}

// ── Stage 3: Prompt construction ───────────────────────────────────────

function looksInstitutional(profile: EpistemologicalProfile): boolean {
  if (profile.persona_type === "institution") return true;
  return /\b(college|guild|society|academy|office|institution)\b/i.test(
    profile.persona_name
  );
}

function buildSystemPrompt(
  profile: EpistemologicalProfile,
  context: BookPromptContext
): string {
  const parts: string[] = [];
  const institutional = looksInstitutional(profile);
  const privateFacts = profile.private_facts_known || [];
  const privateInferences = profile.private_inferences_allowed || [];
  const privateUnknowns = profile.private_unknowns || [];
  const anchors = profile.voice_anchors || [];

  parts.push(
    `You are ${profile.persona_name}. ${profile.persona_description}`
  );
  parts.push("");
  parts.push("## Non-negotiable epistemic constraints");
  parts.push(
    `- Knowledge cutoff: ${context.publication_year} (the publication year of "${context.book_title}").`
  );
  parts.push(
    `- You do NOT know events, discoveries, terminology, or named diseases emerging after ${context.publication_year}.`
  );
  parts.push(
    "- If asked about post-cutoff topics, explicitly say the topic is unknown in your present moment and answer by closest in-period analogy."
  );
  parts.push(
    "- Never present modern biomedical mechanisms (e.g., viruses, DNA, antibiotics, randomized trials) as if they are known to you."
  );
  parts.push(
    "- Do not fabricate private episodes, relationships, motives, or emotions that are not supported by the dossier below."
  );
  parts.push("");
  parts.push("## Persona mode");
  parts.push(
    institutional
      ? "- Speak in first-person plural as an institutional voice (`we`), formal and procedural."
      : "- Speak in first-person singular as the historical author (`I`), with period-appropriate vocabulary."
  );
  parts.push("");
  parts.push(`Voice and tone: ${profile.voice_notes}`);
  if (anchors.length > 0) {
    parts.push("");
    parts.push(
      `Voice anchors (preferred recurring phrases/register): ${anchors.join("; ")}`
    );
  }

  // Voice calibration: actual excerpts from the book
  const excerpts = getVoiceExcerpts(context.book_id);
  if (excerpts.length > 0) {
    parts.push("");
    parts.push(
      "## Voice calibration (actual passages from your text — match this register)"
    );
    for (const ex of excerpts) {
      parts.push(`> "${ex}"`);
    }
  }

  parts.push("");
  parts.push("## Your intellectual framework");
  for (const fw of profile.frameworks) {
    parts.push(`- **${fw.name}** (${fw.role}): ${fw.description}`);
  }
  parts.push("");
  parts.push(
    `## Authorities you trust\n${profile.authorities_trusted.join(", ")}`
  );
  parts.push("");
  parts.push(
    `## Authorities you contest or are skeptical of\n${profile.authorities_contested.join(", ")}`
  );
  parts.push("");
  parts.push(`## Your knowledge sources\n${profile.knowledge_sources}`);
  parts.push("");
  parts.push(
    `## What you do NOT know (critical — never claim knowledge beyond your era)\n${profile.blind_spots}`
  );
  parts.push("");
  parts.push(`## Historical context\n${profile.historical_context}`);
  parts.push("");
  parts.push(`## How you typically reason\n${profile.sample_reasoning}`);

  // Dynamic entity summaries from actual registry data
  parts.push("");
  parts.push(
    "## Your materia — entities discussed in your text (top entries by mention count)"
  );
  parts.push(buildDynamicEntitySummary(context.book_id));

  parts.push("");
  parts.push("## Biographical and inner-life dossier");
  parts.push(`- Public biographical frame: ${profile.persona_description}`);
  if (privateFacts.length > 0) {
    parts.push(`- Private facts known: ${privateFacts.join("; ")}`);
  } else {
    parts.push(
      "- Private facts known: infer ONLY from the supplied historical context and persona description."
    );
  }
  if (privateInferences.length > 0) {
    parts.push(
      `- Private inferences allowed (mark uncertainty): ${privateInferences.join("; ")}`
    );
  } else {
    parts.push(
      "- Private inferences allowed: conservative inference only; mark uncertainty explicitly."
    );
  }
  if (privateUnknowns.length > 0) {
    parts.push(
      `- Private unknowns (must not invent): ${privateUnknowns.join("; ")}`
    );
  }

  return parts.join("\n");
}

function buildUserMessage(
  question: string,
  evidence: RetrievedEvidence[],
  personaName: string,
  context: BookPromptContext
): string {
  const parts: string[] = [];
  const isProcedural = PROCEDURAL_QUERY_RE.test(question);

  parts.push(`A reader asks: "${question}"`);
  parts.push("");

  if (evidence.length > 0) {
    parts.push("Evidence from your writings, grouped by type:");
    parts.push("");

    // Group evidence by category for clearer reasoning
    const grouped = new Map<string, RetrievedEvidence[]>();
    for (const ev of evidence) {
      const cat = ev.entity.category;
      const list = grouped.get(cat) || [];
      list.push(ev);
      grouped.set(cat, list);
    }

    for (const cat of CATEGORY_ORDER) {
      const group = grouped.get(cat);
      if (!group) continue;
      parts.push(`**${cat}:**`);

      for (const { entity, attestation } of group) {
        // Include entity_id so the LLM can cite it back
        parts.push(
          `- [${entity.id}] ${attestation.local_name} (${attestation.count} mentions)`
        );
        if (attestation.contexts?.length) {
          parts.push(`  Context: ${attestation.contexts[0]}`);
        }
        if (attestation.excerpt_samples?.length) {
          parts.push(
            `  > "${attestation.excerpt_samples[0].slice(0, 250)}"`
          );
        }
      }
      parts.push("");
    }

    // Also include any categories not in CATEGORY_ORDER
    for (const [cat, group] of grouped) {
      if (CATEGORY_ORDER.includes(cat)) continue;
      parts.push(`**${cat}:**`);
      for (const { entity, attestation } of group) {
        parts.push(
          `- [${entity.id}] ${attestation.local_name} (${attestation.count} mentions)`
        );
      }
      parts.push("");
    }
  } else {
    parts.push(
      "No passages in your writings directly address this topic. Reason from " +
        "your principles and the closest analogous conditions you do discuss."
    );
    parts.push("");
  }

  parts.push(
    `Respond as ${personaName} would, in first person, drawing only on the knowledge and frameworks described above.`
  );
  parts.push("");
  parts.push(
    `Date lock: you are in year ${context.publication_year}; anything later is unknown to you.`
  );
  parts.push(
    "If the query uses a modern term, acknowledge it as unknown in your period, then reason analogically from your own categories."
  );
  parts.push("");
  parts.push(
    "Match your response length naturally to the question — a greeting gets a brief reply, a complex question gets a thorough answer."
  );
  parts.push(
    "No meta-commentary like 'the query asks'. No headings titled 'Response' or 'Interpretation'."
  );

  if (isProcedural) {
    parts.push(
      "This is a practical/therapeutic question. Include a markdown table summarizing key items, rationale, and cautions."
    );
  } else if (evidence.length > 3) {
    parts.push(
      "If helpful, include a markdown table to organize key findings."
    );
  }

  // Compact JSON format spec — include note about entity_id
  parts.push("");
  parts.push(
    'Respond with a single JSON object: {"response":"markdown answer in character","evidence_used":[{"entity_id":"the [id] from evidence above","entity_name":"name","category":"CAT","relevance":"direct|analogical","reasoning":"why cited"}],"confidence":"high|moderate|low|speculative","confidence_explanation":"why","frameworks_applied":["name"],"modern_note":""}'
  );

  return parts.join("\n");
}

// ── Stage 4: Synthesis via Gemini ──────────────────────────────────────

function extractJSON(text: string): string {
  // Strip markdown code fences if present
  const cleaned = text
    .replace(/^```(?:json)?\s*\n?/i, "")
    .replace(/\n?```\s*$/i, "");
  // Find the outermost JSON object
  const braceStart = cleaned.indexOf("{");
  const braceEnd = cleaned.lastIndexOf("}");
  if (braceStart !== -1 && braceEnd > braceStart) {
    return cleaned.slice(braceStart, braceEnd + 1);
  }
  return cleaned.trim();
}

async function synthesize(
  systemPrompt: string,
  userMessage: string,
  apiKey: string,
  maxOutputTokens: number,
  question: string
): Promise<ConsultResponse> {
  const genAI = new GoogleGenerativeAI(apiKey);
  const model = genAI.getGenerativeModel({
    model: "gemini-2.5-flash",
    generationConfig: {
      temperature: 0.4,
      maxOutputTokens,
      responseMimeType: "application/json",
    },
  });

  // Combine system + user into a single prompt
  const fullPrompt = [
    "=== PERSONA AND CONTEXT ===",
    systemPrompt,
    "",
    "=== QUERY AND EVIDENCE ===",
    userMessage,
    "",
    "IMPORTANT: Respond with ONLY the JSON object described above. No markdown fences, no explanation outside the JSON.",
  ].join("\n");

  const result = await model.generateContent(fullPrompt);
  const rawText = result.response.text().trim();
  const jsonText = extractJSON(rawText);

  const parseCandidates = [rawText, jsonText];
  for (const candidate of parseCandidates) {
    try {
      return JSON.parse(candidate) as ConsultResponse;
    } catch {
      // keep trying
    }
  }

  // If JSON is truncated, try to repair common issues once.
  try {
    let repaired = jsonText;
    const openQuotes = (repaired.match(/"/g) || []).length;
    if (openQuotes % 2 !== 0) repaired += '"';
    const opens = (repaired.match(/[{[]/g) || []).length;
    const closes = (repaired.match(/[}\]]/g) || []).length;
    for (let i = 0; i < opens - closes; i++) {
      repaired +=
        repaired.includes("[") && !repaired.endsWith("]") ? "]" : "}";
    }
    return JSON.parse(repaired) as ConsultResponse;
  } catch {
    // Fail safe: return a minimal, valid structure so UI does not hard-fail.
    return {
      response: "I cannot answer confidently from my text as presently consulted.",
      evidence_used: [],
      confidence: "low",
      confidence_explanation:
        "Model output was malformed and could not be parsed as JSON.",
      frameworks_applied: [],
      modern_note: "",
    };
  }
}

// ── Stage 5: Validation ────────────────────────────────────────────────

function validate(
  response: ConsultResponse,
  evidence: RetrievedEvidence[],
  question: string
): ConsultResponse {
  if (!response || typeof response !== "object") {
    response = {
      response: "",
      evidence_used: [],
      confidence: "low",
      confidence_explanation: "",
      frameworks_applied: [],
      modern_note: "",
    };
  }
  if (!Array.isArray(response.evidence_used)) response.evidence_used = [];
  if (!Array.isArray(response.frameworks_applied))
    response.frameworks_applied = [];
  if (typeof response.response !== "string") response.response = "";

  // Build lookup maps: canonical name, local names, and entity IDs
  const evidenceIds = new Set(evidence.map((e) => e.entity.id));
  const evidenceNames = new Map<string, string>();
  for (const e of evidence) {
    evidenceNames.set(e.entity.canonical_name.toLowerCase(), e.entity.id);
    evidenceNames.set(e.attestation.local_name.toLowerCase(), e.entity.id);
    for (const name of e.entity.names) {
      evidenceNames.set(name.toLowerCase(), e.entity.id);
    }
  }

  // Filter evidence_used to entities we actually retrieved
  response.evidence_used = (response.evidence_used || []).filter((eu) => {
    if (evidenceIds.has(eu.entity_id)) return true;
    // Try matching by name (canonical, local, or variant)
    const matchedId = evidenceNames.get(
      (eu.entity_name || "").toLowerCase()
    );
    if (matchedId) {
      eu.entity_id = matchedId;
      return true;
    }
    return false;
  });

  // Ensure confidence is valid
  const validConfidence = ["high", "moderate", "low", "speculative"];
  if (!validConfidence.includes(response.confidence)) {
    response.confidence = "moderate";
  }

  // Keep persona answer strictly in-period; suppress modern commentary.
  response.modern_note = "";

  // Keep evidence concise for UI.
  response.evidence_used = response.evidence_used.slice(0, 8);

  // Strip unwanted meta headings
  response.response = (response.response || "")
    .replace(/^\s*#{1,6}\s*(response|interpretation)\s*$/gim, "")
    .replace(/^\s*(response|interpretation)\s*:?\s*/i, "")
    .trim();

  if (!response.response) {
    response.response =
      "I have insufficient evidence in my present materials to answer securely.";
  }

  // For procedural questions, ensure at least one table-like structure exists.
  const hasTable =
    /\|.+\|/.test(response.response || "") &&
    /\n\|(?:\s*:?-+:?\s*\|)+\s*\n/.test(response.response || "");
  if (
    !hasTable &&
    PROCEDURAL_QUERY_RE.test(question) &&
    evidence.length > 0
  ) {
    const rows = evidence
      .slice(0, 5)
      .map((e) => {
        const rationale = (e.attestation.contexts?.[0] || "").replace(
          /\|/g,
          "/"
        );
        return `| ${e.attestation.local_name} | ${e.entity.category} | ${rationale || "Referenced in source text"} |`;
      })
      .join("\n");
    response.response +=
      "\n\n## Evidence Table\n\n| Item | Type | Why It Appears |\n|---|---|---|\n" +
      rows;
  }

  return response;
}

// ── API handler ────────────────────────────────────────────────────────

export async function POST(request: NextRequest) {
  const geminiKey = process.env.GEMINI_API_KEY;
  if (!geminiKey) {
    return NextResponse.json(
      { error: "GEMINI_API_KEY not configured" },
      { status: 500 }
    );
  }

  let body: { book_id: string; question: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const { book_id, question } = body;
  if (!book_id || !question?.trim()) {
    return NextResponse.json(
      { error: "Missing book_id or question" },
      { status: 400 }
    );
  }

  if (question.length > 500) {
    return NextResponse.json(
      { error: "Question too long (max 500 characters)" },
      { status: 400 }
    );
  }

  try {
    const registry = getEntityRegistry();
    const bookMeta = registry.books.find((b) => b.id === book_id);
    const fallbackYearMatch = book_id.match(/(1[0-9]{3}|20[0-9]{2})/);
    const publicationYear =
      bookMeta?.year ||
      (fallbackYearMatch
        ? Number.parseInt(fallbackYearMatch[1], 10)
        : 1900);
    const bookTitle = bookMeta?.title || book_id;
    const promptContext: BookPromptContext = {
      book_id,
      book_title: bookTitle,
      publication_year: publicationYear,
    };

    const profiles = getProfiles();
    const profile =
      profiles[book_id] || buildFallbackProfile(book_id, bookMeta, publicationYear);

    // Stage 1: Retrieve (now async — includes semantic search)
    const evidence = await retrieveEntities(book_id, question);

    // Stage 3: Build prompt
    const systemPrompt = buildSystemPrompt(profile, promptContext);
    const userMessage = buildUserMessage(
      question,
      evidence,
      profile.persona_name,
      promptContext
    );
    // Stage 4: Synthesize
    const rawResponse = await synthesize(
      systemPrompt,
      userMessage,
      geminiKey,
      MAX_OUTPUT_TOKENS,
      question
    );

    // Stage 5: Validate
    const validated = validate(rawResponse, evidence, question);

    const bookEntityCount = registry.entities.filter((e) =>
      e.books.includes(book_id)
    ).length;

    return NextResponse.json({
      ...validated,
      _meta: {
        book_id,
        persona: profile.persona_name,
        entities_retrieved: evidence.length,
        entities_in_book: bookEntityCount,
        publication_year: publicationYear,
        frameworks_available: profile.frameworks.length,
        evidence_used_count: validated.evidence_used.length,
        retrieval_mode: process.env.OPENAI_API_KEY ? "hybrid" : "keyword",
        evidence_entities: evidence.map((e) => ({
          id: e.entity.id,
          slug: e.entity.slug,
          name: e.attestation.local_name,
          category: e.entity.category,
          count: e.attestation.count,
          score: Math.round(e.score * 100) / 100,
        })),
      },
    });
  } catch (e) {
    const message = e instanceof Error ? e.message : "Consultation failed";
    console.error("Consult API error:", e);
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
