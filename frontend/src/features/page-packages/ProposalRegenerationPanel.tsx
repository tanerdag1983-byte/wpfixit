import { RefreshCcw, WandSparkles } from "lucide-react";
import { useEffect, useState } from "react";

import type { BlueprintBlock } from "./proposalTypes";

type ProposalRegenerationPanelProps = {
  blocks: BlueprintBlock[];
  busy: boolean;
  onGenerateBlock: (targetBlockId: string, instruction: string) => void;
  onGenerateFull: (instruction: string) => void;
};

export function ProposalRegenerationPanel({
  blocks,
  busy,
  onGenerateBlock,
  onGenerateFull,
}: ProposalRegenerationPanelProps) {
  const [targetBlockId, setTargetBlockId] = useState(blocks[0]?.id ?? "");
  const [instruction, setInstruction] = useState("");

  useEffect(() => {
    if (!blocks.some((block) => block.id === targetBlockId)) {
      setTargetBlockId(blocks[0]?.id ?? "");
    }
  }, [blocks, targetBlockId]);

  return (
    <section className="proposal-regeneration-panel">
      <div>
        <p className="eyebrow">Genereer opnieuw</p>
        <h2>Nieuwe versie laten maken</h2>
        <p className="settings-intro">
          Voeg extra context toe voor een volledige nieuwe versie of stuur alleen een
          specifiek blok bij.
        </p>
      </div>

      <label className="proposal-regeneration-field">
        Extra instructies
        <textarea
          aria-label="Extra instructies"
          disabled={busy}
          onChange={(event) => setInstruction(event.target.value)}
          placeholder="Bijvoorbeeld: maak de intro zakelijker, voeg meer vertrouwen toe of maak de CTA directer."
          value={instruction}
        />
      </label>

      <div className="proposal-regeneration-actions">
        <button
          className="secondary-button"
          disabled={busy}
          onClick={() => onGenerateFull(instruction)}
          type="button"
        >
          <WandSparkles size={16} />
          Volledig opnieuw genereren
        </button>

        <div className="proposal-regeneration-block-row">
          <label className="proposal-regeneration-select">
            Blok kiezen
            <select
              aria-label="Blok kiezen"
              disabled={busy || blocks.length === 0}
              onChange={(event) => setTargetBlockId(event.target.value)}
              value={targetBlockId}
            >
              {blocks.map((block) => (
                <option key={block.id} value={block.id}>
                  {block.label}
                </option>
              ))}
            </select>
          </label>
          <button
            className="secondary-button"
            disabled={busy || !targetBlockId}
            onClick={() => onGenerateBlock(targetBlockId, instruction)}
            type="button"
          >
            <RefreshCcw size={16} />
            Blok opnieuw genereren
          </button>
        </div>
      </div>
    </section>
  );
}
