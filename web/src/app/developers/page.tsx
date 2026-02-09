"use client";

const SCHEMA_PREVIEW = `{
  "metadata": { "created": "...", "threshold": 0.84 },
  "books": [
    { "id": "...", "title": "...", "author": "...", "year": 1652, "language": "English" }
  ],
  "stats": { "total_clusters": 1491, "by_category": { ... } },
  "clusters": [
    {
      "id": 1,
      "canonical_name": "Mercury",
      "category": "SUBSTANCE",
      "book_count": 4,
      "total_mentions": 87,
      "members": [ { "book_id": "...", "name": "...", "count": 12, ... } ],
      "edges": [ { "source_book": "...", "target_book": "...", "similarity": 0.94 } ]
    }
  ]
}`;

const ENDPOINTS = [
  {
    method: "GET",
    path: "/api/clusters",
    description: "List all clusters with optional category and book filters.",
  },
  {
    method: "GET",
    path: "/api/clusters/:id",
    description: "Retrieve a single cluster by ID, including members and edges.",
  },
  {
    method: "GET",
    path: "/api/books",
    description: "List all books in the corpus with metadata.",
  },
  {
    method: "GET",
    path: "/api/search",
    description: "Semantic search across clusters using text-embedding-3-small.",
  },
];

export default function DevelopersPage() {
  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
      {/* Header */}
      <div className="mb-12 animate-fade-up delay-0">
        <h1 className="text-3xl font-semibold tracking-tight mb-2">
          Developer API
        </h1>
        <p className="text-[var(--muted)] max-w-xl">
          Programmatic access to the Premodern Concordance.
        </p>
      </div>

      {/* Status */}
      <div className="bg-[var(--card)] border border-[var(--border)] rounded-lg p-6 mb-12 animate-fade-up delay-1">
        <div className="flex items-center gap-3">
          <span className="w-2.5 h-2.5 rounded-full bg-amber-500 animate-pulse" />
          <span className="text-sm font-medium">The API is under development.</span>
        </div>
        <p className="text-sm text-[var(--muted)] mt-2">
          The concordance data is currently available as a static JSON file at{" "}
          <code className="text-xs bg-[var(--border)] px-1.5 py-0.5 rounded font-mono">
            /data/concordance.json
          </code>
          . A REST API with filtering, pagination, and semantic search is planned.
        </p>
      </div>

      {/* Schema Preview */}
      <section className="mb-12 animate-fade-up delay-2">
        <h2 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-4">
          Data Schema
        </h2>
        <pre className="bg-[var(--card)] border border-[var(--border)] rounded-lg p-6 overflow-x-auto text-xs font-mono leading-relaxed text-[var(--foreground)]">
          {SCHEMA_PREVIEW}
        </pre>
      </section>

      {/* Planned Endpoints */}
      <section className="mb-12 animate-fade-up delay-3">
        <h2 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-4">
          Planned Endpoints
        </h2>
        <div className="space-y-3">
          {ENDPOINTS.map((ep) => (
            <div
              key={ep.path}
              className="bg-[var(--card)] border border-[var(--border)] rounded-lg p-4 flex items-start gap-4"
            >
              <code className="text-xs font-mono bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 px-2 py-0.5 rounded shrink-0">
                {ep.method}
              </code>
              <div className="flex-1 min-w-0">
                <code className="text-sm font-mono">{ep.path}</code>
                <p className="text-xs text-[var(--muted)] mt-1">
                  {ep.description}
                </p>
              </div>
              <span className="text-xs bg-amber-500/10 text-amber-600 dark:text-amber-400 px-2 py-0.5 rounded shrink-0">
                Coming soon
              </span>
            </div>
          ))}
        </div>
      </section>

      {/* Feedback */}
      <section className="animate-fade-up delay-4">
        <p className="text-sm text-[var(--muted)]">
          Questions or feature requests?{" "}
          <a
            href="https://github.com"
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
