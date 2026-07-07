export type InternalLink = { anchor: string; url: string };
export type Replacement = { field_id: string; value: string };

export type PagePackage = {
  title: string;
  slug: string;
  seo_title: string;
  meta_description: string;
  focus_keyword: string;
  replacements: Replacement[];
  internal_links: InternalLink[];
};

export type BlueprintField = {
  id: string;
  path: string;
  label: string;
  value_type: "plain_text" | "rich_text" | "heading" | "button_text" | "url";
  current_value: string;
  required: boolean;
  max_length: number;
};

export type BlueprintBlock = {
  id: string;
  layout: string;
  label: string;
  semantic_role: string;
  fields: BlueprintField[];
};

export type BlueprintSchema = {
  schema_version: "blueprint-v1";
  blocks: BlueprintBlock[];
};

export type ProposalState =
  | "generating"
  | "proposed"
  | "approved"
  | "draft_created"
  | "failed";

export type ProposalCandidate = {
  id: string;
  proposal_group_id: string;
  base_version_id: string;
  generation_mode: "full" | "block";
  target_block_id: string | null;
  instruction: string | null;
  status: string;
  provider: string | null;
  model: string | null;
  prompt_version?: string | null;
  input_tokens?: number;
  output_tokens?: number;
  candidate_package?: PagePackage;
  candidate_rendered_html?: string;
};

export type ProposalHandoff = {
  id: string;
  project_id: string;
  proposal_version_id: string;
  state: string;
  expires_at: string;
  wordpress_edit_url?: string | null;
};

export type ProposalHandoffIssueResponse = {
  handoff: ProposalHandoff;
  code: string;
  import_url: string;
};

export type Proposal = {
  id: string;
  state: ProposalState;
  proposal_group_id?: string;
  version_number?: number;
  is_current?: boolean;
  package: PagePackage;
  rendered_html: string;
  blueprint: {
    name: string;
    page_type: string;
    version: number;
    builder: string;
    seo_plugin: string;
    source_wordpress_page_id?: string;
  } | null;
  config_snapshot: { content_schema?: BlueprintSchema };
  provider: string | null;
  model: string | null;
  approved_at?: string | null;
  wordpress_edit_url?: string | null;
  active_candidate?: ProposalCandidate | null;
  latest_handoff?: ProposalHandoff | null;
  job: { state: string; progress: number; error_message?: string | null } | null;
};
