// 出入库明细行编辑器 — 物料+数量+备注 的简易可编辑表格 (入库/出库录入页共用)
import { Button, Input, InputNumber, Select, Table } from 'antd'
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons'
import type { ProductOption } from './DocItemsEditor'

export interface StockItem {
  key: number
  material_id: string | null
  quantity: number | null
  remark: string
}

export const newStockItem = (key: number): StockItem => ({ key, material_id: null, quantity: null, remark: '' })

interface Props {
  products: ProductOption[]
  items: StockItem[]
  onChange: (items: StockItem[]) => void
}

export default function StockItemsEditor({ products, items, onChange }: Props) {
  const set = (key: number, patch: Partial<StockItem>) =>
    onChange(items.map((it) => (it.key === key ? { ...it, ...patch } : it)))
  const add = () => onChange([...items, newStockItem(Math.max(0, ...items.map((i) => i.key)) + 1)])
  const remove = (key: number) => onChange(items.filter((it) => it.key !== key))

  const productOptions = products.map((p) => ({
    value: p.material_id,
    label: `${p.material_id} - ${p.spec || ''}${p.brand ? ` (${p.brand})` : ''}`,
  }))

  return (
    <Table
      size="small" rowKey="key" dataSource={items} pagination={false}
      footer={() => <Button type="dashed" icon={<PlusOutlined />} onClick={add} block>加一行</Button>}
      columns={[
        {
          title: '物料 *', dataIndex: 'material_id', width: '45%',
          render: (v: string | null, r: StockItem) => (
            <Select style={{ width: '100%' }} showSearch optionFilterProp="label" placeholder="搜索编码/规格"
              value={v} onChange={(val) => set(r.key, { material_id: val })} options={productOptions} />
          ),
        },
        {
          title: '数量(卷) *', dataIndex: 'quantity', width: 140,
          render: (v: number | null, r: StockItem) => (
            <InputNumber style={{ width: '100%' }} min={1} precision={0} value={v}
              onChange={(val) => set(r.key, { quantity: val })} />
          ),
        },
        {
          title: '备注', dataIndex: 'remark',
          render: (v: string, r: StockItem) => (
            <Input value={v} onChange={(e) => set(r.key, { remark: e.target.value })} />
          ),
        },
        {
          title: '', width: 50,
          render: (_: unknown, r: StockItem) => (
            <Button type="text" danger icon={<DeleteOutlined />} onClick={() => remove(r.key)}
              disabled={items.length <= 1} />
          ),
        },
      ]}
    />
  )
}
