import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { FindingReviewWorkbench } from "@/components/review/finding-review-workbench";
import { firstQueryValue, type QueryValue } from "@/config/query";
import { reviewModeEnabled } from "@/server/reviews/config";
import { listFindingReviewItems } from "@/server/reviews/data";
import { listLatestFindingReviews } from "@/server/reviews/store";
import styles from "./page.module.css";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Review findings",
  robots: { index: false, follow: false }
};

export default async function FindingReviewPage({
  searchParams
}: {
  searchParams: Promise<{ finding?: QueryValue }>;
}) {
  if (!reviewModeEnabled()) notFound();
  const query = await searchParams;
  const [items, reviews] = await Promise.all([
    listFindingReviewItems(),
    listLatestFindingReviews()
  ]);
  const currentFindingIds = new Set(items.map((item) => item.finding.id));
  const currentReviews = reviews.filter((review) => currentFindingIds.has(review.findingId));
  const requestedId = firstQueryValue(query.finding, "");
  const initialIndex = Math.max(0, items.findIndex((item) => item.finding.id === requestedId));
  return (
    <div className={`shell ${styles.page}`}>
      <header className={styles.header}>
        <p className="eyebrow">Private research workspace</p>
        <h1>Assess candidate findings</h1>
        <p>
          Judge evidentiary support separately from historical interest. Saves are
          append-only and retain the exact finding, claims, passages, and release you reviewed.
        </p>
      </header>
      <FindingReviewWorkbench items={items} initialReviews={currentReviews} initialIndex={initialIndex} />
    </div>
  );
}
