import { Check, ChevronDown, Pencil, Plus, Trash2 } from "lucide-react";
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
  onDelete: (projectId: string) => void;
  onRename: (projectId: string, name: string) => void;
};

export function ProjectSwitcher({
  projects,
  activeProjectId,
  onSelect,
  onCreate,
  onDelete,
  onRename,
}: ProjectSwitcherProps) {
  const [open, setOpen] = useState(false);
  const [deleteProjectId, setDeleteProjectId] = useState<string | null>(null);
  const [editingProjectId, setEditingProjectId] = useState<string | null>(null);
  const [draftName, setDraftName] = useState("");
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
            <div className="project-row" key={project.id}>
              <button
                className="project-option"
                type="button"
                role="menuitem"
                onClick={() => {
                  onSelect(project.id);
                  setDeleteProjectId(null);
                  setEditingProjectId(null);
                  setOpen(false);
                }}
              >
                <span>
                  <strong>{project.name}</strong>
                  <small>{project.domain.replace(/^https?:\/\//, "")}</small>
                </span>
                {project.id === activeProjectId && <Check size={16} />}
              </button>
              <div className="project-row-actions">
                <button
                  aria-label={`Projectnaam wijzigen voor ${project.name}`}
                  className="project-icon-action"
                  type="button"
                  onClick={() => {
                    setEditingProjectId(project.id);
                    setDeleteProjectId(null);
                    setDraftName(project.name);
                  }}
                >
                  <Pencil size={14} />
                </button>
                <button
                  aria-label={`Project verwijderen voor ${project.name}`}
                  className="project-icon-action danger"
                  type="button"
                  onClick={() => {
                    setDeleteProjectId(project.id);
                    setEditingProjectId(null);
                  }}
                >
                  <Trash2 size={14} />
                </button>
              </div>
              {editingProjectId === project.id && (
                <div className="project-manage-panel">
                  <label>
                    Projectnaam
                    <input
                      value={draftName}
                      onChange={(event) => setDraftName(event.target.value)}
                    />
                  </label>
                  <div>
                    <button
                      className="project-save"
                      type="button"
                      onClick={() => {
                        const nextName = draftName.trim();
                        if (!nextName) return;
                        onRename(project.id, nextName);
                        setEditingProjectId(null);
                        setOpen(false);
                      }}
                    >
                      Naam opslaan
                    </button>
                    <button
                      className="project-cancel"
                      type="button"
                      onClick={() => setEditingProjectId(null)}
                    >
                      Annuleren
                    </button>
                  </div>
                </div>
              )}
              {deleteProjectId === project.id && (
                <div className="project-delete-confirm">
                  <p>Weet je zeker dat je dit project wilt verwijderen?</p>
                  <div>
                    <button
                      className="project-delete"
                      type="button"
                      onClick={() => {
                        onDelete(project.id);
                        setDeleteProjectId(null);
                        setOpen(false);
                      }}
                    >
                      Ja, verwijderen
                    </button>
                    <button
                      className="project-cancel"
                      type="button"
                      onClick={() => setDeleteProjectId(null)}
                    >
                      Annuleren
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
          <button
            className="project-create"
            type="button"
            onClick={() => {
              onCreate();
              setDeleteProjectId(null);
              setEditingProjectId(null);
              setOpen(false);
            }}
          >
            <Plus size={16} />
            Nieuw project
          </button>
        </div>
      )}
    </div>
  );
}
