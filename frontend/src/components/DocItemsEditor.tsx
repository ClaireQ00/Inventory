// 单据明细行编辑器 (F2.6 共享组件)
// 报价模式: 快照单重(带出可改) × 报价系数 → 单价/小计自动算 (ADR-0005)
// 合同模式: 单价直填, 小计自动算
// 派生只作展示, 落库时后端会重算 (不信前端)
import { AutoComplete, Button, InputNumber, Table, Typography } from 'antd'
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons'

const { Text } = Typography

export interface DocItem {
  key: number
  item_no: string
  material_id: string
  spec: string
  weight_per_unit: number | null   // 报价: 快照单重 (从物料带出可覆盖)
  price_coefficient: number | null // 报价: 报价系数 USD/KG
  unit_price: number | null        // 合同: 单价直填
  quantity: number | null
  remark: string
}

export interface ProductOption {
  material_id: string
  spec: string
  brand: string
  weight: number | null
  volume: number | null
}

let seq = 1
export function newItem(no: number): DocItem {
  return {
    key: seq++, item_no: String(no).padStart(3, '0'), material_id: '', spec: '',
    weight_per_unit: null, price_coefficient: null, unit_price: null, quantity: null, remark: '',
  }
}

export function itemCalc(mode: 'quotation' | 'contract', it: DocItem) {
  const q = it.quantity || 0
  const price = mode === 'quotation'
    ? (it.weight_per_unit || 0) * (it.price_coefficient || 0)
    : (it.unit_price || 0)
  return { price: Math.round(price * 100) / 100, subtotal: Math.round(price * q * 100) / 100 }
}

interface Props {
  mode: 'quotation' | 'contract'
  products: ProductOption[]
  items: DocItem[]
  onChange: (items: DocItem[]) => void
}

export default function DocItemsEditor({ mode, products, items, onChange }: Props) {
  const set = (key: number, patch: Partial<DocItem>) =>
    onChange(items.map((it) => (it.key === key ? { ...it, ...patch } : it)))
  const del = (key: number) => onChange(items.filter((it) => it.key !== key))
  const add = () => onChange([...items, newItem(items.length + 1)])

  const matOptions = products.map((p) => ({
    value: p.material_id,
    label: `${p.material_id} · ${p.spec || ''}${p.weight ? ` · ${p.weight}kg` : ''}`,
  }))

  const pickMaterial = (key: number, mid: string) => {
    const p = products.find((x) => x.material_id === mid)
    set(key, {
      material_id: mid,
      spec: p?.spec || '',
      // 快照重量带出 (ADR-0005): 改的是行上副本, 不动物料主数据
      weight_per_unit: p?.weight ?? null,
    })
  }

  const numCell = (it: DocItem, field: keyof DocItem, step = 0.1, width = 110) => (
    <InputNumber
      style={{ width }} min={0} step={step}
      value={it[field] as number | null}
      onChange={(v) => set(it.key, { [field]: v } as Partial<DocItem>)}
    />
  )

  const columns = [
    { title: '行号', dataIndex: 'item_no', width: 56,
      render: (v: string, it: DocItem) => (
        <span style={{ cursor: 'text' }}
          contentEditable suppressContentEditableWarning
          onBlur={(e) => set(it.key, { item_no: e.currentTarget.textContent || it.item_no })}
        >{v}</span>
      ) },
    { title: '物料 *', dataIndex: 'material_id', width: 260,
      render: (v: string, it: DocItem) => (
        <AutoComplete
          style={{ width: '100%' }} value={v} placeholder="输入编码筛选"
          options={matOptions}
          filterOption={(input, option) => (option?.label as string)?.includes(input)}
          onChange={(val) => pickMaterial(it.key, val)}
        />
      ) },
    { title: '规格', dataIndex: 'spec', width: 170, render: (v: string) => <Text type="secondary">{v || '—'}</Text> },
    ...(mode === 'quotation'
      ? [
          { title: '快照单重KG *', dataIndex: 'weight_per_unit', width: 120,
            render: (_: unknown, it: DocItem) => numCell(it, 'weight_per_unit', 0.5) },
          { title: '报价系数 *', dataIndex: 'price_coefficient', width: 110,
            render: (_: unknown, it: DocItem) => numCell(it, 'price_coefficient', 0.001) },
          { title: '单价', width: 90, render: (_: unknown, it: DocItem) => <Text>{itemCalc(mode, it).price || '—'}</Text> },
        ]
      : [
          { title: '单价 *', dataIndex: 'unit_price', width: 110,
            render: (_: unknown, it: DocItem) => numCell(it, 'unit_price', 0.01) },
        ]),
    { title: '数量(卷) *', dataIndex: 'quantity', width: 110,
      render: (_: unknown, it: DocItem) => numCell(it, 'quantity', 1) },
    { title: '小计', width: 100, render: (_: unknown, it: DocItem) => {
      const s = itemCalc(mode, it).subtotal
      return <Text strong>{s ? s.toFixed(2) : '—'}</Text>
    } },
    { title: '', width: 50, render: (_: unknown, it: DocItem) => (
      <Button type="text" danger icon={<DeleteOutlined />} onClick={() => del(it.key)} />
    ) },
  ]

  return (
    <>
      <Table
        size="small" rowKey="key" dataSource={items} columns={columns as never}
        pagination={false} scroll={{ x: 900 }}
      />
      <Button style={{ marginTop: 8 }} icon={<PlusOutlined />} onClick={add}>添加一行</Button>
      <Text type="secondary" style={{ marginLeft: 12, fontSize: 12 }}>
        {mode === 'quotation'
          ? '单价 = 快照单重 × 报价系数；快照单重改的是这一行的副本，物料主数据不动（ADR-0005）'
          : '小计 = 单价 × 数量；单价可从报价转入带出'}
      </Text>
    </>
  )
}
