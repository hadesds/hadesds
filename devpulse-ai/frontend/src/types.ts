export interface Run {
  id: string; run_key: string; kind: string; slot: string | null; edition_date: string | null; trigger: string;
  status: string; step: string | null; attempts: number; started_at: string | null; finished_at: string | null;
  error: string | null; stats: Record<string, unknown>; created_at: string;
}
export interface Dashboard {
  today: string; collected_today: number; analyzed_today: number; scripts_today: number; daily_limit: number;
  notifications_sent_today: number; errors_today: { sources: number; deliveries: number; runs: number };
  pending: { runs: number; deliveries: number }; last_edition_run: Run | null; next_runs: { slot: string; at: string }[];
  llm_today: { calls: number; estimated_cost_usd: number; limit_calls: number }; recent_runs: Run[];
}
export interface SourceRun { id: number; started_at: string; status: string; items_found: number; items_new: number; items_duplicate: number; error: string | null }
export interface Source {
  id: number; slug: string; name: string; connector_type: string; url: string | null; config: Record<string, unknown>;
  category: string | null; priority_tier: number; reliability: number; enabled: boolean; fetch_interval_minutes: number;
  notes: string | null; last_run_at: string | null; last_success_at: string | null; last_error: string | null;
  consecutive_failures: number; last_run: SourceRun | null;
}
export interface Connector { type: string; description: string; config_fields: Record<string, string> }
export interface NewsItem {
  id: number; title: string; url: string; source: { id: number; name: string } | null; summary: string | null;
  author: string | null; published_at: string | null; published_at_inferred: boolean; source_updated_at: string | null; discovered_at: string;
  language: string | null; category: string | null; content_type: string; verification_status: string;
  content_access: string; editorial_score: number | null; cluster_id: number | null;
}
export interface NewsDetail extends NewsItem {
  content_excerpt: string; extraction_error: string | null;
  references: { source: string | null; url: string; type: string; seen_at: string }[];
  related: NewsItem[];
  scores: { total: number; components: Record<string, number>; method: string; eligible: boolean; reason: string | null; computed_at: string }[];
}
export interface Scene {
  start_second: number; end_second: number; section: string; speech: string; action: string; on_screen: string;
  overlay_text: string; editing_notes: string; visual_resource: string;
}
export interface Package {
  identification: { news_title: string; video_title: string; category: string; published_at: string | null; last_verified_at: string;
    editorial_score: number; selection_reason: string; primary_sources: SourceLink[]; complementary_sources: SourceLink[] };
  planning: { objective: string; audience: string; technical_level: string; duration_seconds: number; format: string; hook: string; key_message: string };
  scenes: Scene[];
  recording_guide: Record<string, unknown> & { demo_status: string; demo_note: string; steps: string[]; commands: string[] };
  visual_resources: { scene: number | null; kind: string; description: string; url: string | null; license_info: string; accessible: boolean | null }[];
  publication: { caption: string; cover_title: string; call_to_action: string; hashtags: string[]; pinned_comment: string; final_checklist: string[] };
  uncertainties: string[]; generator: string; generator_notes: string[];
  [key: string]: unknown;
}
export interface SourceLink { ref: string; title: string; url: string; publisher: string; evidence_type: string }
export interface ScriptSummary {
  id: number; edition_date: string; position: number; status: string; news_title: string; video_title: string;
  category: string | null; editorial_score: number | null; estimated_duration_seconds: number | null; generator: string;
  edited_manually: boolean; selection_reason: string | null; rejection_reason: string | null;
  verification: { status?: string; problems?: string[] };
}
export interface ScriptFull extends ScriptSummary {
  package: Package; markdown: string; scenes: Scene[];
  fact_checks: { claim: string; claim_type: string; is_central: boolean; source_url: string | null; evidence_type: string; result: string; notes: string | null }[];
}
export interface Delivery {
  id: number; edition_date: string; channel: string; recipient: string; status: string; attempts: number;
  next_attempt_at: string | null; last_error: string | null; provider_message_id: string | null; provider_status: string | null;
  sent_at: string | null; created_at: string;
}
export interface SettingsView {
  editable: Record<string, string | number | boolean | string[]>;
  categories: string[];
  integrations: Record<string, Record<string, unknown>>;
}
