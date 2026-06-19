import { useState } from "react";

import { AiConnectionsPanel } from "./AiConnectionsPanel";
import { CompanyProfilePanel } from "./CompanyProfilePanel";
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
