import type { ScoreSnapshot } from "../../lib/api";

export function ScoreFactors({
  current,
  projected,
}: {
  current: ScoreSnapshot;
  projected: ScoreSnapshot;
}) {
  const currentFactors = new Map(current.factors.map((factor) => [factor.key, factor]));
  const projectedFactors = new Map(
    projected.factors.map((factor) => [factor.key, factor]),
  );
  const keys = Array.from(
    new Set([...currentFactors.keys(), ...projectedFactors.keys()]),
  );

  return (
    <section aria-labelledby="score-factors-heading" className="package-section">
      <h2 id="score-factors-heading">Verklaarbare scorefactoren</h2>
      <div className="blueprint-review-summary">
        <div><span>Huidige score</span><strong>Huidige score {current.overall_score}</strong></div>
        <div><span>Na dit voorstel</span><strong>Verwachte score {projected.overall_score}</strong></div>
      </div>
      <div aria-label="Scorefactoren" className="crawl-history" role="table">
        <div className="crawl-history-row header" role="row">
          <span role="columnheader">Factor</span>
          <span role="columnheader">Huidig</span>
          <span role="columnheader">Voorgesteld</span>
          <span role="columnheader">Uitleg</span>
        </div>
        {keys.map((key) => {
          const before = currentFactors.get(key);
          const after = projectedFactors.get(key);
          return (
            <div className="crawl-history-row" key={key} role="row">
              <strong role="cell">{factorLabel(key)}</strong>
              <span role="cell">{pointsLabel(before?.points, before?.max_points)}</span>
              <span role="cell">{pointsLabel(after?.points, after?.max_points)}</span>
              <small role="cell">
                {after?.suggested_action || after?.explanation || before?.explanation}
              </small>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function pointsLabel(points = 0, maximum = 0) {
  return `${points} van ${maximum}`;
}

function factorLabel(key: string) {
  const labels: Record<string, string> = {
    title: "Paginatitel",
    meta_description: "Meta description",
    headings: "Koppen",
    indexability: "Indexeerbaarheid",
    canonical: "Canonical URL",
    keyword_coverage: "Zoekwoorddekking",
    readability: "Leesbaarheid",
    links: "Interne links",
    images: "Afbeeldingen",
    company_profile: "Bedrijfsprofiel",
  };
  return labels[key] ?? key.replaceAll("_", " ");
}
