import { Check, ChevronDown, Plus } from "lucide-react";
import { useState } from "react";

export type ProjectSummary = {
  id: string;
  organizationId: string;
  name: string;
  domain: string;
};

type ProjectSwitcherProps = {
  projects: ProjectSummary[];
  activeProjectId: string;
  onSelect: (projectId: string) => void;
  onCreate: () => void;
};

export function ProjectSwitcher({
  projects,
  activeProjectId,
  onSelect,
  onCreate,
}: ProjectSwitcherProps) {
  const [open, setOpen] = useState(false);
  const activeProject =
    projects.find((project) => project.id === activeProjectId) ?? projects[0];

  return (
    <div className="project-menu">
      <button
        className="project-switcher"
        type="button"
        aria-label="Project wijzigen"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        <span className="project-mark">
          {activeProject?.name.slice(0, 1).toUpperCase() ?? "P"}
        </span>
        <span>
          <small>Project</small>
          {activeProject?.domain.replace(/^https?:\/\//, "") ?? "Selecteer project"}
        </span>
        <ChevronDown size={16} />
      </button>

      {open && (
        <div className="project-popover" role="menu">
          <div className="project-popover-label">Jouw projecten</div>
          {projects.map((project) => (
            <button
              className="project-option"
              type="button"
              role="menuitem"
              key={project.id}
              onClick={() => onSelect(project.id)}
            >
              <span>
                <strong>{project.name}</strong>
                <small>{project.domain.replace(/^https?:\/\//, "")}</small>
              </span>
              {project.id === activeProjectId && <Check size={16} />}
            </button>
          ))}
          <button
            className="project-create"
            type="button"
            onClick={onCreate}
          >
            <Plus size={16} />
            Nieuw project
          </button>
        </div>
      )}
    </div>
  );
}
