import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Block backup and intermediate data files from being served
  if (pathname.startsWith("/data/")) {
    const filename = pathname.split("/").pop() || "";

    // Block .bak files, .pre- files, pre_ prefixed backups, tuned_ files,
    // and entity_registry.json (77MB — bundled into serverless functions
    // for API routes but must not be served publicly to avoid bandwidth abuse).
    if (
      filename === "entity_registry.json" ||
      filename.includes(".bak") ||
      filename.includes(".pre-cleanup") ||
      filename.includes(".pre_") ||
      filename.startsWith("concordance.pre_") ||
      filename.startsWith("concordance.tuned_") ||
      filename.startsWith("concordance_pre_")
    ) {
      return new NextResponse(null, { status: 404 });
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/data/:path*"],
};
