// 入库单录入页 (2026-08-02) — 要先有入库才有发货: 生产完工/采购/退货入库
// 落库=实际发生, 状态直接 confirmed; 库存结果表+流水单事务同步; 采购入库联动采购单状态
import { useEffect, useState } from 'react'
import {
  App, Button, Card, Col, DatePicker, Input, Modal, Row, Select, Space, Statistic, Typography,
} from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { api } from '@/api/client'
import StockItemsEditor, { newStockItem, type StockItem } from '@/components/StockItemsEditor'
import type { ProductOption } from '@/components/DocItemsEditor'

const { Text, Title } = Typography

export default function StockInEntry() {
  const { message } = App.useApp()
  const [products, setProducts] = useState<ProductOption[]>([])
  const [warehouses, setWarehouses] = useState<{ code: string; name: string }[]>([])
  const [pos, setPos] = useState<Record<string, unknown>[]>([])
  const [header, setHeader] = useState({
    in_no: '', in_type: 'production', warehouse_code: null as string | null,
    po_no: null as string | null, in_date: dayjs(), remark: '',
  })
  const [items, setItems] = useState<StockItem[]>([newStockItem(1)])
  const [operator, setOperator] = useState('')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    api.productsPicker().then((l) => setProducts(l as unknown as ProductOption[])).catch((e) => message.error(`物料加载失败: ${e.message}`))
    api.warehouses().then(setWarehouses).catch(() => {})
    api.purchaseOrders().then(setPos).catch(() => {})
    suggestNo()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const suggestNo = () => {
    api.suggestDocNo('stock_in').then((r) => setHeader((h) => ({ ...h, in_no: r.doc_no }))).catch(() => {})
  }
  const set = (k: string, v: unknown) => setHeader((h) => ({ ...h, [k]: v }))
  const validItems = items.filter((it) => it.material_id && it.quantity)

  const onSubmit = async () => {
    if (!header.in_no.trim()) return message.warning('请填入库单号')
    if (!header.warehouse_code) return message.warning('请选择仓库')
    if (header.in_type === 'purchase' && !header.po_no) return message.warning('采购入库必须选择采购单')
    if (validItems.length === 0) return message.warning('至少一行完整明细（物料+数量）')
    setSubmitting(true)
    try {
      const r = await api.createDoc('stock-in', {
        in_no: header.in_no.trim(), in_type: header.in_type,
        warehouse_code: header.warehouse_code, po_no: header.po_no || '',
        in_date: header.in_date.format('YYYY-MM-DD'), remark: header.remark,
      }, validItems.map((it) => ({
        material_id: it.material_id, quantity: it.quantity, remark: it.remark,
      })), operator || 'frontend-react')
      if (r.ok) {
        Modal.success({
          title: `✅ 入库单 ${r.doc_no} 已入库（库存已增加）`,
          content: (r.warnings || []).length ? `提示：\n${(r.warnings || []).join('\n')}` : '库存结果表与流水已同步更新。',
        })
        setItems([newStockItem(1)])
        suggestNo()
      } else {
        Modal.error({ title: '写入被拒绝（数据库未改动）', content: r.errors.join('\n') })
      }
    } catch (e) {
      message.error(`提交失败: ${(e as Error).message}`)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div style={{ maxWidth: 980, margin: '0 auto' }}>
      <Title level={4}>📥 入库单录入 <Text type="secondary" style={{ fontSize: 14, fontWeight: 'normal' }}>生产完工/采购/退货 ｜ 落库即增库存</Text></Title>

      <Card size="small" title="入库头" style={{ marginBottom: 16 }}>
        <Row gutter={16}>
          <Col span={6}><Text type="secondary">入库单号 *（自动建议）</Text>
            <Space.Compact style={{ width: '100%' }}>
              <Input value={header.in_no} onChange={(e) => set('in_no', e.target.value)} placeholder="IN+日期+流水" />
              <Button icon={<ReloadOutlined />} onClick={suggestNo} title="重新建议" />
            </Space.Compact></Col>
          <Col span={5}><Text type="secondary">入库类型 *</Text>
            <Select style={{ width: '100%' }} value={header.in_type}
              onChange={(v) => { set('in_type', v); if (v !== 'purchase') set('po_no', null) }}
              options={[
                { value: 'production', label: '生产完工入库' },
                { value: 'purchase', label: '采购入库' },
                { value: 'return', label: '退货入库' },
              ]} /></Col>
          <Col span={5}><Text type="secondary">仓库 *</Text>
            <Select style={{ width: '100%' }} placeholder="选择仓库" value={header.warehouse_code}
              onChange={(v) => set('warehouse_code', v)}
              options={warehouses.map((w) => ({ value: w.code, label: `${w.code} - ${w.name}` }))} /></Col>
          <Col span={4}><Text type="secondary">入库日期 *</Text>
            <DatePicker style={{ width: '100%' }} value={header.in_date} onChange={(v) => v && set('in_date', v)} /></Col>
          <Col span={4}><Text type="secondary">备注</Text>
            <Input value={header.remark} onChange={(e) => set('remark', e.target.value)} /></Col>
        </Row>
        {header.in_type === 'purchase' && (
          <Row gutter={16} style={{ marginTop: 12 }}>
            <Col span={8}><Text type="secondary">关联采购单 *</Text>
              <Select style={{ width: '100%' }} placeholder="选择采购单" value={header.po_no}
                onChange={(v) => set('po_no', v)}
                options={pos.map((p) => ({
                  value: p.po_no as string,
                  label: `${p.po_no} - ${p.supplier_code}（${String(p.order_date).slice(0, 10)}）`,
                }))} /></Col>
          </Row>
        )}
      </Card>

      <Card size="small" title="入库明细" style={{ marginBottom: 16 }}>
        <StockItemsEditor products={products} items={items} onChange={setItems} />
      </Card>

      <Card size="small" style={{ marginBottom: 24 }}>
        <Row align="middle">
          <Col span={4}><Statistic title="明细行" value={validItems.length} /></Col>
          <Col span={5}><Statistic title="总数量(卷)" value={validItems.reduce((s, it) => s + (it.quantity || 0), 0)} /></Col>
          <Col span={15} style={{ textAlign: 'right' }}>
            <Space>
              <Input placeholder="操作人" style={{ width: 160 }} value={operator} onChange={(e) => setOperator(e.target.value)} />
              <Button type="primary" size="large" loading={submitting} onClick={onSubmit}>提交入库单</Button>
            </Space>
          </Col>
        </Row>
        <Text type="secondary" style={{ fontSize: 12 }}>提交即确认（confirmed）：库存结果表 + 出入库流水同步更新；采购入库会自动推进采购单到货状态。</Text>
      </Card>
    </div>
  )
}
