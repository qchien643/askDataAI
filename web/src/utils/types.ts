// Types for Mini Wren AI

// ── Debug Trace ──
export interface StageTrace {
  stage: string;
  status: 'done' | 'error' | 'skipped' | 'running' | 'pending' | 'interrupted';
  duration_ms: number;
  input: Record<string, any>;
  output: Record<string, any>;
  error?: string;
}

export interface DebugTrace {
  total_duration_ms: number;
  total_stages: number;
  stages: StageTrace[];
}


export interface Model {
  name: string;
  table_reference: string;
  description: string;
  primary_key: string;
  columns: Column[];
}

export interface Column {
  name: string;
  display_name: string;
  type: string;
  description: string;
  is_calculated?: boolean;
  expression?: string;
  enum_values?: string[];  // Tập giá trị hợp lệ (categorical column)
}

export interface Relationship {
  name: string;
  model_from: string;
  model_to: string;
  join_type: string;
  condition: string;
}

export interface ModelsResponse {
  models_count: number;
  relationships_count: number;
  models: Model[];
  relationships: Relationship[];
}

export interface ConnectionStatus {
  connected: boolean;
  deployed: boolean;
  host: string;
  port: number;
  database: string;
  models_count: number;
}

export interface ConnectResponse {
  success: boolean;
  message: string;
  models_count: number;
  relationships_count: number;
  manifest_hash: string;
  indexed: boolean;
}

export interface TestConnectionResponse {
  status: string;
  database_name?: string;
  server_version?: string;
  error?: string;
}

export interface AskResponse {
  question: string;
  intent: string;
  sql: string;
  original_sql?: string;
  explanation: string;
  columns: string[];
  rows: Record<string, any>[];
  row_count: number;
  valid: boolean;
  retries: number;
  error: string;
  models_used: string[];
  pipeline_info?: {
    reasoning_steps: string[];
    schema_links: Record<string, any>;
    columns_pruned: number;
    candidates_generated: number;
    voting_method: string;
    glossary_matches: number;
    similar_traces: number;
    active_features: Record<string, any>;
    sub_intent: string;
    sub_intent_hints: string;
    instructions_matched: number;
    guardian_passed: boolean;
    pre_filter_result: string;
    // Stage 0: PIGuardrail
    pi_guard_blocked: boolean;
    pi_guard_confidence: number;
    // Stage 0.5: Conversation Context (mem0)
    session_id: string;
    enriched_question: string;
    was_enriched: boolean;
  };
  debug_trace?: DebugTrace;
}

export interface SQLExecuteResponse {
  columns: string[];
  rows: Record<string, any>[];
  row_count: number;
}

export interface ChartResponse {
  reasoning: string;
  chart_type: string;
  chart_schema: Record<string, any>;
  error?: string;
  data: {
    columns: string[];
    rows: Record<string, any>[];
    row_count: number;
  };
}

export interface HealthResponse {
  status: string;
  connected: boolean;
  deployed: boolean;
}

export interface DeployResponse {
  success: boolean;
  message: string;
  models_count: number;
  relationships_count: number;
  manifest_hash: string;
  indexed: boolean;
}

export interface ChatThread {
  id: string;
  title: string;
  messages: ChatMessage[];
  createdAt: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sql?: string;
  columns?: string[];
  rows?: Record<string, any>[];
  rowCount?: number;
  valid?: boolean;
  explanation?: string;
  timestamp: string;
}

export interface GlossaryTerm {
  id: string;
  term: string;
  aliases: string[];
  sql_expression: string;
  description: string;
}

export interface SQLPair {
  id: string;
  question: string;
  sql: string;
  created_at?: string;
}

export interface GlossaryResponse {
  terms: GlossaryTerm[];
}

export interface SQLPairsResponse {
  pairs: SQLPair[];
}

export interface SettingsData {
  features: Record<string, boolean>;
  generation: Record<string, number>;
}

export interface ModelUpdateData {
  description?: string;
  columns?: { name: string; description?: string; display_name?: string; enum_values?: string[] }[];
}

export interface AddColumnData {
  name: string;
  type: string;
  display_name?: string;
  description?: string;
}

export interface AddModelData {
  name: string;
  table_reference: string;
  description?: string;
  primary_key?: string;
  columns: AddColumnData[];
}

export interface AddRelationshipData {
  name: string;
  model_from: string;
  model_to: string;
  join_type: string;
  condition: string;
}

export interface TestGenerateResponse {
  success: boolean;
  models_added: number;
  relationships_added: number;
  models: { name: string; table: string; columns_count: number }[];
  relationships: { name: string; from: string; to: string }[];
  message: string;
}

export interface AutoDescribeEvent {
  phase: string;
  status: string;
  progress: string;
  table?: string;
  descriptions?: Record<string, string>;
}
