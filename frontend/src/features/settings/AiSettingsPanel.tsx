import { useState } from "react";

import { AiConnectionsPanel } from "./AiConnectionsPanel";
import { CompanyProfilePanel } from "./CompanyProfilePanel";
import { DataForSeoPanel } from "./DataForSeoPanel";
import { PagePackageSettingsPanel } from "./PagePackageSettingsPanel";
import { ProjectAiPolicyPanel } from "./ProjectAiPolicyPanel";
import { WordPressBridgePanel } from "./WordPressBridgePanel";

export function AiSettingsPanel({
  organizationId,
  projectId,
}: {
  organizationId: string;
  projectId: string;
}) {
  const [connectionsRevision, setConnectionsRevision] = useState(0);

  return (
    <div className="ai-settings">
      <WordPressBridgePanel projectId={projectId} />
      <PagePackageSettingsPanel projectId={projectId} />
      <DataForSeoPanel organizationId={organizationId} />
      <AiConnectionsPanel
        organizationId={organizationId}
        onConnectionsChange={() =>
          setConnectionsRevision((revision) => revision + 1)
        }
      />
      <ProjectAiPolicyPanel
        organizationId={organizationId}
        projectId={projectId}
        connectionsRevision={connectionsRevision}
      />
      <CompanyProfilePanel projectId={projectId} />
    </div>
  );
}
