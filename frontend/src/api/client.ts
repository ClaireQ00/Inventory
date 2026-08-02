// Inventory API 客户端 — 对接 api/main.py (FastAPI)
// 所有写库操作走后端 db_writer 规则层 (两段式提交), 前端不直连数据库

export interface Customer {
  code: string
  name: string
}

export interface EngineMsg {
  level: 'info' | 'warn' | 'error'
  msg: string
}

export interface DeriveResp {
  row: Record<string, unknown>
  computed: string[]
  msgs: EngineMsg[]
  density: number | null
  category_group: string | null
}

export interface PreviewResp {
  ok: boolean
  errors: string[]
  derived_row: Record<string, unknown>
  engine_msgs: EngineMsg[]
  rate_note: string
}

export interface InsertResp {
  ok: boolean
  errors: string[]
  warnings: string[]
  record_id: number | null
  checks: EngineMsg[]
}

const BASE = import.meta.env.VITE_API_BASE || '/api'

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!r.ok) throw new Error(`API ${path} 返回 ${r.status}`)
  return r.json() as Promise<T>
}

function post<T>(path: string, body: unknown): Promise<T> {
  return req<T>(path, { method: 'POST', body: JSON.stringify(body) })
}

export const api = {
  customers: () => req<Customer[]>('/options/customers'),
  categories: () => req<string[]>('/options/categories'),
  suggestMaterialId: (customerCode: string) =>
    req<{ material_id: string }>(`/options/suggest-material-id?customer_code=${encodeURIComponent(customerCode)}`),
  brands: (customerCode: string) =>
    req<string[]>(`/options/brands?customer_code=${encodeURIComponent(customerCode)}`),
  nominalInches: () => req<string[]>('/options/nominal-inches'),
  fieldValues: (customerCode: string, field: string) =>
    req<string[]>(`/options/field-values?customer_code=${encodeURIComponent(customerCode)}&field=${encodeURIComponent(field)}`),
  derive: (data: Record<string, unknown>) =>
    post<DeriveResp>('/derive', { table: 'products', data }),
  preview: (table: string, data: Record<string, unknown>) =>
    post<PreviewResp>('/preview', { table, data }),
  insert: (table: string, data: Record<string, unknown>, operator: string) =>
    post<InsertResp>('/insert', { table, data, operator }),
}
