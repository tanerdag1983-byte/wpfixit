import { ArrowUpRight, Sparkles } from "lucide-react";

const opportunities = [
  {
    score: 94,
    title: "Verbeter de snippet van /revisie",
    evidence: "12.400 impressies · 1,2% CTR · positie 4,6",
    action: "Herschrijf de title en meta description rond revisie-intentie.",
    source: "Search Console + WordPress",
  },
  {
    score: 87,
    title: "Versterk de conversie op /versnellingsbak",
    evidence: "1.840 sessies · 11 conversies · 22% daling",
    action: "Maak de propositie en primaire offerte-CTA concreter.",
    source: "GA4 + WordPress",
  },
  {
    score: 79,
    title: "Bouw interne links naar /automaat-revisie",
    evidence: "Positie 8,2 · 7.100 impressies · 2 inkomende links",
    action: "Voeg contextuele links toe vanaf de drie sterkste servicepagina's.",
    source: "Crawl + Search Console",
  },
];

export function OpportunitiesPage() {
  return (
    <section className="data-page opportunity-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Onderbouwde aanbevelingen</p>
          <h1>Kansen</h1>
          <p className="subtitle">
            Concrete voorstellen uit WordPress, Google-data en de externe crawl.
          </p>
        </div>
        <button className="sync-button" type="button">
          <Sparkles size={16} />
          Nieuwe voorstellen
        </button>
      </div>

      <div className="opportunity-list">
        {opportunities.map((item) => (
          <article className="opportunity-card" key={item.title}>
            <div className="opportunity-score">
              <span>Impact</span>
              <strong>{item.score}</strong>
            </div>
            <div>
              <div className="opportunity-meta">
                <span className="priority-tag high">Voorstel</span>
                <small>{item.source}</small>
              </div>
              <h2>{item.title}</h2>
              <p className="opportunity-evidence">{item.evidence}</p>
              <p>{item.action}</p>
            </div>
            <button className="icon-button" type="button" aria-label={item.title}>
              <ArrowUpRight size={18} />
            </button>
          </article>
        ))}
      </div>
    </section>
  );
}
