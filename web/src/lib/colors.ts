/**
 * Canonical category color definitions.
 * Import from here instead of defining locally.
 */

/** Preferred display order for categories (general-purpose). */
export const CATEGORY_ORDER: string[] = [
  "PERSON",
  "CONCEPT",
  "SUBSTANCE",
  "PLANT",
  "ANIMAL",
  "ANATOMY",
  "DISEASE",
  "PLACE",
  "ORGANIZATION",
  "OBJECT",
];

/** Stream-chart display order (sorted by typical cluster count). */
export const CATEGORY_ORDER_STREAM: string[] = [
  "PLACE",
  "SUBSTANCE",
  "PLANT",
  "CONCEPT",
  "DISEASE",
  "PERSON",
  "ANIMAL",
  "OBJECT",
  "ORGANIZATION",
];

/** Hex color per category — use in SVGs, canvas, inline styles. */
export const CAT_HEX: Record<string, string> = {
  PERSON: "#a855f7",
  PLANT: "#10b981",
  ANIMAL: "#84cc16",
  SUBSTANCE: "#06b6d4",
  CONCEPT: "#f59e0b",
  DISEASE: "#ef4444",
  PLACE: "#22c55e",
  OBJECT: "#64748b",
  ANATOMY: "#f43f5e",
  ORGANIZATION: "#ec4899",
};

/** Tailwind badge classes per category — use on <span> badges. */
export const CAT_BADGE: Record<string, string> = {
  PERSON: "bg-purple-500/20 text-purple-600 dark:text-purple-400 border-purple-500/30",
  PLANT: "bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 border-emerald-500/30",
  ANIMAL: "bg-lime-500/20 text-lime-600 dark:text-lime-400 border-lime-500/30",
  SUBSTANCE: "bg-cyan-500/20 text-cyan-600 dark:text-cyan-400 border-cyan-500/30",
  CONCEPT: "bg-amber-500/20 text-amber-600 dark:text-amber-400 border-amber-500/30",
  DISEASE: "bg-red-500/20 text-red-600 dark:text-red-400 border-red-500/30",
  PLACE: "bg-green-500/20 text-green-600 dark:text-green-400 border-green-500/30",
  OBJECT: "bg-slate-500/20 text-slate-600 dark:text-slate-400 border-slate-500/30",
  ANATOMY: "bg-rose-500/20 text-rose-600 dark:text-rose-400 border-rose-500/30",
  ORGANIZATION: "bg-pink-500/20 text-pink-600 dark:text-pink-400 border-pink-500/30",
};

/** Tailwind dot/bar class per category — use on small indicators. */
export const CAT_DOT: Record<string, string> = {
  PERSON: "bg-purple-500",
  PLANT: "bg-emerald-500",
  ANIMAL: "bg-lime-500",
  SUBSTANCE: "bg-cyan-500",
  CONCEPT: "bg-amber-500",
  DISEASE: "bg-red-500",
  PLACE: "bg-green-500",
  OBJECT: "bg-slate-500",
  ANATOMY: "bg-rose-500",
  ORGANIZATION: "bg-pink-500",
};

/** Composite badge+dot — common pattern across the app. */
export const CATEGORY_COLORS: Record<string, { badge: string; dot: string }> =
  Object.fromEntries(
    Object.keys(CAT_BADGE).map((k) => [k, { badge: CAT_BADGE[k], dot: CAT_DOT[k] }])
  );

/** RGBA tint overlays per category (0.25 alpha). */
export const CAT_TINT: Record<string, string> = {
  PERSON: "rgba(147, 51, 234, 0.25)",
  PLANT: "rgba(16, 185, 129, 0.25)",
  ANIMAL: "rgba(132, 204, 22, 0.25)",
  SUBSTANCE: "rgba(6, 182, 212, 0.25)",
  CONCEPT: "rgba(245, 158, 11, 0.25)",
  DISEASE: "rgba(239, 68, 68, 0.25)",
  PLACE: "rgba(34, 197, 94, 0.25)",
  OBJECT: "rgba(100, 116, 139, 0.25)",
  ANATOMY: "rgba(244, 63, 94, 0.25)",
  ORGANIZATION: "rgba(236, 72, 153, 0.25)",
};
