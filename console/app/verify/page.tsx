import Link from "next/link";
import { redirect } from "next/navigation";
import { getDb } from "@/lib/store";
import { shortDate } from "@/lib/format";
import { Badge, Card, PageHead, Topbar, Crumbs } from "@/components/ui";

export const dynamic = "force-dynamic";

export default async function VerifyPage({
  searchParams,
}: {
  searchParams: Promise<{ id?: string }>;
}) {
  const params = await searchParams;
  const id = (params.id ?? "").trim();
  if (id) redirect(`/verify/${id}`);

  const db = getDb();
  const issued = db.credentials
    .filter((c) => ["issued", "signed", "revoked"].includes(c.status))
    .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
    .slice(0, 12);

  return (
    <>
      <Topbar>
        <Crumbs items={[{ label: db.settings.brand.siteName }, { label: "Verification" }]} />
        <Link className="btn small ghost" href="/credentials">
          Credential center
        </Link>
      </Topbar>

      <div className="content">
        <PageHead
          eyebrow="Trust"
          title="Verify a credential"
          subtitle="Employers and licensure boards check an award at the source: the verification id printed on the certificate resolves to the signed record."
        />

        <Card>
          <form method="get" action="/verify" className="card-body">
            <div className="row">
              <input
                className="input"
                style={{ maxWidth: 420 }}
                name="id"
                placeholder="Verification id, e.g. 7f3c1a92e5b44d0a9c6e2b81"
                aria-label="Verification id"
                required
              />
              <button className="btn primary" type="submit">
                Verify
              </button>
            </div>
          </form>
        </Card>

        <Card title="Recently issued" className="mt">
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Credential</th>
                  <th>Learner</th>
                  <th>Status</th>
                  <th>Date</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {issued.map((credential) => (
                  <tr key={credential.id}>
                    <td className="strong">{credential.subjectLabel}</td>
                    <td className="small">{credential.learner.name}</td>
                    <td>
                      <Badge status={credential.status} />
                    </td>
                    <td className="small muted">{shortDate(credential.createdAt)}</td>
                    <td className="actions">
                      <Link className="btn small" href={`/verify/${credential.verifyId}`}>
                        Verify
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </>
  );
}
