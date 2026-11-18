import { certificateDocument, withheldResponse } from "@/lib/certificate";

export const dynamic = "force-dynamic";

/** The certificate document, rendered when it was signed. Staff path, same rule. */
export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const download = new URL(request.url).searchParams.get("download") === "1";
  const lookup = certificateDocument(id, download);

  if (lookup.kind === "document") return lookup.response;

  return (
    withheldResponse(lookup) ??
    new Response("No credential matches that id.\n", { status: 404 })
  );
}
