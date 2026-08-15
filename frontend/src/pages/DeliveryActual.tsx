// 发货单事后处理页 (🔴-4 / 🟡-7, 2026-08-15)
// 两个动作: ① 装柜后回填 actual_quantity (保管员 SOP, R13 实发口径唯一数据源)
//          ② 作废发货单 (仅 draft/confirmed, 反向冲减合同已发数, 原因必填留痕)
// 类比: ① 是"实收实发对齐"——先按计划开单, 装柜后把每行改成真实装柜数;
//       ② 是"整单退货"——单子开错了整张作废, 合同的已发数像退快递一样退回去。
import { useEffect, useState } from 'react'
import {
  Alert, App, Button, Card, Col, Input, InputNumber, Modal, Row, Select, Space, Table, Tag, Typography,
} from 'antd'
import { api } from '@/api/client'
import { selectFilter } from '@/lib/fuzzy'

const { Text, Title } = Typography

interface ActualRow {
  key: string
  contract_no: string
  contract_item_no: string
  material_id: string
  spec: string
  delivery_qty: number   // 计划数
  old_actual: number     // 回填前实发
  actual: number | null  // 本次填的实发
}

export default function DeliveryActual() {
  const { message } = App.useApp()
  const [deliveries, setDeliveries] = useState<Record<string, unknown>[]>([])
  const [deliveryNo, setDeliveryNo] = useState<string | null>(null)
  const [rows, setRows] = useState<ActualRow[]>([])
  const [operator, setOperator] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [cancelReason, setCancelReason] = useState('')
  const [cancelling, setCancelling] = useState(false)

  const loadDeliveries = () => {
    api.deliveries().then((list) => setDeliveries(list as unknown as Record<string, unknown>[]))
      .catch((e) => message.error(`发货单加载失败: ${e.message}`))
  }

  useEffect(loadDeliveries, []) // eslint-disable-line react-hooks/exhaustive-deps

  const onPick = async (no: string) => {
    setDeliveryNo(no)
    setCancelReason('')
    try {
      const list = await api.deliveryMaterials(no)
      setRows(list.map((it) => ({
        key: `${it.contract_no}#${it.contract_item_no}`,
        contract_no: String(it.contract_no || ''),
        contract_item_no: String(it.contract_item_no || ''),
        material_id: String(it.material_id),
        spec: String(it.spec || ''),
        delivery_qty: Number(it.delivery_qty),
        old_actual: Number(it.actual_quantity ?? it.delivery_qty),
        actual: Number(it.actual_quantity ?? it.delivery_qty),
      })))
    } catch (e) {
      message.error(`发货明细读取失败: ${(e as Error).message}`)
      setRows([])
    }
  }

  const changedRows = rows.filter((r) => r.actual !== null && r.actual !== r.old_actual)

  const onSubmit = async () => {
    if (!deliveryNo) return message.warning('请选择发货单')
    if (changedRows.length === 0) return message.warning('没有改动的行 (实发数与当前值相同)')
    setSubmitting(true)
    try {
      const r = await api.deliveryActual(deliveryNo, changedRows.map((x) => ({
        contract_no: x.contract_no, contract_item_no: x.contract_item_no, actual_quantity: x.actual,
      })), operator || 'frontend-react')
      if (r.ok) {
        Modal.success({
          title: `✅ ${r.doc_no} 实发数已回填`,
          content: `短装数自动重算；合同 ${r.contracts_updated.join('、')} 已按差额修正已发数。`,
        })
        await onPick(deliveryNo)
      } else {
        Modal.error({ title: '回填被拒绝（数据库未改动）', content: <div style={{ whiteSpace: 'pre-line' }}>{r.errors.join('\n')}</div> })
      }
    } catch (e) {
      message.error(`提交失败: ${(e as Error).message}`)
    } finally {
      setSubmitting(false)
    }
  }

  const onCancel = () => {
    if (!deliveryNo) return message.warning('请选择发货单')
    if (!cancelReason.trim()) return message.warning('作废原因必填 (无原因无法追溯)')
    const backfilled = rows.some((r) => r.old_actual !== r.delivery_qty)
    Modal.confirm({
      title: `确认作废 ${deliveryNo}？`,
      content: (
        <div style={{ whiteSpace: 'pre-line' }}>
          {backfilled ? '注意：该单已回填过实发数，作废会按实发数反向冲减合同已发数。\n' : ''}
          作废后不可恢复；合同状态会自动重算。原因：{cancelReason.trim()}
        </div>
      ),
      okText: '作废',
      okButtonProps: { danger: true },
      onOk: async () => {
        setCancelling(true)
        try {
          const r = await api.deliveryCancel(deliveryNo, cancelReason.trim(), operator || 'frontend-react')
          if (r.ok) {
            Modal.success({ title: `🗑️ ${r.doc_no} 已作废`, content: (r.warnings || []).join('\n') })
            setDeliveryNo(null)
            setRows([])
            setCancelReason('')
            loadDeliveries()
          } else {
            Modal.error({ title: '作废被拒绝', content: <div style={{ whiteSpace: 'pre-line' }}>{r.errors.join('\n')}</div> })
          }
        } catch (e) {
          message.error(`作废失败: ${(e as Error).message}`)
        } finally {
          setCancelling(false)
        }
      },
    })
  }

  return (
    <div style={{ maxWidth: 1080, margin: '0 auto' }}>
      <Title level={4}>🚢 发货单处理 <Text type="secondary" style={{ fontSize: 14, fontWeight: 'normal' }}>装柜后回填实发数 ｜ 整单作废</Text></Title>

      <Card size="small" title="选择发货单" style={{ marginBottom: 16 }}>
        <Row gutter={16}>
          <Col span={10}><Text type="secondary">发货单 *</Text>
            <Select
              style={{ width: '100%' }} placeholder="选择要处理的发货单 (cancelled 已排除)"
              value={deliveryNo} onChange={onPick}
              showSearch filterOption={selectFilter}
              options={deliveries.map((d) => ({
                value: String(d.delivery_no),
                label: `${d.delivery_no} · ${d.customer_code} · ${d.delivery_date} · ${d.status}`,
              }))}
            /></Col>
          <Col span={14}>
            <Alert type="info" showIcon message="回填实发数 = 把计划数改成装柜后的真实数（短装/超装）；作废 = 整单取消并冲回合同已发数。两处都会留审计。" />
          </Col>
        </Row>
      </Card>

      <Card size="small" title={deliveryNo ? `实发数回填 — ${deliveryNo}（装柜后保管员填写）` : '实发数回填（先选择发货单）'} style={{ marginBottom: 16 }}>
        {rows.length === 0 ? (
          <Alert type="info" message="选择发货单后明细自动带出；实发数默认等于计划数，改动的行才会提交" />
        ) : (
          <>
            <Table
              size="small" rowKey="key" dataSource={rows} pagination={false}
              columns={[
                { title: '合同', dataIndex: 'contract_no', width: 130 },
                { title: '行', dataIndex: 'contract_item_no', width: 60 },
                { title: '物料', dataIndex: 'material_id', width: 140 },
                { title: '规格', dataIndex: 'spec', render: (v: string) => <Text type="secondary">{v || '—'}</Text> },
                { title: '计划数', dataIndex: 'delivery_qty', width: 90 },
                { title: '当前实发', dataIndex: 'old_actual', width: 90,
                  render: (v: number, r: ActualRow) => (v !== r.delivery_qty
                    ? <Tag color="orange">{v}</Tag> : <Tag>{v}</Tag>) },
                { title: '实发数 *', width: 130, render: (_: unknown, r: ActualRow) => (
                  <InputNumber
                    style={{ width: 110 }} min={0}
                    value={r.actual}
                    onChange={(v) => setRows(rows.map((x) => (x.key === r.key ? { ...x, actual: v } : x)))}
                  />
                ) },
                { title: '短装', width: 80, render: (_: unknown, r: ActualRow) => {
                  const short = r.delivery_qty - (r.actual ?? r.old_actual)
                  return short === 0 ? <Tag color="green">0</Tag> : <Tag color="red">{short}</Tag>
                } },
              ]}
            />
            <Row align="middle" style={{ marginTop: 12 }}>
              <Col span={16}>
                <Text type="secondary">
                  本次改动 {changedRows.length} 行；回填会使合同累计已发超过合同量的行会被后端拦截。实发 0 = 整行短装。
                </Text>
              </Col>
              <Col span={8} style={{ textAlign: 'right' }}>
                <Space>
                  <Input placeholder="操作人" style={{ width: 160 }} value={operator} onChange={(e) => setOperator(e.target.value)} />
                  <Button type="primary" loading={submitting} onClick={onSubmit} disabled={rows.length === 0}>提交回填</Button>
                </Space>
              </Col>
            </Row>
          </>
        )}
      </Card>

      <Card size="small" title="作废发货单（危险操作，原因必填）">
        <Row gutter={16} align="middle">
          <Col span={16}>
            <Text type="secondary">作废原因 *</Text>
            <Input
              placeholder="如：客户改单 / 录错重开（留痕审计，不可为空）"
              value={cancelReason} onChange={(e) => setCancelReason(e.target.value)}
              disabled={!deliveryNo}
            />
          </Col>
          <Col span={8} style={{ textAlign: 'right' }}>
            <Button danger loading={cancelling} onClick={onCancel} disabled={!deliveryNo}>
              🗑️ 作废 {deliveryNo || '发货单'}
            </Button>
          </Col>
        </Row>
        <Alert
          type="warning" showIcon style={{ marginTop: 12 }}
          message="仅 draft/confirmed 状态可作废；已装船（shipped）的单子涉及报关/收款，差异请走贷记单流程。作废会冲回合同已发数并自动重算合同状态。"
        />
      </Card>
    </div>
  )
}
