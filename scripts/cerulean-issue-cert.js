/**
 * Issue (or re-issue) one certificate through Cerulean's own ACME path.
 *
 * Cerulean is the deployment's certificate authority of record: it solves a
 * Technitium DNS-01 challenge, stores the material in its database and uploads
 * it to NPM (see `docs/Deployment.md` §"Cerulean DNS and TLS"). Its HTTP API
 * needs a signed-in session, and new public names are added by an operator, so
 * this runs the same code path from inside the cerulean container — the same
 * decision, with operator access, instead of break-glass enabling password
 * sign-in on the edge.
 *
 *   scp scripts/cerulean-issue-cert.js proxy:/tmp/
 *   ssh proxy incus exec ... # or on the proxy host:
 *   docker cp /tmp/cerulean-issue-cert.js cerulean:/tmp/
 *   docker exec -e DOMAIN=ai.lms.innotel.us cerulean node /tmp/cerulean-issue-cert.js
 *
 * Idempotent: an existing row for the same exact name is re-issued rather than
 * duplicated, and a wildcard is never touched. The certificate still has to be
 * uploaded to NPM separately (`scripts/npm-upload-cert.py`) because NPM is what
 * terminates TLS, and then pointed at a proxy host.
 *
 * This box-wide script is deliberately not `require`d by anything: it is an
 * operator tool, run once per new name.
 */
const db = require("/app/server/dist/db.js").db;
const { runIssueJob } = require("/app/server/dist/jobs.js");

const DOMAIN = (process.env.DOMAIN || "").trim().toLowerCase();
if (!DOMAIN) {
  console.error("set DOMAIN=<hostname>");
  process.exit(2);
}

function show(label, row) {
  console.log(label, JSON.stringify({
    id: row.id, name: row.name, domain: row.domain, wildcard: row.wildcard,
    status: row.status, strategy: row.strategy, expires_at: row.expires_at,
  }));
}

(async () => {
  let row = db.listCertificates().find((c) => c.domain === DOMAIN && !c.wildcard);
  if (!row) {
    row = db.createCertificate({ name: `${DOMAIN} certificate`, domain: DOMAIN, wildcard: false });
    console.log("created certificate row");
  } else {
    console.log("existing certificate row");
  }
  const before = db.getCertificate(row.id);
  show("before:", before);
  if (before && before.status === "issued" && process.env.REISSUE !== "1") {
    console.log("already issued — set REISSUE=1 to force a new order");
    return;
  }

  await runIssueJob(row.id);

  const after = db.getCertificate(row.id);
  show("after: ", after);
  if (!after || after.status !== "issued") {
    console.error("issuance did not reach 'issued'");
    process.exit(1);
  }
  console.log("issued certificate id =", after.id);
})().catch((err) => {
  console.error("issuance failed:", err && err.message ? err.message : err);
  process.exit(1);
});
