# DataForSEO Keyword Opportunities Design

## Doel

WP FixPilot krijgt een eerste DataForSEO-integratie die externe zoekmarktdata toevoegt aan projecten. De eerste release richt zich op keyword opportunities: zoekwoorden met volume, concurrentiegegevens en een concrete actie voor bestaande of nieuwe pagina's. SERP-detailanalyse en uitgebreide concurrentieanalyse volgen daarna.

## Scope

Deze fase bouwt:

- organisatiebrede DataForSEO-verbinding met versleutelde credentials;
- verbindingstest zonder credentials terug te sturen naar de browser;
- projectmatige keyword-opportunity sync;
- opslag van keyword opportunities per project;
- live weergave in de bestaande Kansen-tab.

Deze fase bouwt nog niet:

- backlinkanalyse;
- volledige SERP-snapshot opslag;
- bulk concurrentie-overlap;
- automatische WordPress-publicatie vanuit keyword opportunities.

## Datamodel

`dataforseo_connections`

- `organization_id` als primary key en foreign key;
- `login`;
- `encrypted_password`;
- `enabled`;
- `last_tested_at`;
- `last_test_status`;
- `last_test_message`;
- timestamps.

`keyword_opportunities`

- `id`;
- `project_id`;
- `keyword`;
- `location_code`;
- `language_code`;
- `search_volume`;
- `cpc`;
- `competition`;
- `competition_level`;
- `keyword_difficulty`;
- `intent`;
- `target_url`;
- `recommended_action`;
- `source`;
- `raw_payload`;
- `discovered_at`.

Uniqueness: `project_id`, `keyword`, `location_code`, `language_code`.

## Backend API

Instellingen:

- `GET /organizations/{id}/dataforseo-connection`
- `PUT /organizations/{id}/dataforseo-connection`
- `POST /organizations/{id}/dataforseo-connection/test`

Projectdata:

- `POST /projects/{id}/sync-keyword-opportunities`
- `GET /projects/{id}/keyword-opportunities`

Alle routes gebruiken bestaande membership-controles. Alleen owners/admins mogen credentials beheren en syncs starten. Projectleden mogen kansen lezen als ze projecttoegang hebben.

## DataForSEO Provider

De provider gebruikt Basic Auth met DataForSEO login en password. De eerste sync gebruikt keyword-idee/volume endpoints via een kleine adapterlaag, zodat later SERP, difficulty, intent en competitor modules kunnen worden toegevoegd zonder routes te herschrijven.

Input voor seeds:

- projectdomein;
- WordPress pagina URL-paden;
- bekende SEO title en meta description indien aanwezig;
- fallback seed uit projectnaam/domein.

De eerste implementatie mag met een beperkte seedset werken om kosten en runtime te beperken. De route moet idempotent zijn: opnieuw syncen werkt opportunities bij in plaats van duplicaten te maken.

## Kansenlogica

Elke opportunity krijgt een eenvoudige aanbevolen actie:

- bestaande pagina verbeteren wanneer een keyword logisch aan een bekende URL kan worden gekoppeld;
- nieuwe landingspagina maken wanneer geen duidelijke URL bestaat;
- snippet verbeteren wanneer er zoekvolume is en een bestaande pagina al lijkt te passen.

De Kansen-tab toont:

- impactscore;
- keyword;
- volume, CPC, competitie/difficulty;
- gekoppelde pagina of "Nieuwe pagina";
- recommended action;
- bron `DataForSEO`.

## Foutafhandeling

- Ongeldige credentials geven een veilige melding zonder login/password te lekken.
- DataForSEO timeouts of API-fouten worden opgeslagen als test/sync-status.
- Als er geen opportunities zijn, toont de frontend een lege staat met uitleg.
- Sync mag falen zonder bestaande opportunities te verwijderen.

## Security

- Credentials worden versleuteld opgeslagen via de bestaande crypto helper.
- API responses bevatten nooit plaintext credentials.
- Raw provider payload wordt alleen opgeslagen voor opportunitydata, niet voor secrets.
- Routes blijven tenant-isolated via organization/project membership.

## Testing

Backend:

- model/route tests voor credentialvrije responses;
- connection test success/failure met gemockte provider;
- sync route maakt/updatet opportunities idempotent;
- cross-organization toegang wordt geweigerd.

Frontend:

- DataForSEO settings panel slaat credentials op en test verbinding;
- Kansen-tab laadt echte opportunities;
- sync button toont voortgang/status;
- lege staat bij geen opportunities.

## Uitrol

Deze fase vereist een backend deploy op Render en frontend deploy op Vercel. Er zijn nieuwe tabellen nodig via Alembic migratie. Na deploy vult de gebruiker DataForSEO login/password in bij Instellingen en start per project de keyword-opportunity sync.
