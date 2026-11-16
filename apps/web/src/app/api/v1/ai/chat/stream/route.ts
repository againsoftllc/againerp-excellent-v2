import { NextRequest } from "next/server";
import { proxyToApi } from "@/lib/api/proxy-to-api";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * Aladin's streamed chat. A product upload reads a whole page and writes with the AI before it answers (about 45-70 s), more than
 * the 60 s of the generic /api/v1 proxy - which cut the stream and left the browser with "No response from the model".
 */
export const maxDuration = 300;

export async function POST(req: NextRequest) {
  return proxyToApi(req, "/api/v1/ai/chat/stream");
}
