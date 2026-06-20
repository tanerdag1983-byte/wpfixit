# AI Recommendation Quality Design

## Goal

Make generated recommendations safe to review and publish. The action list should show concise, human-readable titles and explanations, while the publishing review should receive only the exact value that can be written to WordPress after approval.

## Output Contract

AI providers must return structured JSON with three separated presentation layers:

- `action_title`: short dashboard title, no HTML.
- `explanation`: one short reason for the recommendation, no HTML.
- `recommendation`: exact publishable value for WordPress. HTML is allowed only for `content` recommendations.

For `seo_title`, `meta_description`, `canonical`, `noindex`, `internal_links`, and `redirect`, HTML in `recommendation` is invalid and should be stripped or rejected before storing.

## Project Context

The project-specific company profile and custom prompt are part of the provider system prompt. The prompt should be followed when it does not conflict with the publishable-output contract, safety, or evidence constraints. Changing the profile, project prompt, or AI policy changes the prompt version and creates a new recommendation version.

## Fallback Behavior

If AI generation fails, the rules engine should still produce useful project/page-specific output. It should use page title, URL path, current WordPress fields, SEO plugin context, priority score, and available audit evidence. It must not expose internal scoring language such as "component audit" to end users.

## Testing

Backend tests cover:

- Provider output normalization rejects or sanitizes HTML in presentation fields.
- Non-content publishable fields do not store HTML recommendations.
- Rules fallback creates page-specific titles and explanations without internal scoring jargon.
- API responses expose AI fallback status and reason.

Frontend tests cover:

- Action list renders concise title, explanation, provider label, and fallback warning.
