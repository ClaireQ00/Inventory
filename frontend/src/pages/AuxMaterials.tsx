// 辅料档案页 — 标签纸等生产辅料主档维护 + 附件上传 (M1)
// 计划: docs/AUX_MATERIALS_PLAN.md。用料=半成品原材料后续独立模块, 不在此页
import { useCallback, useEffect, useState } from 'react'
import {
  App, Button, Card, Col, Input, InputNumber, Modal, Row, Select, Space,
  Table, Tag, Typography, Upload,
} from 'antd'
import { DownloadOutlined, UploadOutlined } from '@ant-design/icons'
import { api } from '@/api/client'

const { Text, Title } = Typography

const TYPE_LABEL: Record<string, string> = {
  label_paper: '标签纸', packaging: '包装', spray_code: '喷码', meter_mark: '米标',
  material_used: '用料', wire_pattern: '打线', coil_type: '盘型', other: '其他',
}

export default function AuxMaterials() {
  const { message } = App.useApp()
  const [rows, setRows] = useState<Record<string, unknown>[]>([])
  const [operator, setOperator] = useState('')
  const [form, setForm] = useState({
    aux_code: '', aux_type: 'label_paper', name: '', shape: 'R', width_mm: null as number | null,
    height_mm: null as number | null, material_desc: '', unit: '张',
    min_stock: null as number | null, remark: '',
  })
  const [typeFilter, setTypeFilter] = useState<string>('')
  const [attachments, setAttachments] = useState<Record<string, Record<string, unknown>[]>>({})

  const reload = useCallback(() => {
    api.auxMaterials().then(setRows).catch((e) => message.error(`加载失败: ${e.message}`))
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(reload, [reload])

  const loadAttachments = (auxCode: string) => {
    api.auxAttachments(auxCode)
      .then((list) => setAttachments((m) => ({ ...m, [auxCode]: list as Record<string, unknown>[] })))
      .catch(() => {})
  }

  const onCreate = async () => {
    if (!form.aux_code.trim()) return message.warning('请填辅料编码')
    const r = await api.auxCreate({
      aux_code: form.aux_code.trim(), aux_type: form.aux_type,
      name: form.name, shape: form.shape,
      width_mm: form.width_mm || null, height_mm: form.height_mm || null,
      material_desc: form.material_desc, unit: form.unit,
      min_stock: form.min_stock || null, remark: form.remark,
    }, operator || 'frontend-react')
    if (r.ok) {
      message.success(`✅ 辅料档案已建立 (#${r.record_id})`)
      setForm({ ...form, aux_code: '', name: '', width_mm: null, height_mm: null, material_desc: '', remark: '' })
      reload()
    } else {
      Modal.error({ title: '创建被拒绝', content: r.errors.join('\n') })
    }
  }

  const onUpload = async (auxCode: string, file: File) => {
    try {
      const r = await api.auxUpload(auxCode, file, operator || 'frontend-react')
      message.success(r.duplicate ? '附件已存在（内容相同，未重复保存）' : '✅ 附件已上传')
      loadAttachments(auxCode)
    } catch (e) {
      message.error((e as Error).message)
    }
  }

  return (
    <div style={{ maxWidth: 1080, margin: '0 auto' }}>
      <Title level={4}>🗂️ 辅料档案 <Text type="secondary" style={{ fontSize: 14, fontWeight: 'normal' }}>标签纸等生产辅料主档 + 图纸/样张附件</Text></Title>

      <Card size="small" title="新增辅料档案" style={{ marginBottom: 16 }}>
        <Row gutter={16}>
          <Col span={4}><Text type="secondary">类型</Text>
            <Select style={{ width: '100%' }} value={form.aux_type} onChange={(v) => setForm({ ...form, aux_type: v })}
              options={Object.entries(TYPE_LABEL).map(([value, label]) => ({ value, label }))} /></Col>
          <Col span={4}><Text type="secondary">辅料编码 *</Text>
            <Input value={form.aux_code} onChange={(e) => setForm({ ...form, aux_code: e.target.value })} placeholder="如 LP-R02507" /></Col>
          <Col span={6}><Text type="secondary">名称</Text>
            <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="如 长方形标签 25×40" /></Col>
          <Col span={3}><Text type="secondary">形状</Text>
            <Select style={{ width: '100%' }} value={form.shape} onChange={(v) => setForm({ ...form, shape: v })}
              options={[{ value: 'R', label: 'R 长方形' }, { value: 'C', label: 'C 圆环形' }]} /></Col>
          <Col span={3}><Text type="secondary">宽 (mm)</Text>
            <InputNumber style={{ width: '100%' }} min={0} value={form.width_mm} onChange={(v) => setForm({ ...form, width_mm: v })} /></Col>
          <Col span={4}><Text type="secondary">高 (mm)</Text>
            <InputNumber style={{ width: '100%' }} min={0} value={form.height_mm} onChange={(v) => setForm({ ...form, height_mm: v })} /></Col>
        </Row>
        <Row gutter={16} style={{ marginTop: 12 }}>
          <Col span={5}><Text type="secondary">材质描述</Text>
            <Input value={form.material_desc} onChange={(e) => setForm({ ...form, material_desc: e.target.value })} placeholder="如 铜版纸/不干胶" /></Col>
          <Col span={3}><Text type="secondary">单位</Text>
            <Input value={form.unit} onChange={(e) => setForm({ ...form, unit: e.target.value })} /></Col>
          <Col span={4}><Text type="secondary">安全库存(张)</Text>
            <InputNumber style={{ width: '100%' }} min={0} value={form.min_stock} onChange={(v) => setForm({ ...form, min_stock: v })} /></Col>
          <Col span={9}><Text type="secondary">备注</Text>
            <Input value={form.remark} onChange={(e) => setForm({ ...form, remark: e.target.value })} /></Col>
          <Col span={4}><Text type="secondary">操作人</Text>
            <Input value={operator} onChange={(e) => setOperator(e.target.value)} /></Col>
          <Col span={4} style={{ display: 'flex', alignItems: 'flex-end' }}>
            <Button type="primary" onClick={onCreate}>建立档案</Button>
          </Col>
        </Row>
      </Card>

      <Space style={{ marginBottom: 8 }}>
        <Text type="secondary">类型筛选</Text>
        <Select
          style={{ width: 160 }} value={typeFilter} onChange={setTypeFilter}
          options={[{ value: '', label: '全部' }, ...Object.entries(TYPE_LABEL).map(([value, label]) => ({ value, label }))]}
        />
      </Space>
      <Table
        size="small" rowKey="aux_code"
        dataSource={typeFilter ? rows.filter((r) => r.aux_type === typeFilter) : rows}
        pagination={false}
        columns={[
          { title: '编码', dataIndex: 'aux_code', width: 120 },
          { title: '类型', dataIndex: 'aux_type', width: 80, render: (v: string) => <Tag>{TYPE_LABEL[v] || v}</Tag> },
          { title: '名称', dataIndex: 'name' },
          { title: '形状', dataIndex: 'shape', width: 60 },
          { title: '尺寸 (mm)', width: 110, render: (_, r) => r.width_mm ? `${r.width_mm}×${r.height_mm ?? '?'}` : '—' },
          { title: '单位', dataIndex: 'unit', width: 60 },
          { title: '安全库存', dataIndex: 'min_stock', width: 90, render: (v) => v ?? '—' },
          { title: '当前库存(张)', dataIndex: 'stock_total', width: 110,
            render: (v: number, r) => (
              <Text strong type={r.min_stock != null && Number(v) < Number(r.min_stock) ? 'danger' : undefined}>{v}</Text>
            ) },
          { title: '备注', dataIndex: 'remark', ellipsis: true },
        ]}
        expandable={{
          expandedRowRender: (r) => {
            const list = attachments[r.aux_code as string]
            return (
              <div>
                <Space style={{ marginBottom: 8 }}>
                  <Upload
                    showUploadList={false} accept=".pdf,.doc,.docx,.jpg,.jpeg,.png"
                    customRequest={({ file }) => onUpload(r.aux_code as string, file as File)}
                  >
                    <Button size="small" icon={<UploadOutlined />}>上传附件 (pdf/word/图片 ≤10MB)</Button>
                  </Upload>
                  {!list && <Button size="small" onClick={() => loadAttachments(r.aux_code as string)}>查看附件</Button>}
                </Space>
                {list && (
                  list.length === 0 ? <Text type="secondary">暂无附件</Text> : (
                    <ul style={{ margin: 0, paddingLeft: 18 }}>
                      {list.map((a) => (
                        <li key={a.id as number}>
                          <a href={api.auxDownloadUrl(a.id as number)} target="_blank" rel="noreferrer">
                            <DownloadOutlined /> {a.file_name as string}
                          </a>
                          <Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>
                            {a.file_type as string} · {Math.round(Number(a.file_size) / 1024)}KB · {a.uploaded_by as string}
                          </Text>
                        </li>
                      ))}
                    </ul>
                  )
                )}
              </div>
            )
          },
          onExpand: (expanded, r) => { if (expanded) loadAttachments(r.aux_code as string) },
        }}
      />
    </div>
  )
}
