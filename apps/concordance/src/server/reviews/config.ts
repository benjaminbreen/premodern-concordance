import "server-only";

export function reviewModeEnabled(): boolean {
  return process.env.NODE_ENV !== "production"
    || process.env.ENABLE_HISTORIAN_REVIEW === "1";
}

export function reviewModeReviewer(): string {
  return process.env.HISTORIAN_REVIEWER_NAME?.trim() || "Benjamin Breen";
}
