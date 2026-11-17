import { certificateResponse } from "@/lib/certificate";
import { fail } from "@/lib/api";

export const dynamic = "force-dynamic";

/** The certificate document, rendered when it was signed. Staff path. */
export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const download = new URL(request.url).searchParams.get("download") === "1";
  return certificateResponse(id, download) ?? fail("Credential not found.", 404);
}
