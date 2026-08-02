// 物料录入页 — 实时派生表单 (React 版, 替代 Streamlit 录入中心·物料 tab)
// 交互: 边填边调 /api/derive (300ms 防抖) → 派生面板局部刷新, 不重载页面
// 提交: 两段式 — 预览 Modal (人确认) → /api/insert (写后校验 ERROR 自动回滚)
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Alert, App, AutoComplete, Button, Card, Col, Input, InputNumber,
  Modal, Row, Select, Space, Statistic, Tag, Typography,
} from 'antd'
import { ReloadOutlined, ToolOutlined } from '@ant-design/icons'
import { api, type Customer, type DeriveResp } from '@/api/client'

const { Text, Title } = Typography

interface FormState {
  customer_code: string | null
  material_id: string
  product_category: string
  brand: string
  material_type: string
  inner_diameter: number | null
  thickness: number | null
  length: number | null
  outer_diameter: number | null
  weight_per_meter: number | null
  weight: number | null
}

const EMPTY: FormState = {
  customer_code: null,
  material_id: '',
  product_category: '',
  brand: '',
  material_type: '',
  inner_diameter: null,
  thickness: null,
  length: null,
  outer_diameter: null,
  weight_per_meter: null,
  weight: null,
}

/** 数字输入: null/0 都视为未填 (0 在几何字段里没有业务意义) */
function num(v: number | null): number | null {
  return v && v > 0 ? v : null
}

export default function ProductEntry() {
  const { message } = App.useApp()
  const [form, setForm] = useState<FormState>(EMPTY)
  const [customers, setCustomers] = useState<Customer[]>([])
  const [categories, setCategories] = useState<string[]>([])
  const [operator, setOperator] = useState('')
  const [derive, setDerive] = useState<DeriveResp | null>(null)
  const [spec, setSpec] = useState('')
  const specDirty = useRef(false)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [previewData, setPreviewData] = useState<Record<string, unknown> | null>(null)
  const [previewErrors, setPreviewErrors] = useState<string[]>([])
  const [submitting, setSubmitting] = useState(false)

  const set = <K extends keyof FormState>(k: K, v: FormState[K]) =>
    setForm((f) => ({ ...f, [k]: v }))

  // ── 初始化下拉 ──
  useEffect(() => {
    api.customers().then(setCustomers).catch((e) => message.error(`客户列表加载失败: ${e.message}`))
    api.categories().then(setCategories).catch(() => {})
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // ── 选客户 → 自动建议物料编码 ──
  const suggestId = useCallback((code: string) => {
    api.suggestMaterialId(code)
      .then((r) => set('material_id', r.material_id))
      .catch(() => {})
  }, [])

  // ── 实时派生 (防抖 300ms) ──
  useEffect(() => {
    const payload = {
      product_category: form.product_category || null,
      inner_diameter: num(form.inner_diameter),
      thickness: num(form.thickness),
      length: num(form.length),
      outer_diameter: num(form.outer_diameter),
      weight_per_meter: num(form.weight_per_meter),
      weight: num(form.weight),
    }
    if (!payload.product_category && !payload.inner_diameter) {
      setDerive(null)
      return
    }
    const t = setTimeout(() => {
      api.derive(payload)
        .then((r) => {
          setDerive(r)
          // 规格描述: 用户没手改过就跟随引擎推算值
          if (!specDirty.current) setSpec((r.row.spec as string) || '')
        })
        .catch(() => {})
    }, 300)
    return () => clearTimeout(t)
  }, [form])

  const computed = new Set(derive?.computed || [])
  const derivedRow = derive?.row || {}

  // ── 提交: 预览 → 确认 → 落库 ──
  const buildData = () => ({
    material_id: form.material_id.trim(),
    customer_code: form.customer_code,
    product_category: form.product_category || null,
    brand: form.brand,
    material_type: form.material_type,
    spec: spec || null,
    inner_diameter: num(form.inner_diameter),
    thickness: num(form.thickness),
    length: num(form.length),
    outer_diameter: num(form.outer_diameter),
    weight_per_meter: num(form.weight_per_meter),
    weight: num(form.weight),
    inner_diameter_inch: (derivedRow.inner_diameter_inch as string) || null,
    spec_meter: (derivedRow.spec_meter as string) || null,
    is_active: 1,
  })

  const onSubmit = async () => {
    if (!form.material_id.trim()) return message.warning('请填物料编码')
    if (!form.customer_code) return message.warning('请选择所属客户')
    if (!form.product_category) return message.warning('请填产品类别')
    if (!num(form.inner_diameter)) return message.warning('请填内径')
    try {
      const pv = await api.preview('products', buildData())
      setPreviewData(pv.derived_row)
      setPreviewErrors(pv.errors)
      setPreviewOpen(true)
    } catch (e) {
      message.error(`预览失败: ${(e as Error).message}`)
    }
  }

  const onConfirm = async () => {
    setSubmitting(true)
    try {
      const r = await api.insert('products', buildData(), operator || 'frontend-react')
      if (r.ok) {
        message.success(`✅ 已入库 (记录 #${r.record_id})${r.warnings.length ? `, ${r.warnings.length} 条警告` : ''}`)
        r.warnings.forEach((w) => message.warning(w, 6))
        setPreviewOpen(false)
        // 保留客户/类别, 清空其余, 方便连续录入同类物料
        setForm((f) => ({ ...EMPTY, customer_code: f.customer_code, product_category: f.product_category }))
        setSpec('')
        specDirty.current = false
        if (form.customer_code) suggestId(form.customer_code)
      } else {
        Modal.error({ title: '写入被拒绝（数据库未改动）', content: r.errors.join('\n') })
      }
    } catch (e) {
      message.error(`提交失败: ${(e as Error).message}`)
    } finally {
      setSubmitting(false)
    }
  }

  // 派生面板指标 (⚙️ = 本次自动算出)
  const metric = (field: string, label: string, digits = 2) => {
    const v = derivedRow[field]
    const isComputed = computed.has(field)
    const shown = v === null || v === undefined || v === ''
      ? '—'
      : typeof v === 'number' ? v.toFixed(digits) : String(v)
    return (
      <Col span={6}>
        <Statistic
          title={<span>{label}{isComputed && <Tag icon={<ToolOutlined />} color="blue" style={{ marginLeft: 6 }}>自动</Tag>}</span>}
          value={shown}
          valueStyle={{ fontSize: 20, color: isComputed ? '#1677ff' : undefined }}
        />
      </Col>
    )
  }

  const warns = (derive?.msgs || []).filter((m) => m.level !== 'info')

  return (
    <div style={{ maxWidth: 960, margin: '0 auto' }}>
      <Title level={4}>🧱 物料录入 <Text type="secondary" style={{ fontSize: 14, fontWeight: 'normal' }}>边填边算：外径 / 厚度 / 米重 / 单重 / 规格实时派生</Text></Title>

      <Card size="small" title="基本信息" style={{ marginBottom: 16 }}>
        <Row gutter={16}>
          <Col span={8}>
            <Text type="secondary">所属客户 *</Text>
            <Select
              style={{ width: '100%' }} placeholder="选择客户"
              value={form.customer_code}
              onChange={(v) => { set('customer_code', v); suggestId(v) }}
              options={customers.map((c) => ({ value: c.code, label: `${c.code} - ${c.name}` }))}
            />
          </Col>
          <Col span={8}>
            <Text type="secondary">物料编码 *（按客户自动建议，可改）</Text>
            <Space.Compact style={{ width: '100%' }}>
              <Input value={form.material_id} onChange={(e) => set('material_id', e.target.value)} placeholder="M-客户-流水" />
              <Button icon={<ReloadOutlined />} onClick={() => form.customer_code && suggestId(form.customer_code)} title="重新建议" />
            </Space.Compact>
          </Col>
          <Col span={8}>
            <Text type="secondary">产品类别 *（真实类别，可输新类别）</Text>
            <AutoComplete
              style={{ width: '100%' }} placeholder="如 线管 / 水带 / 钢丝管"
              value={form.product_category}
              onChange={(v) => set('product_category', v)}
              options={categories.map((c) => ({ value: c }))}
              filterOption={(input, option) => (option?.value as string)?.includes(input)}
            />
          </Col>
        </Row>
        <Row gutter={16} style={{ marginTop: 12 }}>
          <Col span={8}>
            <Text type="secondary">品牌</Text>
            <Input value={form.brand} onChange={(e) => set('brand', e.target.value)} />
          </Col>
          <Col span={8}>
            <Text type="secondary">材质类型</Text>
            <Input value={form.material_type} onChange={(e) => set('material_type', e.target.value)} placeholder="如 PVC" />
          </Col>
          <Col span={8}>
            <Text type="secondary">内径 (mm) *</Text>
            <InputNumber style={{ width: '100%' }} min={0} step={0.5} value={form.inner_diameter} onChange={(v) => set('inner_diameter', v)} />
          </Col>
        </Row>
      </Card>

      <Card size="small" title="几何与重量" style={{ marginBottom: 16 }}
        extra={<Text type="secondary" style={{ fontSize: 12 }}>路径① 填厚度→出外径 ｜ ② 填外径→反推厚度 ｜ ③ 内径+厚度+长度→出米重/单重</Text>}>
        <Row gutter={16}>
          <Col span={4}><Text type="secondary">厚度 (mm)</Text>
            <InputNumber style={{ width: '100%' }} min={0} step={0.05} value={form.thickness} onChange={(v) => set('thickness', v)} /></Col>
          <Col span={4}><Text type="secondary">长度 (M)</Text>
            <InputNumber style={{ width: '100%' }} min={0} step={1} value={form.length} onChange={(v) => set('length', v)} /></Col>
          <Col span={5}><Text type="secondary">外径 (mm)</Text>
            <InputNumber style={{ width: '100%' }} min={0} step={0.1} value={form.outer_diameter} onChange={(v) => set('outer_diameter', v)} /></Col>
          <Col span={5}><Text type="secondary">米重 (g/m)</Text>
            <InputNumber style={{ width: '100%' }} min={0} step={10} value={form.weight_per_meter} onChange={(v) => set('weight_per_meter', v)} /></Col>
          <Col span={6}><Text type="secondary">单重 (KG)</Text>
            <InputNumber style={{ width: '100%' }} min={0} step={0.5} value={form.weight} onChange={(v) => set('weight', v)} /></Col>
        </Row>
      </Card>

      {/* ── 实时派生面板 ── */}
      <Card size="small" title="实时派生" style={{ marginBottom: 16, borderColor: '#1677ff' }}>
        <Space style={{ marginBottom: 12 }} wrap>
          {derive?.category_group && <Tag color="geekblue">大类 {derive.category_group}</Tag>}
          {derive?.density != null
            ? <Tag color="green">密度 {derive.density}</Tag>
            : form.product_category && <Tag color="orange">密度待客户补充（该类别暂无密度规则，重量无法自动算）</Tag>}
          {derivedRow.inner_diameter_inch != null && <Tag color="purple">标称 {String(derivedRow.inner_diameter_inch)}</Tag>}
        </Space>
        <Row gutter={16}>
          {metric('outer_diameter', '外径 (mm)')}
          {metric('thickness', '厚度 (mm)')}
          {metric('weight_per_meter', '米重 (g/m)', 0)}
          {metric('weight', '单重 (KG)')}
        </Row>
        <Text type="secondary" style={{ fontSize: 12 }}>
          「自动」= 本次按公式算出；无标记 = 你手填的值。体积(CBM)需外观尺寸实测后补，不补也能入库（影响装箱校验）。
        </Text>
        {warns.length > 0 && (
          <Alert style={{ marginTop: 12 }} type={warns.some((m) => m.level === 'error') ? 'error' : 'warning'}
            message="手填值与公式有偏差（提交时保留手填值，偏差会写入备注）"
            description={<ul style={{ margin: 0, paddingLeft: 18 }}>{warns.map((m, i) => <li key={i}>{m.msg}</li>)}</ul>}
          />
        )}
      </Card>

      <Card size="small" style={{ marginBottom: 16 }}>
        <Text type="secondary">规格描述（自动推算，可改；手改后不再跟随）</Text>
        <Input
          value={spec}
          onChange={(e) => { specDirty.current = true; setSpec(e.target.value) }}
          placeholder='格式: 英寸 ID内径mm -米数M (短/中/长)，如 1-1/4" ID32 -100M'
        />
      </Card>

      <Space style={{ marginBottom: 24 }}>
        <Input placeholder="操作人（写入审计日志）" style={{ width: 200 }} value={operator} onChange={(e) => setOperator(e.target.value)} />
        <Button type="primary" size="large" onClick={onSubmit}>预览并提交</Button>
      </Space>

      {/* ── 两段式: 预览 Modal ── */}
      <Modal
        title="确认入库（预览 → 确认 → 落库）"
        open={previewOpen}
        onOk={onConfirm}
        onCancel={() => setPreviewOpen(false)}
        okText="确认入库"
        cancelText="返回修改"
        confirmLoading={submitting}
        okButtonProps={{ disabled: previewErrors.length > 0 }}
        width={640}
      >
        {previewErrors.length > 0 && (
          <Alert type="error" style={{ marginBottom: 12 }} message="字段校验未通过"
            description={<ul style={{ margin: 0, paddingLeft: 18 }}>{previewErrors.map((e, i) => <li key={i}>{e}</li>)}</ul>} />
        )}
        {previewData && (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <tbody>
              {Object.entries(previewData)
                .filter(([, v]) => v !== null && v !== '')
                .map(([k, v]) => (
                  <tr key={k}>
                    <td style={{ padding: '4px 8px', color: '#888', width: 180, borderBottom: '1px solid #f0f0f0' }}>{k}</td>
                    <td style={{ padding: '4px 8px', borderBottom: '1px solid #f0f0f0' }}>{String(v)}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        )}
      </Modal>
    </div>
  )
}
