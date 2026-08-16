// 贷记单录入页 (🟡-10 差异闭环, 2026-08-15):
// 报关后发现的短装/超装差异, 挂到 具体报关单 + 合同明细行 上。
// diff_qty 正=短装 / 负=超装; 汇率按报关单 shipping_date 所在月自动带出 (R2);
// diff_amount_cny 由派生引擎算, 前端只展示不手填。
import { useEffect, useState } from 'react'
import {
  Alert, App, Button, Card, Col, Input, InputNumber, Modal, Row,
  Select, Space, Table, Typography,
} from 'antd'
import dayjs from 'dayjs'
import { api, type PreviewResp } from '@/api/client'
import { selectFilter } from '@/lib/fuzzy'

const { Text, Title } = Typography

interface ShipItem {
  key: string
  material_id: string
  planned_qty: number
  actual_qty: number
  unit_price_usd: number | null
  contract_no: string | null
  contract_item_no: string | null
}

const RESOLUTIONS = [
  { value: 'pending', label: 'pending（待处理）' },
  { value: 'replenish', label: 'replenish（补货）' },
  { value: 'refund', label: 'refund（退款）' },
  { value: 'writeoff', label: 'writeoff（核销）' },
]

export default function CreditNoteEntry() {
  const { message } = App.useApp()
  const [shippings, setShippings] = useState<Record<string, unknown>[]>([])
  const [items, setItems] = useState<ShipItem[]>([])
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  const [form, setForm] = useState({
    shipping_no: '',
    cn_no: `CN${dayjs().format('YYYYMMDD')}`,
    contract_no: '',
    contract_item_no: '',
    material_id: '',
    diff_qty: null as number | null,
    diff_amount: null as number | null,
    currency: 'USD',
    resolution: 'pending',
    remark: '',
  })
  const [operator, setOperator] = useState('')
  const [preview, setPreview] = useState<PreviewResp | null>(null)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  const set = (patch: Partial<typeof form>) => setForm((f) => ({ ...f, ...patch }))

  useEffect(() => {
    api.shippingRecords().then(setShippings).catch((e) => message.error(`报关单列表加载失败: ${e.message}`))
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const onShippingChange = (no: string) => {
    set({ shipping_no: no, contract_no: '', contract_item_no: '', material_id: '', diff_qty: null, diff_amount: null })
    setSelectedKey(null)
    setItems([])
    if (!no) return
    api.shippingItems(no).then((rows) => {
      const list: ShipItem[] = rows.map((r, i) => ({
        key: String(i),
        material_id: String(r.material_id || ''),
        planned_qty: Number(r.planned_qty || 0),
        actual_qty: Number(r.actual_qty || 0),
        unit_price_usd: r.unit_price_usd == null ? null : Number(r.unit_price_usd),
        contract_no: r.contract_no ? String(r.contract_no) : null,
        contract_item_no: r.contract_item_no ? String(r.contract_item_no) : null,
      }))
      setItems(list)
      const cur = shippings.find((s) => s.shipping_no === no)
      if (cur?.currency) set({ currency: String(cur.currency) })
    }).catch((e) => message.error(`报关明细加载失败: ${e.message}`))
  }

  // 选中报关行 → 带出 合同行 + 物料 + 建议差异数/金额 (计划-实发=短装为正)
  const onRowSelect = (key: string) => {
    const it = items.find((r) => r.key === key)
    if (!it) return
    setSelectedKey(key)
    const diffQty = it.planned_qty - it.actual_qty
    const diffAmount = it.unit_price_usd != null ? Number((diffQty * it.unit_price_usd).toFixed(2)) : null
    set({
      contract_no: it.contract_no || '',
      contract_item_no: it.contract_item_no || '',
      material_id: it.material_id,
      diff_qty: diffQty !== 0 ? diffQty : null,
      diff_amount: diffAmount,
    })
  }

  const buildData = () => ({
    cn_no: form.cn_no.trim(),
    shipping_no: form.shipping_no,
    contract_no: form.contract_no.trim(),
    contract_item_no: form.contract_item_no.trim(),
    material_id: form.material_id,
    diff_qty: form.diff_qty,
    diff_amount: form.diff_amount,
    currency: form.currency,
    resolution: form.resolution,
    remark: form.remark.trim(),
  })

  const onSubmit = async () => {
    if (!form.cn_no.trim()) return message.warning('请填贷记单号')
    if (!form.shipping_no) return message.warning('请选择报关单')
    if (!form.contract_no || !form.contract_item_no) return message.warning('请从报关明细中选中一行 (须带合同行)')
    if (form.diff_qty == null) return message.warning('请填差异数量 (正=短装, 负=超装)')
    if (form.diff_amount == null) return message.warning('请填差异金额 (原币)')
    try {
      const pv = await api.preview('credit_notes', buildData())
      setPreview(pv)
      setPreviewOpen(true)
    } catch (e) {
      message.error(`预览失败: ${(e as Error).message}`)
    }
  }

  const onConfirm = async () => {
    setSubmitting(true)
    try {
      const r = await api.insert('credit_notes', buildData(), operator || 'frontend-react')
      if (r.ok) {
        message.success(`✅ 贷记单已入库 (#${r.record_id})`)
        r.warnings.forEach((w) => message.warning(w, 6))
        setPreviewOpen(false)
        setForm((f) => ({ ...f, cn_no: `CN${dayjs().format('YYYYMMDD')}`, diff_qty: null, diff_amount: null, remark: '' }))
        setSelectedKey(null)
      } else {
        Modal.error({ title: '写入被拒绝（数据库未改动，已回滚）', content: r.errors.join('\n') })
      }
    } catch (e) {
      message.error(`提交失败: ${(e as Error).message}`)
    } finally {
      setSubmitting(false)
    }
  }

  const sel = items.find((r) => r.key === selectedKey)

  return (
    <div style={{ maxWidth: 1080, margin: '0 auto' }}>
      <Title level={4}>🧾 贷记单录入 <Text type="secondary" style={{ fontSize: 14, fontWeight: 'normal' }}>报关后短装/超装差异 ｜ 挂具体报关单+合同行 ｜ 汇率按报关月自动带出</Text></Title>

      <Card size="small" style={{ marginBottom: 16 }}>
        <Row gutter={16}>
          <Col span={10}><Text type="secondary">报关单 *</Text>
            <Select style={{ width: '100%' }} placeholder="选择报关单 (差异来源)" value={form.shipping_no || undefined}
              showSearch filterOption={selectFilter} onChange={onShippingChange}
              options={shippings.map((s) => ({
                value: String(s.shipping_no),
                label: `${s.shipping_no}（${s.shipping_date} · ${s.delivery_no} · ${Number(s.total_amount || 0).toLocaleString()} ${s.currency}）`,
              }))} /></Col>
          <Col span={6}><Text type="secondary">贷记单号 *</Text>
            <Input value={form.cn_no} onChange={(e) => set({ cn_no: e.target.value })} /></Col>
          <Col span={4}><Text type="secondary">币种 *</Text>
            <Select style={{ width: '100%' }} value={form.currency} onChange={(v) => set({ currency: v })}
              options={['USD', 'EUR', 'IDR', 'CNY'].map((c) => ({ value: c, label: c }))} /></Col>
          <Col span={4}><Text type="secondary">处理方式</Text>
            <Select style={{ width: '100%' }} value={form.resolution} onChange={(v) => set({ resolution: v })}
              options={RESOLUTIONS} /></Col>
        </Row>

        {items.length > 0 && (
          <Table<ShipItem> size="small" style={{ marginTop: 12 }} title={() => <Text type="secondary">报关明细（选中一行作为差异归属，自动带出合同行+建议差异）</Text>}
            rowSelection={{ type: 'radio', selectedRowKeys: selectedKey ? [selectedKey] : [], onChange: (keys) => onRowSelect(String(keys[0])) }}
            pagination={false} rowKey="key" dataSource={items}
            columns={[
              { title: '物料', dataIndex: 'material_id' },
              { title: '计划数', dataIndex: 'planned_qty', width: 90, align: 'right' },
              { title: '实发数', dataIndex: 'actual_qty', width: 90, align: 'right' },
              { title: '差异', key: 'diff', width: 90, align: 'right',
                render: (_, r) => <Text type={r.planned_qty - r.actual_qty > 0 ? 'danger' : 'success'}>{r.planned_qty - r.actual_qty}</Text> },
              { title: '单价', dataIndex: 'unit_price_usd', width: 100, align: 'right' },
              { title: '合同行', key: 'cno', render: (_, r) => r.contract_no ? `${r.contract_no}#${r.contract_item_no}` : '（未反解出）' },
            ]} />
        )}

        <Row gutter={16} style={{ marginTop: 12 }}>
          <Col span={5}><Text type="secondary">合同号 *</Text>
            <Input value={form.contract_no} onChange={(e) => set({ contract_no: e.target.value })} /></Col>
          <Col span={4}><Text type="secondary">合同行号 *</Text>
            <Input value={form.contract_item_no} onChange={(e) => set({ contract_item_no: e.target.value })} /></Col>
          <Col span={5}><Text type="secondary">物料编码 *</Text>
            <Input value={form.material_id} onChange={(e) => set({ material_id: e.target.value })} /></Col>
          <Col span={4}><Text type="secondary">差异数量 *（正=短装 负=超装）</Text>
            <InputNumber style={{ width: '100%' }} precision={0} value={form.diff_qty} onChange={(v) => set({ diff_qty: v })} /></Col>
          <Col span={6}><Text type="secondary">差异金额（原币）*</Text>
            <InputNumber style={{ width: '100%' }} value={form.diff_amount} onChange={(v) => set({ diff_amount: v })} /></Col>
        </Row>
        <Row gutter={16} style={{ marginTop: 12 }}>
          <Col span={16}><Text type="secondary">备注</Text>
            <Input value={form.remark} onChange={(e) => set({ remark: e.target.value })} /></Col>
        </Row>
        <Space style={{ marginTop: 16 }}>
          <Input placeholder="操作人（写入审计日志）" style={{ width: 200 }} value={operator} onChange={(e) => setOperator(e.target.value)} />
          <Button type="primary" size="large" onClick={onSubmit}>预览并提交</Button>
        </Space>
      </Card>

      {/* ── 两段式: 预览 Modal (汇率带出 + 折 CNY) ── */}
      <Modal
        title="确认入库（预览 → 确认 → 落库）"
        open={previewOpen}
        onOk={onConfirm}
        onCancel={() => setPreviewOpen(false)}
        okText="确认入库" cancelText="返回修改"
        confirmLoading={submitting}
        okButtonProps={{ disabled: (preview?.errors.length || 0) > 0 }}
        width={560}
      >
        {(preview?.errors.length || 0) > 0 && (
          <Alert type="error" style={{ marginBottom: 12 }} message="校验未通过"
            description={<ul style={{ margin: 0, paddingLeft: 18 }}>{preview?.errors.map((e, i) => <li key={i}>{e}</li>)}</ul>} />
        )}
        {preview?.rate_note && <Alert type="info" style={{ marginBottom: 12 }} message={preview.rate_note} />}
        {preview && (
          <Table
            size="small" pagination={false} showHeader={false}
            dataSource={[
              ['贷记单号', form.cn_no],
              ['报关单', form.shipping_no],
              ['合同行', `${form.contract_no}#${form.contract_item_no}`],
              ['物料', form.material_id],
              ['差异数量', `${form.diff_qty}（${(form.diff_qty || 0) > 0 ? '短装' : '超装'}）`],
              ['差异金额', `${Number(form.diff_amount).toLocaleString()} ${form.currency}`],
              ['汇率', preview.derived_row.exchange_rate ? String(preview.derived_row.exchange_rate) : '（未带出）'],
              ['折 CNY', preview.derived_row.diff_amount_cny ? `¥ ${Number(preview.derived_row.diff_amount_cny).toLocaleString()}` : '—'],
              ['处理方式', form.resolution],
            ].map(([k, v], i) => ({ k, v, i }))}
            columns={[
              { dataIndex: 'k', width: 110, render: (v) => <Text type="secondary">{v}</Text> },
              { dataIndex: 'v', render: (v) => <b>{v}</b> },
            ]}
            rowKey="i"
          />
        )}
      </Modal>
      {sel && (sel.contract_no == null) && (
        <Alert type="warning" message="选中行的合同行未反解出来（报关明细与发货明细对不上），请人工核对合同号+行号后再提交" />
      )}
    </div>
  )
}
