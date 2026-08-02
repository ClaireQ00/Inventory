// 辅料收发存页 — 入库/出库(生产领用)/库存查询+流水 (M2)
// 护栏: 出库库存不足后端回滚拦截; after_qty 由后端库存行算, 不信前端
import { useCallback, useEffect, useState } from 'react'
import {
  Alert, App, Button, Card, Col, DatePicker, Input, InputNumber, Row, Select,
  Space, Table, Tabs, Tag, Typography,
} from 'antd'
import dayjs from 'dayjs'
import { api } from '@/api/client'

const { Text, Title } = Typography

const SOURCE_IN = [{ value: 'purchase', label: '采购入库' }, { value: 'adjust', label: '盘点调整' }]
const SOURCE_OUT = [{ value: 'production_use', label: '生产领用' }, { value: 'scrap', label: '报废' }, { value: 'adjust', label: '盘点调整' }]

export default function AuxStock() {
  const { message } = App.useApp()
  const [materials, setMaterials] = useState<Record<string, unknown>[]>([])
  const [warehouses, setWarehouses] = useState<{ code: string; name: string }[]>([])
  const [operator, setOperator] = useState('')
  const [inventory, setInventory] = useState<Record<string, unknown>[]>([])
  const [moves, setMoves] = useState<Record<string, unknown>[]>([])
  const [demand, setDemand] = useState<Record<string, unknown> | null>(null)

  const [inForm, setInForm] = useState({ aux_code: null as string | null, warehouse_code: 'AUX', qty: null as number | null, source_type: 'purchase', source_no: '', remark: '', move_date: dayjs() })
  const [outForm, setOutForm] = useState({ aux_code: null as string | null, warehouse_code: 'AUX', qty: null as number | null, source_type: 'production_use', source_no: '', remark: '', move_date: dayjs() })

  const reloadStock = useCallback(() => {
    api.auxInventory().then(setInventory).catch(() => {})
    api.auxMoves().then(setMoves).catch(() => {})
  }, [])

  useEffect(() => {
    // 只拉标签纸: 包装/喷码等是纯档案不计量, 不出现在收发存选择器里 (后端也有同款护栏)
    api.auxMaterials('label_paper').then(setMaterials).catch((e) => message.error(`辅料档案加载失败: ${e.message}`))
    api.warehouses().then(setWarehouses).catch(() => {})
    reloadStock()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const auxOptions = materials.map((m) => ({
    value: m.aux_code as string,
    label: `${m.aux_code} - ${m.name || ''}（库存 ${m.stock_total}）`,
  }))
  const whOptions = warehouses.map((w) => ({ value: w.code, label: `${w.code} - ${w.name}` }))

  // 出库时填了合同号 → 自动算该合同标签需求做参照 (M3 联动, 只提示不扣减)
  const onContractBlur = async () => {
    const no = outForm.source_no.trim()
    if (!no) { setDemand(null); return }
    try {
      const d = await api.auxLabelDemand(no)
      setDemand(d as unknown as Record<string, unknown>)
      if (!d.found) message.warning(`合同 ${no} 不存在`)
    } catch { setDemand(null) }
  }

  const submit = async (direction: 'in' | 'out') => {
    const f = direction === 'in' ? inForm : outForm
    if (!f.aux_code) return message.warning('请选择辅料')
    if (!f.qty || f.qty <= 0) return message.warning('请填数量')
    const fn = direction === 'in' ? api.auxStockIn : api.auxStockOut
    const r = await fn({
      aux_code: f.aux_code, warehouse_code: f.warehouse_code, qty: f.qty,
      source_type: f.source_type, source_no: f.source_no.trim(),
      operator: operator || 'frontend-react',
      move_date: f.move_date.format('YYYY-MM-DD'), remark: f.remark,
    })
    if (r.ok) {
      message.success(`✅ ${direction === 'in' ? '入库' : '出库'}完成 ${r.move_no}，结余 ${r.after_qty} 张`)
      reloadStock()
      if (direction === 'in') setInForm({ ...inForm, qty: null, source_no: '', remark: '' })
      else setOutForm({ ...outForm, qty: null, remark: '' })
    } else {
      message.error(r.errors.join('；'), 8)
    }
  }

  const moveForm = (direction: 'in' | 'out') => {
    const f = direction === 'in' ? inForm : outForm
    const setF = direction === 'in' ? setInForm : setOutForm
    const sources = direction === 'in' ? SOURCE_IN : SOURCE_OUT
    return (
      <Card size="small" style={{ maxWidth: 720 }}>
        <Row gutter={16}>
          <Col span={12}><Text type="secondary">辅料 *</Text>
            <Select style={{ width: '100%' }} showSearch optionFilterProp="label"
              value={f.aux_code} onChange={(v) => setF({ ...f, aux_code: v })} options={auxOptions} placeholder="选择辅料" /></Col>
          <Col span={6}><Text type="secondary">仓库</Text>
            <Select style={{ width: '100%' }} value={f.warehouse_code} onChange={(v) => setF({ ...f, warehouse_code: v })} options={whOptions} /></Col>
          <Col span={6}><Text type="secondary">数量(张) *</Text>
            <InputNumber style={{ width: '100%' }} min={1} value={f.qty} onChange={(v) => setF({ ...f, qty: v })} /></Col>
        </Row>
        <Row gutter={16} style={{ marginTop: 12 }}>
          <Col span={6}><Text type="secondary">来源类型</Text>
            <Select style={{ width: '100%' }} value={f.source_type} onChange={(v) => setF({ ...f, source_type: v })} options={sources} /></Col>
          <Col span={8}><Text type="secondary">{direction === 'out' && f.source_type === 'production_use' ? '关联合同号（自动算需求参照）' : '关联单号（可空）'}</Text>
            <Input value={f.source_no} onChange={(e) => setF({ ...f, source_no: e.target.value })}
              onBlur={direction === 'out' ? onContractBlur : undefined} placeholder={direction === 'out' ? '如 SC20260730001' : '如 PO20260731001'} /></Col>
          <Col span={5}><Text type="secondary">日期</Text>
            <DatePicker style={{ width: '100%' }} value={f.move_date} onChange={(v) => v && setF({ ...f, move_date: v })} /></Col>
          <Col span={5}><Text type="secondary">备注</Text>
            <Input value={f.remark} onChange={(e) => setF({ ...f, remark: e.target.value })} /></Col>
        </Row>
        {direction === 'out' && demand != null && Boolean(demand.found) && (
          <Alert style={{ marginTop: 12 }}
            type={demand.all_sufficient ? 'success' : 'warning'}
            message={`合同 ${demand.contract_no} 标签需求`}
            description={
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {((demand.lines as Record<string, unknown>[]) || []).map((l) => (
                  <li key={l.aux_code as string}>
                    {l.aux_code as string}（{l.name as string}）：需 <b>{l.required as number}</b> 张 / 库存 {l.in_stock as number} 张
                    {Number(l.shortage) > 0 && <Text type="danger"> → 缺 {l.shortage as number} 张</Text>}
                    {Boolean(l.profile_missing) && <Tag color="orange" style={{ marginLeft: 6 }}>辅料库未建档</Tag>}
                  </li>
                ))}
              </ul>
            } />
        )}
        <Space style={{ marginTop: 16 }}>
          <Input placeholder="操作人" style={{ width: 160 }} value={operator} onChange={(e) => setOperator(e.target.value)} />
          <Button type="primary" onClick={() => submit(direction)}>
            确认{direction === 'in' ? '入库' : '出库'}
          </Button>
        </Space>
      </Card>
    )
  }

  return (
    <div style={{ maxWidth: 1080, margin: '0 auto' }}>
      <Title level={4}>📦 辅料收发存 <Text type="secondary" style={{ fontSize: 14, fontWeight: 'normal' }}>入库 / 生产领用出库 / 库存计数 / 流水账</Text></Title>
      <Tabs
        items={[
          { key: 'in', label: '📥 入库', children: moveForm('in') },
          { key: 'out', label: '📤 出库（生产领用）', children: moveForm('out') },
          {
            key: 'stock', label: '📊 库存与流水', children: (
              <>
                <Table size="small" rowKey={(r) => `${r.aux_code}-${r.warehouse_code}`} dataSource={inventory} pagination={false} style={{ marginBottom: 16 }}
                  columns={[
                    { title: '辅料', dataIndex: 'aux_code', width: 130 },
                    { title: '名称', dataIndex: 'name' },
                    { title: '仓库', dataIndex: 'warehouse_code', width: 100, render: (v, r) => `${v} ${(r.warehouse_name as string) || ''}` },
                    { title: '库存(张)', dataIndex: 'quantity', width: 100,
                      render: (v: number, r) => <Text strong type={r.low_stock ? 'danger' : undefined}>{v}{Boolean(r.low_stock) && <Tag color="red" style={{ marginLeft: 6 }}>低库存</Tag>}</Text> },
                    { title: '安全库存', dataIndex: 'min_stock', width: 90, render: (v) => v ?? '—' },
                    { title: '更新时间', dataIndex: 'updated_at', width: 160, render: (v) => String(v).replace('T', ' ').slice(0, 19) },
                  ]} />
                <Title level={5}>收发流水</Title>
                <Table size="small" rowKey="id" dataSource={moves} pagination={{ pageSize: 20 }}
                  columns={[
                    { title: '单号', dataIndex: 'move_no', width: 200 },
                    { title: '辅料', dataIndex: 'aux_code', width: 120 },
                    { title: '方向', dataIndex: 'direction', width: 70, render: (v) => v === 'in' ? <Tag color="green">入库</Tag> : <Tag color="orange">出库</Tag> },
                    { title: '数量', dataIndex: 'change_qty', width: 80, render: (v: number) => (v > 0 ? `+${v}` : v) },
                    { title: '结余', dataIndex: 'after_qty', width: 80 },
                    { title: '来源', dataIndex: 'source_type', width: 110, render: (v) => ({ purchase: '采购入库', production_use: '生产领用', adjust: '盘点调整', scrap: '报废' } as Record<string, string>)[v] || v },
                    { title: '关联单号', dataIndex: 'source_no', width: 150 },
                    { title: '日期', dataIndex: 'move_date', width: 110, render: (v) => String(v).slice(0, 10) },
                    { title: '操作人', dataIndex: 'operator', width: 110 },
                  ]} />
              </>
            ),
          },
        ]}
      />
    </div>
  )
}
