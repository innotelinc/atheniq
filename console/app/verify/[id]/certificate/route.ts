import { certificateDocument, withheldResponse } from "@/lib/certificate";

export const dynamic = "force-dynamic";

/**
 * The document itself, at a path anyone holding the verification id can open.
 *
 * It lives under `/verify` rather than `/api/credentials` on purpose: the edge
 * puts its single sign-on in front of the console and lets only a short list of
 * paths through without a session, `/verify` among them. A graduate's link on a
 * résumé — or an employer's download from a verification result — is a public
 * read, so it has to sit where the public is answered.
 */
export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const download = new URL(request.url).searchParams.get("download") === "1";
  const lookup = certificateDocument(id, download);

  if (lookup.kind === "document") return lookup.response;

  return (
    withheldResponse(lookup) ??
    new Response("No credential matches that verification id.\n", { status: 404 })
  );
}
