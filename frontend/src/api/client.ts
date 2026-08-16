// Inventory API 客户端 — 对接 api/main.py (FastAPI)
// 所有写库操作走后端 db_writer 规则层 (两段式提交), 前端不直连数据库

export interface Customer {
  code: string
  name: string
}

export interface Salesperson {
  code: string
  name: string
  digit: string
}

export interface SalespersonFull extends Salesperson {
  id: number
  phone: string | null
  commission_rate: number | null
  is_active: number
  remark: string | null
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
  docHeaderTerms: (field: string) =>
    req<string[]>(`/options/doc-header-terms?field=${encodeURIComponent(field)}`),
  fieldValues: (customerCode: string, field: string) =>
    req<string[]>(`/options/field-values?customer_code=${encodeURIComponent(customerCode)}&field=${encodeURIComponent(field)}`),
  warehouses: () => req<{ code: string; name: string }[]>('/options/warehouses'),
  contracts: (customerCode?: string) =>
    req<Record<string, unknown>[]>(`/options/contracts${customerCode ? `?customer_code=${encodeURIComponent(customerCode)}` : ''}`),
  deliveries: () => req<Record<string, unknown>[]>('/options/deliveries'),
  purchaseOrders: () => req<Record<string, unknown>[]>('/options/purchase-orders'),
  contractMaterials: (contractNo: string) =>
    req<Record<string, unknown>[]>(`/options/contract-materials?contract_no=${encodeURIComponent(contractNo)}`),
  deliveryMaterials: (deliveryNo: string) =>
    req<Record<string, unknown>[]>(`/options/delivery-materials?delivery_no=${encodeURIComponent(deliveryNo)}`),
  contractStockProgress: (contractNo: string) =>
    req<Record<string, unknown>>(`/options/contract-stock-progress?contract_no=${encodeURIComponent(contractNo)}`),
  contractReceiptSummary: (contractNo: string) =>
    req<{ contract_no: string; customer_name: string; total_amount: number; currency: string; received: number; remaining: number; fully_received: boolean }>(
      `/options/contract-receipt-summary?contract_no=${encodeURIComponent(contractNo)}`),
  exchangeRates: () => req<Record<string, unknown>[]>('/options/exchange-rates'),
  materialTypeProfiles: () =>
    req<{ type_code: string; name: string; guide_cost_price: number | null }[]>('/aux/material-types'),
  // ── 生产辅料 (标签纸等) ──
  auxMaterials: (auxType?: string) =>
    req<Record<string, unknown>[]>(`/aux/materials${auxType ? `?aux_type=${encodeURIComponent(auxType)}` : ''}`),
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
  auxCreatePurchaseRequests: (body: Record<string, unknown>) =>
    post<{ ok: boolean; errors: string[]; req_nos: string[] }>('/aux/purchase-requests', body),
  auxPurchaseRequests: (status?: string) =>
    req<Record<string, unknown>[]>(`/aux/purchase-requests${status ? `?status=${encodeURIComponent(status)}` : ''}`),
  suggestCustomerCode: (letter?: string) =>
    req<{ code: string }>(`/options/suggest-customer-code${letter ? `?letter=${encodeURIComponent(letter)}` : ''}`),
  salespersons: () => req<Salesperson[]>('/options/salespersons'),
  salespersonsFull: () => req<SalespersonFull[]>('/salespersons'),
  createSalesperson: (data: Record<string, unknown>, operator: string) =>
    post<{ ok: boolean; errors: string[]; code: string | null }>('/salespersons', { data, operator }),
  updateSalesperson: (code: string, data: Record<string, unknown>, operator: string) =>
    req<{ ok: boolean; errors: string[]; code: string | null }>(
      `/salespersons/${encodeURIComponent(code)}`,
      { method: 'PUT', body: JSON.stringify({ data, operator }) }),
  createCustomer: (data: Record<string, unknown>, operator: string) =>
    post<{ ok: boolean; errors: string[]; code: string | null }>('/customers', { data, operator }),
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
  insert: (table: string, data: Record<string, unknown>, operator: string,
           options?: Record<string, unknown>) =>
    post<InsertResp>('/insert', { table, data, operator, options }),
  // ── 单据录入 (F2.6: 报价/合同/发货) ──
  suggestDocNo: (kind: string) =>
    req<{ ok: boolean; doc_no: string }>(`/options/suggest-doc-no?kind=${encodeURIComponent(kind)}`),
  productsPicker: (customerCode?: string) =>
    req<Record<string, unknown>[]>(`/options/products-picker${customerCode ? `?customer_code=${encodeURIComponent(customerCode)}` : ''}`),
  quotationsList: (customerCode?: string) =>
    req<Record<string, unknown>[]>(`/options/quotations${customerCode ? `?customer_code=${encodeURIComponent(customerCode)}` : ''}`),
  docQuotation: (quoteNo: string) =>
    req<{ found: boolean; header: Record<string, unknown> | null; items: Record<string, unknown>[] }>(
      `/docs/quotation?quote_no=${encodeURIComponent(quoteNo)}`),
  contractPending: (contractNo: string) =>
    req<{ found: boolean; header: Record<string, unknown> | null; items: Record<string, unknown>[] }>(
      `/docs/contract-pending?contract_no=${encodeURIComponent(contractNo)}`),
  createDoc: (kind: string, header: Record<string, unknown>, items: Record<string, unknown>[], operator: string) =>
    post<{ ok: boolean; errors: string[]; warnings: string[]; doc_no: string | null; total_amount?: number; total_amount_cny?: number; exchange_rate?: number }>(
      `/docs/${kind}`, { header, items, operator }),
  // ── 发货单事后处理 (🔴-4 回填实发 / 🟡-7 作废) ──
  deliveryActual: (deliveryNo: string, items: Record<string, unknown>[], operator: string) =>
    post<{ ok: boolean; errors: string[]; warnings: string[]; doc_no: string | null; contracts_updated: string[] }>(
      '/docs/delivery/actual', { data: { delivery_no: deliveryNo, items }, operator }),
  deliveryCancel: (deliveryNo: string, reason: string, operator: string) =>
    post<{ ok: boolean; errors: string[]; warnings: string[]; doc_no: string | null; contracts_updated: string[] }>(
      '/docs/delivery/cancel', { data: { delivery_no: deliveryNo, reason }, operator }),
  // ── 贷记单 (🟡-10 差异闭环: 报关后短装/超装挂具体报关单+合同行) ──
  shippingRecords: () => req<Record<string, unknown>[]>('/options/shipping-records'),
  shippingItems: (shippingNo: string) =>
    req<Record<string, unknown>[]>(`/options/shipping-items?shipping_no=${encodeURIComponent(shippingNo)}`),
}
