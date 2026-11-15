import { getDb, publicSettings } from "@/lib/store";
import { PageHead, Topbar, Crumbs } from "@/components/ui";
import { IntegrationsForm } from "@/components/IntegrationsForm";

export const dynamic = "force-dynamic";

export default function IntegrationsPage() {
  const db = getDb();
  return (
    <>
      <Topbar>
        <Crumbs items={[{ label: "Registrar console" }, { label: "Integrations" }]} />
      </Topbar>

      <div className="content">
        <PageHead
          eyebrow="Platform"
          title="Integrations"
          subtitle="The console writes to the same systems the AthenIQ stack already runs: the Open edX course engine, Signara for signing, and the OmniRoute model gateway."
        />
        <IntegrationsForm settings={publicSettings(db.settings)} />
      </div>
    </>
  );
}
