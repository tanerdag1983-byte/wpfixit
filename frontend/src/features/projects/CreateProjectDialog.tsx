import { X } from "lucide-react";
import { useState } from "react";

type ProjectDraft = {
  name: string;
  domain: string;
};

type CreateProjectDialogProps = {
  onClose: () => void;
  onSubmit: (project: ProjectDraft) => void;
};

export function CreateProjectDialog({
  onClose,
  onSubmit,
}: CreateProjectDialogProps) {
  const [name, setName] = useState("");
  const [domain, setDomain] = useState("");

  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onSubmit({
      name: name.trim(),
      domain: domain.trim().replace(/\/+$/, ""),
    });
  }

  return (
    <div className="dialog-backdrop">
      <section
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-project-title"
      >
        <div className="dialog-heading">
          <div>
            <p className="eyebrow">Nieuw project</p>
            <h2 id="create-project-title">Website toevoegen</h2>
          </div>
          <button
            className="icon-button"
            type="button"
            aria-label="Sluiten"
            onClick={onClose}
          >
            <X size={18} />
          </button>
        </div>
        <form onSubmit={submit}>
          <label>
            Projectnaam
            <input
              required
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Bijvoorbeeld SHM Transmissie"
            />
          </label>
          <label>
            Domein
            <input
              type="url"
              required
              value={domain}
              onChange={(event) => setDomain(event.target.value)}
              placeholder="https://voorbeeld.nl"
            />
          </label>
          <div className="dialog-actions">
            <button className="secondary-button" type="button" onClick={onClose}>
              Annuleren
            </button>
            <button className="primary-button" type="submit">
              Project aanmaken
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}

