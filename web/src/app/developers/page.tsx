"use client";

import { useState } from "react";

/* ───── endpoint definitions ───── */

interface Param {
  name: string;
  type: string;
  required?: boolean;
  description: string;
}

interface Endpoint {
  method: "GET" | "POST";
  path: string;
  description: string;
  group: "data" | "search" | "ai";
  params?: Param[];
  body?: Param[];
  exampleRequest?: string;
  exampleResponse: string;
  notes?: string;
}

const ENDPOINTS: Endpoint[] = [
  {
    method: "GET",
    path: "/api/books",
    description: "List all books in the corpus with metadata.",
    group: "data",
    exampleRequest: "curl https://premodern-concordance.vercel.app/api/books",
    exampleResponse: `{
  "books": [
    {
      "id": "culpeper",
      "title": "The English Physician",
      "author": "Nicholas Culpeper",
      "year": 1652,
      "language": "English"
    }
  ],
  "total": 12
}`,
  },
  {
    method: "GET",
    path: "/api/entities",
    description:
      "Browse and search all entities with filtering, pagination, and sorting.",
    group: "data",
    params: [
      { name: "q", type: "string", description: "Search query (fuzzy name matching)" },
      { name: "category", type: "string", description: 'Filter by category, e.g. "SUBSTANCE", "PERSON", "PLANT"' },
      { name: "book", type: "string", description: 'Filter by book ID, e.g. "culpeper"' },
      { name: "cross_book", type: "string", description: '"only" = multi-book entities, "exclude" = single-book only' },
      { name: "sort", type: "string", description: '"alpha" or "mentions" (default: relevance)' },
      { name: "page", type: "number", description: "Page number (default: 1)" },
      { name: "limit", type: "number", description: "Results per page (default: 40, max: 100)" },
      { name: "compact", type: "string", description: '"1" for compact results (fewer fields, max 5000)' },
    ],
    exampleRequest:
      "curl 'https://premodern-concordance.vercel.app/api/entities?q=mercury&limit=3'",
    exampleResponse: `{
  "query": "mercury",
  "page": 1,
  "limit": 3,
  "total": 8,
  "total_pages": 3,
  "results": [
    {
      "id": "mercury-cl",
      "slug": "mercury",
      "canonical_name": "Mercury",
      "category": "SUBSTANCE",
      "book_count": 5,
      "total_mentions": 87,
      "is_concordance": true,
      "books": ["culpeper", "monardes", "orta", "ricettario", "semedo"]
    }
  ]
}`,
  },
  {
    method: "GET",
    path: "/api/entity/:slug",
    description:
      "Get full details for a single entity by slug, including all attestations and ground truth.",
    group: "data",
    params: [
      { name: "slug", type: "string", required: true, description: "Entity slug (from /api/entities results)" },
    ],
    exampleRequest:
      "curl https://premodern-concordance.vercel.app/api/entity/mercury",
    exampleResponse: `{
  "entity": {
    "id": "mercury-cl",
    "slug": "mercury",
    "canonical_name": "Mercury",
    "category": "SUBSTANCE",
    "book_count": 5,
    "total_mentions": 87,
    "ground_truth": {
      "modern_name": "Mercury",
      "wikidata_id": "Q925",
      "wikipedia_url": "https://en.wikipedia.org/wiki/Mercury_(element)"
    },
    "attestations": [ "..." ]
  },
  "book_details": [ "..." ]
}`,
  },
  {
    method: "GET",
    path: "/api/entity/:slug/attestations",
    description:
      "Get attestation details for an entity in each book where it appears.",
    group: "data",
    params: [
      { name: "slug", type: "string", required: true, description: "Entity slug" },
    ],
    exampleRequest:
      "curl https://premodern-concordance.vercel.app/api/entity/mercury/attestations",
    exampleResponse: `{
  "entity_id": "mercury-cl",
  "attestations": [
    {
      "book_id": "culpeper",
      "local_name": "Mercury",
      "count": 23,
      "contexts": ["..."],
      "excerpt_samples": ["..."]
    }
  ]
}`,
  },
  {
    method: "GET",
    path: "/api/clusters/:slug",
    description:
      "Get a concordance cluster by slug, with book metadata, navigation, and neighbors.",
    group: "data",
    params: [
      { name: "slug", type: "string", required: true, description: "Cluster slug (stable_key or slugified name)" },
    ],
    exampleRequest:
      "curl https://premodern-concordance.vercel.app/api/clusters/galen",
    exampleResponse: `{
  "cluster": {
    "id": 42,
    "canonical_name": "Galen",
    "category": "PERSON",
    "members": [ "..." ],
    "ground_truth": { "modern_name": "Galen", "..." : "..." }
  },
  "books": [ { "id": "culpeper", "title": "The English Physician", "..." : "..." } ],
  "prev_slug": "frankincense",
  "next_slug": "galangal",
  "position": 42,
  "total_clusters": 4546,
  "neighbors": [
    { "id": 105, "slug": "hippocrates", "name": "Hippocrates", "category": "PERSON", "sim": 0.72 }
  ]
}`,
  },
  {
    method: "GET",
    path: "/api/search",
    description:
      "Hybrid semantic + lexical search across all concordance clusters. Falls back to lexical-only if no OpenAI key is configured on the server.",
    group: "search",
    params: [
      { name: "q", type: "string", required: true, description: "Search query (min 2 characters)" },
      { name: "limit", type: "number", description: "Max results (default: 20)" },
      { name: "category", type: "string", description: "Filter by category" },
    ],
    exampleRequest:
      "curl 'https://premodern-concordance.vercel.app/api/search?q=humoral+theory&limit=5'",
    exampleResponse: `{
  "query": "humoral theory",
  "results": [
    {
      "metadata": {
        "id": "123",
        "canonical_name": "Humours",
        "category": "CONCEPT",
        "book_count": 6
      },
      "score": 0.82,
      "semantic_score": 0.79,
      "lexical_score": 0.65
    }
  ],
  "total_candidates": 4546,
  "mode": "hybrid"
}`,
    notes:
      "Semantic mode uses text-embedding-3-small via a server-side OpenAI key. The server falls back to lexical-only if the key is unavailable.",
  },
  {
    method: "POST",
    path: "/api/consult",
    description:
      "Ask a question to a historical author persona grounded in concordance evidence. Rate-limited to 10 req/min per IP.",
    group: "ai",
    body: [
      { name: "book_id", type: "string", required: true, description: 'Book ID, e.g. "culpeper"' },
      { name: "question", type: "string", required: true, description: "Question text (max 500 chars)" },
    ],
    exampleRequest: `curl -X POST https://premodern-concordance.vercel.app/api/consult \\
  -H "Content-Type: application/json" \\
  -d '{"book_id":"culpeper","question":"What is the best remedy for a fever?"}'`,
    exampleResponse: `{
  "response": "A fever, being an excess of heat...",
  "evidence_used": [ { "entity_id": "fever-cl", "entity_name": "Fever", "..." : "..." } ],
  "confidence": "moderate",
  "frameworks_applied": ["Humoral medicine"]
}`,
    notes: "Powered by Gemini via a server-side API key. Rate-limited: 10 requests/min per IP.",
  },
  {
    method: "POST",
    path: "/api/translate",
    description:
      "Translate an early modern text excerpt into modern English. Rate-limited to 20 req/min per IP.",
    group: "ai",
    body: [
      { name: "text", type: "string", required: true, description: "The text to translate" },
      { name: "language", type: "string", required: true, description: 'Source language, e.g. "Portuguese", "Latin"' },
    ],
    exampleRequest: `curl -X POST https://premodern-concordance.vercel.app/api/translate \\
  -H "Content-Type: application/json" \\
  -d '{"text":"a pedra bezoar he muy estimada","language":"Portuguese"}'`,
    exampleResponse: `{
  "translation": "The bezoar stone is very highly esteemed"
}`,
    notes: "Powered by Gemini Flash Lite via a server-side API key. Rate-limited: 20 requests/min per IP.",
  },
];

const GROUP_META: Record<string, { label: string; description: string }> = {
  data: {
    label: "Data",
    description: "Free, no API keys required. Returns JSON from the concordance dataset.",
  },
  search: {
    label: "Search",
    description:
      "Semantic search uses a server-side OpenAI embedding key. Falls back to lexical matching if unavailable.",
  },
  ai: {
    label: "AI-Powered",
    description:
      "LLM endpoints use a server-side Gemini key. Rate-limited per IP to prevent abuse.",
  },
};

const METHOD_COLORS: Record<string, string> = {
  GET: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
  POST: "bg-blue-500/10 text-blue-600 dark:text-blue-400",
};

/* ───── components ───── */

function ParamTable({ params, label }: { params: Param[]; label: string }) {
  return (
    <div className="mt-3">
      <p className="text-[10px] uppercase tracking-widest text-[var(--muted)] font-medium mb-1.5">
        {label}
      </p>
      <div className="border border-[var(--border)] rounded-md overflow-hidden text-xs">
        <table className="w-full">
          <thead>
            <tr className="bg-[var(--border)]/30">
              <th className="text-left px-3 py-1.5 font-medium">Name</th>
              <th className="text-left px-3 py-1.5 font-medium">Type</th>
              <th className="text-left px-3 py-1.5 font-medium">Description</th>
            </tr>
          </thead>
          <tbody>
            {params.map((p) => (
              <tr key={p.name} className="border-t border-[var(--border)]">
                <td className="px-3 py-1.5 font-mono whitespace-nowrap">
                  {p.name}
                  {p.required && (
                    <span className="text-red-500 ml-0.5">*</span>
                  )}
                </td>
                <td className="px-3 py-1.5 text-[var(--muted)]">{p.type}</td>
                <td className="px-3 py-1.5 text-[var(--muted)]">
                  {p.description}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function EndpointCard({ ep }: { ep: Endpoint }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="bg-[var(--card)] border border-[var(--border)] rounded-lg overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full text-left px-5 py-4 flex items-start gap-3 hover:bg-[var(--border)]/20 transition-colors cursor-pointer"
      >
        <code
          className={`text-[11px] font-mono font-semibold px-2 py-0.5 rounded shrink-0 mt-0.5 ${METHOD_COLORS[ep.method]}`}
        >
          {ep.method}
        </code>
        <div className="flex-1 min-w-0">
          <code className="text-sm font-mono">{ep.path}</code>
          <p className="text-xs text-[var(--muted)] mt-0.5">
            {ep.description}
          </p>
        </div>
        <span className="text-[var(--muted)] text-xs shrink-0 mt-1">
          {expanded ? "collapse" : "expand"}
        </span>
      </button>

      {expanded && (
        <div className="px-5 pb-5 border-t border-[var(--border)] pt-4 space-y-4">
          {ep.params && ep.params.length > 0 && (
            <ParamTable
              params={ep.params}
              label={ep.params[0]?.required ? "Path / Query Parameters" : "Query Parameters"}
            />
          )}
          {ep.body && ep.body.length > 0 && (
            <ParamTable params={ep.body} label="Request Body (JSON)" />
          )}

          {ep.notes && (
            <p className="text-xs text-[var(--muted)] italic">{ep.notes}</p>
          )}

          {ep.exampleRequest && (
            <div>
              <p className="text-[10px] uppercase tracking-widest text-[var(--muted)] font-medium mb-1.5">
                Example Request
              </p>
              <pre className="bg-[var(--background)] border border-[var(--border)] rounded-md p-3 text-xs font-mono overflow-x-auto whitespace-pre-wrap break-all leading-relaxed">
                {ep.exampleRequest}
              </pre>
            </div>
          )}

          <div>
            <p className="text-[10px] uppercase tracking-widest text-[var(--muted)] font-medium mb-1.5">
              Example Response
            </p>
            <pre className="bg-[var(--background)] border border-[var(--border)] rounded-md p-3 text-xs font-mono overflow-x-auto whitespace-pre leading-relaxed max-h-64 overflow-y-auto">
              {ep.exampleResponse}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}

/* ───── page ───── */

export default function DevelopersPage() {
  const groups = ["data", "search", "ai"] as const;

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
      {/* Header */}
      <div className="mb-10 animate-fade-up delay-0">
        <h1 className="text-3xl font-semibold tracking-tight mb-2">
          Developer API
        </h1>
        <p className="text-[var(--muted)] max-w-xl">
          Programmatic access to the Premodern Concordance — entities,
          clusters, search, and AI-powered historical consultation.
        </p>
      </div>

      {/* Status */}
      <div className="bg-[var(--card)] border border-[var(--border)] rounded-lg p-5 mb-10 animate-fade-up delay-1">
        <div className="flex items-center gap-3">
          <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
          <span className="text-sm font-medium">API available</span>
        </div>
        <p className="text-xs text-[var(--muted)] mt-2 leading-relaxed">
          All endpoints below are live. No authentication required — this is a
          public academic resource. CORS is enabled for all origins.
        </p>
      </div>

      {/* Base URL */}
      <div className="bg-[var(--card)] border border-[var(--border)] rounded-lg p-5 mb-10 animate-fade-up delay-1">
        <p className="text-[10px] uppercase tracking-widest text-[var(--muted)] font-medium mb-2">
          Base URL
        </p>
        <code className="text-sm font-mono select-all">
          https://premodern-concordance.vercel.app
        </code>
      </div>

      {/* Endpoint groups */}
      {groups.map((groupKey) => {
        const meta = GROUP_META[groupKey];
        const eps = ENDPOINTS.filter((ep) => ep.group === groupKey);
        return (
          <section key={groupKey} className="mb-10 animate-fade-up delay-2">
            <div className="mb-4">
              <h2 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium">
                {meta.label} Endpoints
              </h2>
              <p className="text-xs text-[var(--muted)] mt-1">
                {meta.description}
              </p>
            </div>
            <div className="space-y-3">
              {eps.map((ep) => (
                <EndpointCard key={ep.path} ep={ep} />
              ))}
            </div>
          </section>
        );
      })}

      {/* Static data note */}
      <section className="mb-10 animate-fade-up delay-3">
        <h2 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-3">
          Static Data Files
        </h2>
        <p className="text-xs text-[var(--muted)] leading-relaxed">
          The full dataset is also available as static JSON at{" "}
          <code className="bg-[var(--border)] px-1.5 py-0.5 rounded font-mono text-[11px]">
            /data/concordance.json
          </code>{" "}
          (~18 MB),{" "}
          <code className="bg-[var(--border)] px-1.5 py-0.5 rounded font-mono text-[11px]">
            /data/entity_registry.json
          </code>
          , and{" "}
          <code className="bg-[var(--border)] px-1.5 py-0.5 rounded font-mono text-[11px]">
            /data/search_index.json
          </code>
          . These are cached with a 24-hour TTL.
        </p>
      </section>

      {/* CORS */}
      <section className="mb-10 animate-fade-up delay-3">
        <h2 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-3">
          CORS
        </h2>
        <p className="text-xs text-[var(--muted)] leading-relaxed">
          All <code className="bg-[var(--border)] px-1 py-0.5 rounded font-mono text-[11px]">/api/*</code> routes
          return <code className="bg-[var(--border)] px-1 py-0.5 rounded font-mono text-[11px]">Access-Control-Allow-Origin: *</code>.
          POST endpoints support OPTIONS preflight.
        </p>
      </section>

      {/* Rate limits */}
      <section className="mb-10 animate-fade-up delay-4">
        <h2 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-3">
          Rate Limits
        </h2>
        <p className="text-xs text-[var(--muted)] leading-relaxed">
          Data and search endpoints are not rate-limited. AI-powered endpoints
          are limited per IP:{" "}
          <code className="bg-[var(--border)] px-1 py-0.5 rounded font-mono text-[11px]">/api/consult</code> at 10
          req/min,{" "}
          <code className="bg-[var(--border)] px-1 py-0.5 rounded font-mono text-[11px]">/api/translate</code> at
          20 req/min. Exceeding returns{" "}
          <code className="bg-[var(--border)] px-1 py-0.5 rounded font-mono text-[11px]">429</code> with a{" "}
          <code className="bg-[var(--border)] px-1 py-0.5 rounded font-mono text-[11px]">Retry-After</code> header.
        </p>
      </section>

      {/* Footer */}
      <section className="animate-fade-up delay-4">
        <p className="text-sm text-[var(--muted)]">
          Questions or feature requests?{" "}
          <a
            href="https://github.com/bgreen-litai/premodern-concordance"
            target="_blank"
            rel="noopener noreferrer"
            className="underline underline-offset-2 decoration-[var(--border)] hover:text-[var(--foreground)] transition-colors"
          >
            Open an issue on GitHub
          </a>
          .
        </p>
      </section>
    </div>
  );
}
