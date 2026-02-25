import { NextResponse } from "next/server";
import {
  getConcordance,
  getNeighborGraph,
  findClusterBySlug,
  clusterSlug,
} from "@/lib/concordanceData";

export async function GET(
  _request: Request,
  context: { params: Promise<{ slug: string }> }
) {
  const { slug } = await context.params;
  const data = getConcordance();
  const clusters = data.clusters;

  const cluster = findClusterBySlug(slug, clusters);
  if (!cluster) {
    return NextResponse.json({ error: "Cluster not found" }, { status: 404 });
  }

  // Books that appear in this cluster
  const memberBookIds = new Set(cluster.members.map((m) => m.book_id));
  const books = data.books.filter((b) => memberBookIds.has(b.id));

  // Position & navigation
  const idx = clusters.findIndex((c) => c.id === cluster.id);
  const prevCluster = idx > 0 ? clusters[idx - 1] : null;
  const nextCluster = idx < clusters.length - 1 ? clusters[idx + 1] : null;

  // Neighbor graph
  let neighbors: { id: number; slug: string; name: string; category: string; sim: number }[] = [];
  try {
    const graph = getNeighborGraph();
    const entries = graph.neighbors[String(cluster.id)] ?? [];
    neighbors = entries
      .map((entry) => {
        const neighbor = clusters.find((c) => c.id === entry.id);
        if (!neighbor) return null;
        return {
          id: neighbor.id,
          slug: clusterSlug(neighbor, clusters),
          name: neighbor.ground_truth?.modern_name || neighbor.canonical_name,
          category: neighbor.category,
          sim: entry.sim,
        };
      })
      .filter((n): n is NonNullable<typeof n> => n !== null);
  } catch {
    // neighbor graph not built — return empty
  }

  return NextResponse.json({
    cluster,
    books,
    prev_slug: prevCluster ? clusterSlug(prevCluster, clusters) : null,
    next_slug: nextCluster ? clusterSlug(nextCluster, clusters) : null,
    position: idx + 1,
    total_clusters: clusters.length,
    neighbors,
  });
}
