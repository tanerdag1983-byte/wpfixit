import { useEffect, useState } from "react";

export type SemanticRole =
  | "hero"
  | "introduction"
  | "benefits"
  | "process"
  | "faq"
  | "cta"
  | "content";

export type BlueprintField = {
  id: string;
  path: string;
  label: string;
  value_type: "plain_text" | "rich_text" | "heading" | "button_text" | "url";
  current_value: string;
  required: boolean;
  max_length: number;
};

export type BlueprintSchema = {
  schema_version: "blueprint-v1";
  blocks: Array<{
    id: string;
    layout: string;
    label: string;
    semantic_role: SemanticRole;
    fields: BlueprintField[];
  }>;
};

const roleLabels: Record<SemanticRole, string> = {
  hero: "Hero",
  introduction: "Introductie",
  benefits: "Voordelen / problemen",
  process: "Werkwijze",
  faq: "FAQ",
  cta: "Call-to-action",
  content: "Inhoud",
};

export function BlueprintOutline({
  schema,
  onSave,
}: {
  schema: BlueprintSchema;
  onSave: (roles: Record<string, SemanticRole>) => Promise<void>;
}) {
  const [roles, setRoles] = useState<Record<string, SemanticRole>>({});
  const [openBlocks, setOpenBlocks] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setRoles(
      Object.fromEntries(
        schema.blocks.map((block) => [block.id, block.semantic_role]),
      ),
    );
    setOpenBlocks(new Set());
  }, [schema]);

  async function save() {
    setBusy(true);
    try {
      await onSave(roles);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="blueprint-outline">
      <div className="blueprint-outline-heading">
        <div>
          <h3>Blokken en bewerkbare velden</h3>
          <p>Controleer de betekenis per blok. Builderpaden blijven vergrendeld.</p>
        </div>
        <button className="secondary-button" disabled={busy} onClick={save} type="button">
          {busy ? "Opslaan..." : "Rollen opslaan"}
        </button>
      </div>
      <p className="blueprint-preserved-note">
        Afbeeldingen, vormgeving en builderstructuur blijven behouden.
      </p>
      <div className="blueprint-block-list">
        {schema.blocks.map((block, index) => {
          const isOpen = openBlocks.has(block.id);
          return (
            <section className="blueprint-block" key={block.id}>
              <button
                aria-expanded={isOpen}
                className="blueprint-block-toggle"
                onClick={() =>
                  setOpenBlocks((current) => {
                    const next = new Set(current);
                    if (next.has(block.id)) next.delete(block.id);
                    else next.add(block.id);
                    return next;
                  })
                }
                type="button"
              >
                <span>{String(index + 1).padStart(2, "0")}</span>
                <strong>{block.label}</strong>
                <small>{block.layout}</small>
                <b aria-hidden="true">{isOpen ? "−" : "+"}</b>
              </button>
              {isOpen && (
                <div className="blueprint-block-detail">
                  <label>
                    Rol voor {block.label}
                    <select
                      value={roles[block.id] ?? block.semantic_role}
                      onChange={(event) =>
                        setRoles((current) => ({
                          ...current,
                          [block.id]: event.target.value as SemanticRole,
                        }))
                      }
                    >
                      {Object.entries(roleLabels).map(([value, label]) => (
                        <option key={value} value={value}>{label}</option>
                      ))}
                    </select>
                  </label>
                  <div className="blueprint-field-list">
                    {block.fields.map((field) => (
                      <div key={field.id}>
                        <strong>{field.label}</strong>
                        <span>{field.value_type.replace("_", " ")}</span>
                        <code>{field.path}</code>
                        <p>{field.current_value || "Nog geen standaardtekst"}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </section>
          );
        })}
      </div>
    </div>
  );
}
