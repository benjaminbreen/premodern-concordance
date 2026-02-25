import { readFileSync } from "fs";
import { join } from "path";

export interface ClusterMember {
  entity_id: string;
  book_id: string;
  name: string;
  category: string;
  subcategory: string;
  count: number;
  variants: string[];
  contexts: string[];
}

export interface ClusterEdge {
  source_book: string;
  source_name: string;
  target_book: string;
  target_name: string;
  similarity: number;
}

export interface GroundTruth {
  modern_name: string;
  confidence: string;
  type: string;
  wikidata_id?: string;
  wikidata_description?: string;
  wikipedia_url?: string;
  linnaean?: string;
  family?: string;
  birth_year?: number;
  death_year?: number;
  description?: string;
  country?: string;
  modern_term?: string;
  note?: string;
  portrait_url?: string;
  semantic_gloss?: string;
}

export interface CrossReference {
  found_name: string;
  link_type: string;
  link_strength: number;
  target_cluster_id: number | null;
  target_cluster_name: string | null;
  source_book: string;
  evidence_snippet: string;
  confidence: number;
  auto_label: string;
  found_relationship: string;
  is_reverse?: boolean;
}

export interface Cluster {
  id: number;
  stable_key?: string;
  canonical_name: string;
  category: string;
  subcategory: string;
  book_count: number;
  total_mentions: number;
  members: ClusterMember[];
  edges: ClusterEdge[];
  ground_truth?: GroundTruth;
  cross_references?: CrossReference[];
}

export interface BookMeta {
  id: string;
  title: string;
  author: string;
  year: number;
  language: string;
}

export interface ConcordanceData {
  metadata: {
    created: string;
    threshold: number;
    enriched?: boolean;
    enrichment_model?: string;
  };
  books: BookMeta[];
  stats: {
    total_clusters: number;
    entities_matched: number;
    clusters_all_books: number;
    by_category: Record<string, number>;
    enriched_clusters?: number;
    with_wikidata?: number;
    with_wikipedia?: number;
    with_linnaean?: number;
  };
  clusters: Cluster[];
}

export interface NeighborEntry {
  id: number;
  sim: number;
}

export interface NeighborGraph {
  k: number;
  count: number;
  neighbors: Record<string, NeighborEntry[]>;
}

// ── Module-level caches ─────────────────────────────────────────────

let cachedConcordance: ConcordanceData | null = null;
let cachedNeighbors: NeighborGraph | null = null;

export function getConcordance(): ConcordanceData {
  if (cachedConcordance) return cachedConcordance;
  const raw = readFileSync(join(process.cwd(), "public", "data", "concordance.json"), "utf-8");
  cachedConcordance = JSON.parse(raw) as ConcordanceData;
  return cachedConcordance;
}

export function getNeighborGraph(): NeighborGraph {
  if (cachedNeighbors) return cachedNeighbors;
  const raw = readFileSync(join(process.cwd(), "public", "data", "cluster_neighbors.json"), "utf-8");
  cachedNeighbors = JSON.parse(raw) as NeighborGraph;
  return cachedNeighbors;
}

// ── Slug helpers ────────────────────────────────────────────────────

function slugify(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

export function clusterSlug(cluster: Cluster, allClusters: Cluster[]): string {
  if (cluster.stable_key) return cluster.stable_key;
  const base = slugify(cluster.canonical_name);
  const hasCollision = allClusters.some(
    (c) => c.id !== cluster.id && slugify(c.canonical_name) === base
  );
  return hasCollision ? `${base}-${cluster.id}` : base;
}

export function findClusterBySlug(
  slug: string,
  clusters: Cluster[]
): Cluster | null {
  const stable = clusters.find((c) => c.stable_key === slug);
  if (stable) return stable;

  const baseMatches = clusters.filter(
    (c) => slugify(c.canonical_name) === slug
  );
  if (baseMatches.length === 1) return baseMatches[0];

  const idMatch = slug.match(/-(\d+)$/);
  if (idMatch) {
    const id = Number(idMatch[1]);
    const found = clusters.find((c) => c.id === id);
    if (found) return found;
  }

  return null;
}
