// API client for Mini Wren AI FastAPI backend
import type {
  ConnectionStatus,
  ConnectResponse,
  TestConnectionResponse,
  AskResponse,
  SQLExecuteResponse,
  ChartResponse,
  ModelsResponse,
  GlossaryResponse,
  GlossaryTerm,
  SQLPairsResponse,
  SQLPair,
  SettingsData,
  DeployResponse,
  HealthResponse,
  ModelUpdateData,
} from '@/utils/types';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000';

// ── Base helpers ──

class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function apiGet<T>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`);
  } catch {
    throw new ApiError('Backend không phản hồi. Kiểm tra server đang chạy.', 0);
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    throw new ApiError(err.detail || `API error: ${res.status}`, res.status);
  }
  return res.json();
}

async function apiPost<T>(path: string, body?: any): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError('Backend không phản hồi. Kiểm tra server đang chạy.', 0);
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    throw new ApiError(err.detail || `API error: ${res.status}`, res.status);
  }
  return res.json();
}

async function apiPut<T>(path: string, body: any): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  } catch {
    throw new ApiError('Backend không phản hồi. Kiểm tra server đang chạy.', 0);
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    throw new ApiError(err.detail || `API error: ${res.status}`, res.status);
  }
  return res.json();
}

async function apiPatch<T>(path: string, body: any): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  } catch {
    throw new ApiError('Backend không phản hồi. Kiểm tra server đang chạy.', 0);
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    throw new ApiError(err.detail || `API error: ${res.status}`, res.status);
  }
  return res.json();
}

async function apiDelete<T>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { method: 'DELETE' });
  } catch {
    throw new ApiError('Backend không phản hồi. Kiểm tra server đang chạy.', 0);
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    throw new ApiError(err.detail || `API error: ${res.status}`, res.status);
  }
  return res.json();
}

// ── Connection data ──
interface ConnectionData {
  host: string;
  port: number;
  database: string;
  username: string;
  password: string;
}

// ── Full API with proper types ──
export const api = {
  // Health
  health: () => apiGet<HealthResponse>('/health'),

  // Connection management
  testConnection: (data: ConnectionData) =>
    apiPost<TestConnectionResponse>('/v1/connections/test', data),
  connect: (data: ConnectionData) =>
    apiPost<ConnectResponse>('/v1/connections/connect', data),
  connectionStatus: () =>
    apiGet<ConnectionStatus>('/v1/connections/status'),
  disconnect: () =>
    apiPost<{ success: boolean; message: string }>('/v1/connections/disconnect'),

  // Ask & Execute
  ask: (question: string, overrides?: Record<string, any>, debug = false) =>
    apiPost<AskResponse>('/v1/ask', { question, debug, ...overrides }),
  executeSql: (sql: string, limit = 100) =>
    apiPost<SQLExecuteResponse>('/v1/sql/execute', { sql, limit }),
  getModels: () =>
    apiGet<ModelsResponse>('/v1/models'),

  // Chart generation
  generateChart: (question: string, sql: string) =>
    apiPost<ChartResponse>('/v1/charts/generate', { question, sql }),

  // Model metadata update
  updateModel: (modelName: string, data: ModelUpdateData) =>
    apiPatch<{ success: boolean; model: any }>(`/v1/models/${encodeURIComponent(modelName)}`, data),

  // Knowledge — Glossary
  getGlossary: () =>
    apiGet<GlossaryResponse>('/v1/knowledge/glossary'),
  addGlossaryTerm: (term: { term: string; aliases: string[]; sql_expression: string; description: string }) =>
    apiPost<{ success: boolean; term: GlossaryTerm }>('/v1/knowledge/glossary', term),
  updateGlossaryTerm: (id: string, data: { term: string; aliases: string[]; sql_expression: string; description: string }) =>
    apiPut<{ success: boolean; term: GlossaryTerm }>(`/v1/knowledge/glossary/${id}`, data),
  deleteGlossaryTerm: (id: string) =>
    apiDelete<{ success: boolean }>(`/v1/knowledge/glossary/${id}`),

  // Knowledge — SQL Pairs
  getSqlPairs: () =>
    apiGet<SQLPairsResponse>('/v1/knowledge/sql-pairs'),
  addSqlPair: (pair: { question: string; sql: string }) =>
    apiPost<{ success: boolean; pair: SQLPair }>('/v1/knowledge/sql-pairs', pair),
  updateSqlPair: (id: string, data: { question: string; sql: string }) =>
    apiPut<{ success: boolean; pair: SQLPair }>(`/v1/knowledge/sql-pairs/${id}`, data),
  deleteSqlPair: (id: string) =>
    apiDelete<{ success: boolean }>(`/v1/knowledge/sql-pairs/${id}`),

  // Settings
  getSettings: () =>
    apiGet<SettingsData>('/v1/settings'),
  updateSettings: (data: { features?: Record<string, boolean>; generation?: Record<string, any> }) =>
    apiPut<{ success: boolean; settings: SettingsData }>('/v1/settings', data),

  // Deploy (re-deploy)
  deploy: () =>
    apiPost<DeployResponse>('/v1/deploy'),
};
