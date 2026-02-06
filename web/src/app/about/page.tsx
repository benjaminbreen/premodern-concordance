export default function AboutPage() {
  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
      {/* Title */}
      <h1 className="text-3xl font-bold mb-3">About</h1>
      <p className="text-[var(--muted)] max-w-2xl mb-12 leading-relaxed">
        The Premodern Concordance is a prototype for a larger project that will use
        computational methods to link named entities &mdash; people, plants,
        substances, places, diseases, and concepts &mdash; across multilingual
        early modern texts relating to natural and scientific knowledge. The goal is to make the unstable, polyglot terminology
        of premodern natural knowledge searchable and comparable across languages,
        centuries, and traditions, and then to explore new research possibilities and questions unlocked by this.
      </p>

      {/* Personnel */}
      <section className="mb-16">
        <h2 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-6">
          Personnel
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-8">
          <div>
            <h3 className="font-semibold mb-1">Benjamin Breen</h3>
            <p className="text-sm text-[var(--muted)]">
              Department of History, UC Santa Cruz
            </p>
          </div>
          <div>
            <h3 className="font-semibold mb-1">Mackenzie Cooley</h3>
            <p className="text-sm text-[var(--muted)]">
              Department of History, Hamilton College
            </p>
          </div>
        </div>
      </section>

      {/* Colophon */}
      <section>
        <h2 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-6">
          Colophon
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-12 gap-y-6 text-sm">
          <div>
            <h3 className="font-semibold mb-2">Typography</h3>
            <ul className="text-[var(--muted)] space-y-1">
              <li>
                <span className="text-[var(--foreground)]">System UI</span> &mdash; body text
              </li>
              <li>
                <span className="text-[var(--foreground)]" style={{ fontFamily: "'UnifrakturMaguntia', cursive" }}>UnifrakturMaguntia</span> &mdash; logotype, blackletter display
              </li>
              <li>
                <span className="text-[var(--foreground)]" style={{ fontFamily: "'EB Garamond', serif" }}>EB Garamond</span> &mdash; early modern serif
              </li>
              <li>
                <span className="text-[var(--foreground)]" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>Space Grotesk</span> &mdash; geometric display
              </li>
            </ul>
          </div>
          <div>
            <h3 className="font-semibold mb-2">Framework</h3>
            <ul className="text-[var(--muted)] space-y-1">
              <li>
                <span className="text-[var(--foreground)]">Next.js 16</span> &mdash; React framework
              </li>
              <li>
                <span className="text-[var(--foreground)]">Tailwind CSS 4</span> &mdash; styling
              </li>
              <li>
                <span className="text-[var(--foreground)]">Vercel</span> &mdash; hosting
              </li>
            </ul>
          </div>
          <div>
            <h3 className="font-semibold mb-2">Research models</h3>
            <ul className="text-[var(--muted)] space-y-1">
              <li>
                <span className="text-[var(--foreground)]">BGE-M3</span> &mdash; fine-tuned cross-lingual embeddings for entity matching (current model was fine-tuned on 500 matched multi-lingual pairs of early modern natural concepts/terms)
              </li>
              <li>
                <span className="text-[var(--foreground)]">Google Gemini 2.5 Flash Lite</span> &mdash; entity extraction, enrichment, and verification
              </li>
              <li>
                <span className="text-[var(--foreground)]">OpenAI text-embedding-3-small</span> &mdash; semantic search index
              </li>
            </ul>
          </div>
          <div>
            <h3 className="font-semibold mb-2">Site code</h3>
            <p className="text-[var(--muted)]">
              Built with assistance from{" "}
              <a
                href="https://claude.ai/claude-code"
                target="_blank"
                rel="noopener noreferrer"
                className="text-[var(--foreground)] underline underline-offset-2 decoration-[var(--border)] hover:decoration-[var(--foreground)] transition-colors"
              >
                Claude Code
              </a>{" "}
              (Claude Opus 4.5).
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}
