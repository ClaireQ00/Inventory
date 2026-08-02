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
  warehouses: () => req<{ code: string; name: string }[]>('/options/warehouses'),
  materialTypeProfiles: () =>
    req<{ type_code: string; name: string; guide_cost_price: number | null }[]>('/aux/material-types'),
  // ── 生产辅料 (标签纸等) ──
  auxMaterials: () => req<Record<string, unknown>[]>('/aux/materials'),
  auxCreate: (data: Record<string, unknown>, operator: string) =>
    post<{ ok: boolean; errors: string[]; record_id: number | null }>('/aux/materials', { data, operator }),
  auxInventory: (lowOnly = false) =>
    req<Record<string, unknown>[]>(`/aux/inventory${lowOnly ? '?low_only=true' : ''}`),
  auxStockIn: (body: Record<string, unknown>) =>
    post<{ ok: boolean; errors: string[]; move_no: string | null; after_qty: number | null }>('/aux/stock-in', body),
  auxStockOut: (body: Record<string, unknown>) =>
    post<{ ok: boolean; errors: string[]; move_no: string | null; after_qty: number | null }>('/aux/stock-out', body),
  auxMoves: (auxCode?: string) =>
    req<Record<string, unknown>[]>(`/aux/moves${auxCode ? `?aux_code=${encodeURIComponent(auxCode)}` : ''}`),
  auxLabelDemand: (contractNo: string) =>
    req<{
      contract_no: string; found: boolean; all_sufficient: boolean | null
      lines: { label_paper: string; aux_code: string; name: string; unit: string; required: number; in_stock: number; shortage: number; profile_missing: boolean }[]
    }>(`/aux/label-demand?contract_no=${encodeURIComponent(contractNo)}`),
  auxAttachments: (auxCode: string) =>
    req<{ id: number; file_name: string; file_type: string; file_size: number; uploaded_by: string; created_at: string }[]>(
      `/aux/attachments?aux_code=${encodeURIComponent(auxCode)}`),
  auxUpload: async (auxCode: string, file: File, uploadedBy: string) => {
    const fd = new FormData()
    fd.append('file', file)
    const r = await fetch(`${BASE}/aux/materials/${encodeURIComponent(auxCode)}/attachments?uploaded_by=${encodeURIComponent(uploadedBy)}`, {
      method: 'POST', body: fd,
    })
    if (!r.ok) {
      const detail = await r.json().catch(() => ({}))
      throw new Error(detail.detail || `上传失败 ${r.status}`)
    }
    return r.json()
  },
  auxDownloadUrl: (id: number) => `${BASE}/aux/attachments/${id}/download`,
  derive: (data: Record<string, unknown>) =>
    post<DeriveResp>('/derive', { table: 'products', data }),
  preview: (table: string, data: Record<string, unknown>) =>
    post<PreviewResp>('/preview', { table, data }),
  insert: (table: string, data: Record<string, unknown>, operator: string) =>
    post<InsertResp>('/insert', { table, data, operator }),
}
