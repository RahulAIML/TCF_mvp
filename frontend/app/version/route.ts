import { NextResponse } from "next/server";

/** Which frontend build is live. Render injects RENDER_GIT_COMMIT; anything else reports "dev". */
export function GET() {
  const commit = process.env.RENDER_GIT_COMMIT || process.env.GIT_COMMIT || "dev";
  return NextResponse.json({ service: "tcf-frontend", commit });
}
