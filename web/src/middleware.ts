import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Block backup and intermediate data files from being served
  if (pathname.startsWith("/data/")) {
    const filename = pathname.split("/").pop() || "";

    // Block .bak files, .pre- files, pre_ prefixed backups, tuned_ files
    if (
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
