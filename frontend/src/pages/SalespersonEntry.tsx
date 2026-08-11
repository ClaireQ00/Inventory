// 业务员档案管理页 (2026-08-11) — 基础资料: 建档/编辑/停用
// 规则: code(首字母)+digit(首位数字) 是客户编码的锚, 建档后不可改;
//       客户编码 = 字母(业务员) + digit + 3位流水, 换业务员只换字母
import { useEffect, useState } from 'react'
import { App, Badge, Button, Card, Col, Input, InputNumber, Modal, Row, Space, Switch, Table, Typography } from 'antd'
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import { api, type SalespersonFull } from '@/api/client'

const { Text, Title, Paragraph } = Typography

const EMPTY_FORM = { code: '', name: '', digit: '', phone: '', commission_rate: null as number | null, remark: '' }

export default function SalespersonEntry() {
  const { message } = App.useApp()
  const [rows, setRows] = useState<SalespersonFull[]>([])
  const [loading, setLoading] = useState(false)
  const [operator, setOperator] = useState('')
  // 建档小窗
  const [createOpen, setCreateOpen] = useState(false)
  const [createForm, setCreateForm] = useState({ ...EMPTY_FORM })
  const [submitting, setSubmitting] = useState(false)
  // 编辑小窗
  const [editOpen, setEditOpen] = useState(false)
  const [editTarget, setEditTarget] = useState<SalespersonFull | null>(null)
  const [editForm, setEditForm] = useState({ name: '', phone: '', commission_rate: null as number | null, is_active: 1, remark: '' })

  const load = () => {
    setLoading(true)
    api.salespersonsFull().then(setRows).catch((e) => message.error(`加载失败: ${(e as Error).message}`))
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  const usedDigits = rows.map((r) => r.digit)
  const freeDigits = '0123456789'.split('').filter((d) => !usedDigits.includes(d))

  const onCreate = async () => {
    setSubmitting(true)
    try {
      const r = await api.createSalesperson({ ...createForm }, operator || 'frontend-react')
      if (r.ok) {
        message.success(`业务员 ${r.code} 已建档`)
        setCreateOpen(false)
        setCreateForm({ ...EMPTY_FORM })
        load()
      } else {
        Modal.error({ title: '建档被拒绝', content: r.errors.join('\n') })
      }
    } catch (e) {
      message.error(`提交失败: ${(e as Error).message}`)
    } finally {
      setSubmitting(false)
    }
  }

  const openEdit = (r: SalespersonFull) => {
    setEditTarget(r)
    setEditForm({
      name: r.name || '', phone: r.phone || '',
      commission_rate: r.commission_rate, is_active: r.is_active, remark: r.remark || '',
    })
    setEditOpen(true)
  }

  const onUpdate = async () => {
    if (!editTarget) return
    setSubmitting(true)
    try {
      const r = await api.updateSalesperson(editTarget.code, { ...editForm }, operator || 'frontend-react')
      if (r.ok) {
        message.success(`业务员 ${r.code} 已更新`)
        setEditOpen(false)
        load()
      } else {
        Modal.error({ title: '更新被拒绝', content: r.errors.join('\n') })
      }
    } catch (e) {
      message.error(`提交失败: ${(e as Error).message}`)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div style={{ maxWidth: 1000, margin: '0 auto' }}>
      <Title level={4}>🧑‍💼 业务员档案 <Text type="secondary" style={{ fontSize: 14, fontWeight: 'normal' }}>客户编码的字母与首位数字来源</Text></Title>
      <Paragraph type="secondary" style={{ fontSize: 12 }}>
        规则：代码 = 客户编码首字母；首位数字 = 业务员数字编码（其名下客户编号的第一位数字）。
        客户换业务员只换编码字母、数字不变。代码和首位数字建档后不可改。
      </Paragraph>

      <Card size="small" style={{ marginBottom: 16 }}
        title={`档案列表（${rows.length}）`}
        extra={<Space>
          <Input placeholder="操作人" style={{ width: 140 }} value={operator} onChange={(e) => setOperator(e.target.value)} />
          <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>新增业务员</Button>
        </Space>}>
        <Table<SalespersonFull> rowKey="code" size="small" loading={loading} dataSource={rows}
          pagination={false}
          columns={[
            { title: '代码', dataIndex: 'code', width: 70, render: (v: string) => <Text strong>{v}</Text> },
            { title: '姓名', dataIndex: 'name', width: 110,
              render: (v: string) => v || <Text type="warning">待补</Text> },
            { title: '首位数字', dataIndex: 'digit', width: 90 },
            { title: '电话', dataIndex: 'phone', width: 130, render: (v: string | null) => v || '—' },
            { title: '提成比例', dataIndex: 'commission_rate', width: 100,
              render: (v: number | null) => (v != null ? `${(v * 100).toFixed(2)}%` : '—') },
            { title: '状态', dataIndex: 'is_active', width: 80,
              render: (v: number) => (v ? <Badge status="success" text="在职" /> : <Badge status="default" text="停用" />) },
            { title: '备注', dataIndex: 'remark', ellipsis: true, render: (v: string | null) => v || '—' },
            { title: '操作', width: 80, render: (_, r) => <Button size="small" onClick={() => openEdit(r)}>编辑</Button> },
          ]} />
      </Card>

      <Modal title="新增业务员" open={createOpen} onOk={onCreate} onCancel={() => setCreateOpen(false)}
        okText="建档" cancelText="取消" confirmLoading={submitting}>
        <Space direction="vertical" style={{ width: '100%' }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            代码 = 客户编码的首字母（1 个字母）；首位数字 = 该业务员的数字编码。
            建议用空闲数字：{freeDigits.join(' ') || '（0-9 均已占用，可与其他业务员共用）'}
          </Text>
          <Input placeholder="代码（1个字母，如 G）" value={createForm.code} maxLength={1}
            onChange={(e) => setCreateForm((f) => ({ ...f, code: e.target.value.toUpperCase() }))} />
          <Input placeholder="姓名 *" value={createForm.name}
            onChange={(e) => setCreateForm((f) => ({ ...f, name: e.target.value }))} />
          <Input placeholder={`首位数字（0-9，空闲: ${freeDigits.join(' ')}）`} value={createForm.digit} maxLength={1}
            onChange={(e) => setCreateForm((f) => ({ ...f, digit: e.target.value }))} />
          <Input placeholder="电话（可空）" value={createForm.phone}
            onChange={(e) => setCreateForm((f) => ({ ...f, phone: e.target.value }))} />
          <Row align="middle" gutter={8}>
            <Col><Text type="secondary">提成比例（预留，可空）：</Text></Col>
            <Col><InputNumber min={0} max={1} step={0.005} value={createForm.commission_rate}
              placeholder="如 0.02"
              onChange={(v) => setCreateForm((f) => ({ ...f, commission_rate: v }))} /></Col>
          </Row>
          <Input placeholder="备注（可空）" value={createForm.remark}
            onChange={(e) => setCreateForm((f) => ({ ...f, remark: e.target.value }))} />
        </Space>
      </Modal>

      <Modal title={`编辑业务员 ${editTarget?.code ?? ''}（代码 ${editTarget?.code} / 首位数字 ${editTarget?.digit} 不可改）`}
        open={editOpen} onOk={onUpdate} onCancel={() => setEditOpen(false)}
        okText="保存" cancelText="取消" confirmLoading={submitting}>
        <Space direction="vertical" style={{ width: '100%' }}>
          <Input placeholder="姓名 *" value={editForm.name}
            onChange={(e) => setEditForm((f) => ({ ...f, name: e.target.value }))} />
          <Input placeholder="电话" value={editForm.phone}
            onChange={(e) => setEditForm((f) => ({ ...f, phone: e.target.value }))} />
          <Row align="middle" gutter={8}>
            <Col><Text type="secondary">提成比例：</Text></Col>
            <Col><InputNumber min={0} max={1} step={0.005} value={editForm.commission_rate}
              onChange={(v) => setEditForm((f) => ({ ...f, commission_rate: v }))} /></Col>
            <Col><Text type="secondary">在职：</Text></Col>
            <Col><Switch checked={!!editForm.is_active}
              onChange={(v) => setEditForm((f) => ({ ...f, is_active: v ? 1 : 0 }))} /></Col>
          </Row>
          <Input placeholder="备注" value={editForm.remark}
            onChange={(e) => setEditForm((f) => ({ ...f, remark: e.target.value }))} />
        </Space>
      </Modal>
    </div>
  )
}
