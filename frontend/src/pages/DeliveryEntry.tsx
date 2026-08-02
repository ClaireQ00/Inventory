// 发货录入页 (F2.6) — 按合同未发量发货, 超发后端拦截
// 选合同 → 未发明细带出(默认发全部未发) → 提交后回写合同已发数+状态联动
import { useEffect, useState } from 'react'
import {
  Alert, App, Button, Card, Col, DatePicker, Input, InputNumber, Modal, Row, Select,
  Space, Table, Tag, Typography,
} from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { api, type Customer } from '@/api/client'

const { Text, Title } = Typography

interface ShipRow {
  key: string
  item_no: string
  material_id: string
  spec: string
  quantity: number      // 合同数
  delivered_qty: number // 已发
  pending_qty: number   // 未发
  ship_qty: number | null // 本次发
}

export default function DeliveryEntry() {
  const { message } = App.useApp()
  const [customers, setCustomers] = useState<Customer[]>([])
  const [contracts, setContracts] = useState<Record<string, unknown>[]>([])
  const [header, setHeader] = useState({
    delivery_no: '', customer_code: null as string | null, contract_no: null as string | null,
    delivery_date: dayjs(), receiver: '', receiver_phone: '', receiver_address: '',
    transport_no: '', remark: '',
  })
  const [rows, setRows] = useState<ShipRow[]>([])
  const [operator, setOperator] = useState('')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    api.customers().then(setCustomers).catch((e) => message.error(`客户加载失败: ${e.message}`))
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const suggestNo = () => {
    api.suggestDocNo('delivery').then((r) => setHeader((h) => ({ ...h, delivery_no: r.doc_no }))).catch(() => {})
  }

  const onCustomer = (code: string) => {
    setHeader((h) => ({ ...h, customer_code: code, contract_no: null }))
    setRows([])
    api.contracts(code).then((list) => setContracts(list as unknown as Record<string, unknown>[])).catch(() => setContracts([]))
    if (!header.delivery_no) suggestNo()
  }

  const onContract = async (contractNo: string) => {
    setHeader((h) => ({ ...h, contract_no: contractNo }))
    try {
      const d = await api.contractPending(contractNo)
      if (!d.found) return message.warning(`合同 ${contractNo} 不存在`)
      setRows(d.items.map((it) => ({
        key: String(it.item_no),
        item_no: String(it.item_no),
        material_id: String(it.material_id),
        spec: String(it.spec || ''),
        quantity: Number(it.quantity),
        delivered_qty: Number(it.delivered_qty),
        pending_qty: Number(it.pending_qty),
        ship_qty: Number(it.pending_qty) > 0 ? Number(it.pending_qty) : null,
      })).filter((r) => r.pending_qty > 0))
      if (d.items.every((it) => Number(it.pending_qty) === 0)) {
        message.info(`合同 ${contractNo} 已全部发完`)
      }
    } catch (e) {
      message.error(`合同明细读取失败: ${(e as Error).message}`)
    }
  }

  const set = (k: string, v: unknown) => setHeader((h) => ({ ...h, [k]: v }))
  const shipRows = rows.filter((r) => r.ship_qty && r.ship_qty > 0)

  const onSubmit = async () => {
    if (!header.customer_code) return message.warning('请选择客户')
    if (!header.delivery_no.trim()) return message.warning('请填发货单号')
    if (shipRows.length === 0) return message.warning('没有可发货的明细行')
    setSubmitting(true)
    try {
      const r = await api.createDoc('delivery', {
        delivery_no: header.delivery_no.trim(),
        customer_code: header.customer_code,
        delivery_date: header.delivery_date.format('YYYY-MM-DD'),
        receiver: header.receiver, receiver_phone: header.receiver_phone,
        receiver_address: header.receiver_address, transport_no: header.transport_no,
        remark: header.remark,
      }, shipRows.map((r2) => ({
        contract_no: header.contract_no, contract_item_no: r2.item_no, quantity: r2.ship_qty,
      })), operator || 'frontend-react')
      if (r.ok) {
        Modal.success({
          title: `✅ 发货单 ${r.doc_no} 已入库`,
          content: '合同已发数已回写，状态自动联动（全部发完→已完成，否则→发货中）。',
        })
        setRows([])
        setHeader((h) => ({ ...h, contract_no: null }))
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
    <div style={{ maxWidth: 1080, margin: '0 auto' }}>
      <Title level={4}>🚚 发货录入 <Text type="secondary" style={{ fontSize: 14, fontWeight: 'normal' }}>按合同未发量发货 ｜ 超发自动拦截</Text></Title>

      <Card size="small" title="发货头" style={{ marginBottom: 16 }}>
        <Row gutter={16}>
          <Col span={6}><Text type="secondary">客户 *</Text>
            <Select style={{ width: '100%' }} placeholder="选择客户" value={header.customer_code} onChange={onCustomer}
              options={customers.map((c) => ({ value: c.code, label: `${c.code} - ${c.name}` }))} /></Col>
          <Col span={6}><Text type="secondary">关联合同 *（带出未发明细）</Text>
            <Select
              style={{ width: '100%' }} placeholder={header.customer_code ? '选择合同' : '先选客户'}
              value={header.contract_no} onChange={onContract}
              options={contracts.map((c) => ({
                value: String(c.contract_no),
                label: `${c.contract_no} · ${c.total_amount} ${c.currency} · ${c.status}`,
              }))}
            /></Col>
          <Col span={6}><Text type="secondary">发货单号 *（自动建议）</Text>
            <Space.Compact style={{ width: '100%' }}>
              <Input value={header.delivery_no} onChange={(e) => set('delivery_no', e.target.value)} placeholder="DN+日期+流水" />
              <Button icon={<ReloadOutlined />} onClick={suggestNo} title="重新建议" />
            </Space.Compact></Col>
          <Col span={6}><Text type="secondary">发货日期 *</Text>
            <DatePicker style={{ width: '100%' }} value={header.delivery_date} onChange={(v) => v && set('delivery_date', v)} /></Col>
        </Row>
        <Row gutter={16} style={{ marginTop: 12 }}>
          <Col span={4}><Text type="secondary">收货人</Text>
            <Input value={header.receiver} onChange={(e) => set('receiver', e.target.value)} /></Col>
          <Col span={4}><Text type="secondary">收货电话</Text>
            <Input value={header.receiver_phone} onChange={(e) => set('receiver_phone', e.target.value)} /></Col>
          <Col span={8}><Text type="secondary">收货地址</Text>
            <Input value={header.receiver_address} onChange={(e) => set('receiver_address', e.target.value)} /></Col>
          <Col span={4}><Text type="secondary">物流单号</Text>
            <Input value={header.transport_no} onChange={(e) => set('transport_no', e.target.value)} /></Col>
          <Col span={4}><Text type="secondary">备注</Text>
            <Input value={header.remark} onChange={(e) => set('remark', e.target.value)} /></Col>
        </Row>
      </Card>

      <Card size="small" title="发货明细（默认发全部未发，可改数量）" style={{ marginBottom: 16 }}>
        {rows.length === 0 ? (
          <Alert type="info" message="先选择客户和合同，未发明细自动带出" />
        ) : (
          <Table
            size="small" rowKey="key" dataSource={rows} pagination={false}
            columns={[
              { title: '行号', dataIndex: 'item_no', width: 60 },
              { title: '物料', dataIndex: 'material_id', width: 140 },
              { title: '规格', dataIndex: 'spec', render: (v: string) => <Text type="secondary">{v || '—'}</Text> },
              { title: '合同数', dataIndex: 'quantity', width: 90 },
              { title: '已发', dataIndex: 'delivered_qty', width: 80 },
              { title: '未发', dataIndex: 'pending_qty', width: 80,
                render: (v: number) => <Tag color="orange">{v}</Tag> },
              { title: '本次发 *', width: 130, render: (_: unknown, r: ShipRow) => (
                <InputNumber
                  style={{ width: 110 }} min={0} max={r.pending_qty}
                  value={r.ship_qty}
                  onChange={(v) => setRows(rows.map((x) => (x.key === r.key ? { ...x, ship_qty: v } : x)))}
                />
              ) },
            ]}
          />
        )}
      </Card>

      <Card size="small" style={{ marginBottom: 24 }}>
        <Row align="middle">
          <Col span={16}>
            <Text type="secondary">
              本次共发 {shipRows.reduce((s, r) => s + (r.ship_qty || 0), 0)} 卷 / {shipRows.length} 行；
              发货量超过合同未发量会被后端整体拦截回滚。
            </Text>
          </Col>
          <Col span={8} style={{ textAlign: 'right' }}>
            <Space>
              <Input placeholder="操作人" style={{ width: 160 }} value={operator} onChange={(e) => setOperator(e.target.value)} />
              <Button type="primary" size="large" loading={submitting} onClick={onSubmit} disabled={rows.length === 0}>提交发货单</Button>
            </Space>
          </Col>
        </Row>
      </Card>
    </div>
  )
}
