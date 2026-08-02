// 物料录入页 — 实时派生表单 (React 版, 替代 Streamlit 录入中心·物料 tab)
// 字段与 MySQL products 表 / products.csv 全列对齐 (2026-08-01 老板要求)
// 交互: 边填边调 /api/derive (300ms 防抖) → 派生面板局部刷新, 不重载页面
// 提交: 两段式 — 预览 Modal (人确认) → /api/insert (写后校验 ERROR 自动回滚)
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Alert, App, AutoComplete, Button, Card, Col, Collapse, Input, InputNumber,
  Modal, Row, Select, Space, Statistic, Tag, Typography,
} from 'antd'
import { ReloadOutlined, ToolOutlined } from '@ant-design/icons'
import { api, type Customer, type DeriveResp } from '@/api/client'

const { Text, Title } = Typography

interface FormState {
  // A. 标识与基本信息
  customer_code: string | null
  material_id: string
  product_category: string
  brand: string
  material_type: string
  // B. 尺寸参数
  inner_diameter: number | null
  thickness: number | null
  length: number | null
  spec_meter: number | null       // 标称米数: 不填则按长度四舍五入自动算
  outer_diameter: number | null
  virtual_weight: number | null   // 虚重(kg)
  virtual_length: number | null   // 虚米(m)
  wire_spacing: string            // 线距/簧距
  // C. 重量参数
  weight_per_meter: number | null
  weight: number | null
  // D. 外观与包装
  appearance_inner: number | null
  appearance_outer: number | null
  appearance_height: number | null
  package: string
  label_paper: string
  material_used: string
  wire_pattern: string
  // E/F. 盘型与工艺标识
  coil_type: string
  pressure: number | null
  spray_code: string              // 喷码
  meter_mark: string              // 米标
  meter_mark_count: number | null // 印花循环次数
  remark: string
}

const EMPTY: FormState = {
  customer_code: null, material_id: '', product_category: '', brand: '', material_type: '',
  inner_diameter: null, thickness: null, length: null, spec_meter: null, outer_diameter: null,
  virtual_weight: null, virtual_length: null, wire_spacing: '',
  weight_per_meter: null, weight: null,
  appearance_inner: null, appearance_outer: null, appearance_height: null,
  package: '', label_paper: '', material_used: '', wire_pattern: '',
  coil_type: '', pressure: null, spray_code: '', meter_mark: '', meter_mark_count: null,
  remark: '',
}

/** 数字输入: null/0 都视为未填 (0 在几何字段里没有业务意义) */
function num(v: number | null): number | null {
  return v && v > 0 ? v : null
}

function str(v: string): string | null {
  return v.trim() ? v.trim() : null
}

export default function ProductEntry() {
  const { message } = App.useApp()
  const [form, setForm] = useState<FormState>(EMPTY)
  const [customers, setCustomers] = useState<Customer[]>([])
  const [categories, setCategories] = useState<string[]>([])
  const [brands, setBrands] = useState<string[]>([])
  const [operator, setOperator] = useState('')
  const [derive, setDerive] = useState<DeriveResp | null>(null)
  const [spec, setSpec] = useState('')
  const specDirty = useRef(false)
  // 标称英寸: 引擎建议值 = 向上取标准管型, 用户可手改覆盖 (手改后不再跟随)
  const [inch, setInch] = useState('')
  const inchDirty = useRef(false)
  const [inchOptions, setInchOptions] = useState<string[]>([])
  // 按客户历史值下拉 (喷码/用料/打线/米标, 与品牌同款: 下拉+可手填)
  const [fieldOpts, setFieldOpts] = useState<Record<string, string[]>>({})
  // 物料类型: 档案库驱动 (material_type_profiles, 成本指导价预留), 客户历史值作补充
  const [mtArchive, setMtArchive] = useState<string[]>([])
  // 印花循环次数: 默认跟随标称米数, 手改后不再跟随
  const mmCountDirty = useRef(false)
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
    api.nominalInches().then(setInchOptions).catch(() => {})
    api.materialTypeProfiles()
      .then((list) => setMtArchive(list.map((t) => t.type_code)))
      .catch(() => {})
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // ── 选客户 → 自动建议物料编码 + 拉该客户的品牌清单 ──
  const suggestId = useCallback((code: string) => {
    api.suggestMaterialId(code)
      .then((r) => set('material_id', r.material_id))
      .catch(() => {})
  }, [])

  // 需要按客户历史值下拉的字段 (与后端 DROPDOWN_FIELDS 白名单一致)
  const HISTORY_FIELDS = ['spray_code', 'material_type', 'material_used', 'wire_pattern', 'meter_mark']

  const onCustomerChange = (code: string) => {
    set('customer_code', code)
    suggestId(code)
    api.brands(code).then(setBrands).catch(() => setBrands([]))
    HISTORY_FIELDS.forEach((f) => {
      api.fieldValues(code, f)
        .then((vals) => setFieldOpts((m) => ({ ...m, [f]: vals })))
        .catch(() => {})
    })
  }

  // ── 实时派生 (防抖 300ms) ──
  useEffect(() => {
    const payload: Record<string, unknown> = {
      product_category: form.product_category || null,
      inner_diameter: num(form.inner_diameter),
      thickness: num(form.thickness),
      length: num(form.length),
      spec_meter: num(form.spec_meter),
      outer_diameter: num(form.outer_diameter),
      weight_per_meter: num(form.weight_per_meter),
      weight: num(form.weight),
      appearance_outer: num(form.appearance_outer),
      appearance_height: num(form.appearance_height),
    }
    // 用户手改了标称英寸 → 带上用户值 (引擎不再自动换算, spec 按用户 inch 拼)
    if (inchDirty.current) payload.inner_diameter_inch = inch || null
    if (!payload.product_category && !payload.inner_diameter) {
      setDerive(null)
      return
    }
    const t = setTimeout(() => {
      api.derive(payload)
        .then((r) => {
          setDerive(r)
          // 规格描述/标称英寸: 用户没手改过就跟随引擎推算值
          if (!specDirty.current) setSpec((r.row.spec as string) || '')
          if (!inchDirty.current) setInch((r.row.inner_diameter_inch as string) || '')
          // 印花循环次数: 默认 = 标称米数 (手填优先, 否则引擎推算), 手改后不再跟随
          const effMeter = num(form.spec_meter) ?? (r.row.spec_meter ? Number(r.row.spec_meter) : null)
          if (!mmCountDirty.current && effMeter != null && form.meter_mark_count !== effMeter) {
            set('meter_mark_count', effMeter)
          }
        })
        .catch(() => {})
    }, 300)
    return () => clearTimeout(t)
  }, [form, inch])

  const computed = new Set(derive?.computed || [])
  const derivedRow = derive?.row || {}

  // ── 提交: 预览 → 确认 → 落库 ──
  const buildData = () => ({
    material_id: form.material_id.trim(),
    customer_code: form.customer_code,
    product_category: str(form.product_category),
    brand: str(form.brand),
    material_type: str(form.material_type),
    spec: spec || null,
    inner_diameter: num(form.inner_diameter),
    // 标称英寸: 用户手改优先, 否则引擎建议值 (向上取标准管型)
    inner_diameter_inch: inch || (derivedRow.inner_diameter_inch as string) || null,
    thickness: num(form.thickness),
    length: num(form.length),
    spec_meter: num(form.spec_meter) ?? (derivedRow.spec_meter ? Number(derivedRow.spec_meter) : null),
    outer_diameter: num(form.outer_diameter),
    id_x_od: (derivedRow.id_x_od as string) || null,
    virtual_weight: num(form.virtual_weight),
    virtual_length: num(form.virtual_length),
    wire_spacing: str(form.wire_spacing),
    weight_per_meter: num(form.weight_per_meter),
    weight: num(form.weight),
    appearance_inner: num(form.appearance_inner),
    appearance_outer: num(form.appearance_outer),
    appearance_height: num(form.appearance_height),
    package: str(form.package),
    label_paper: str(form.label_paper),
    material_used: str(form.material_used),
    wire_pattern: str(form.wire_pattern),
    coil_type: str(form.coil_type),
    pressure: num(form.pressure),
    spray_code: str(form.spray_code),
    meter_mark: str(form.meter_mark),
    meter_mark_count: num(form.meter_mark_count),
    remark: str(form.remark),
    is_active: 1,
  })

  const onSubmit = async () => {
    if (!form.material_id.trim()) return message.warning('请填物料编码')
    if (!form.customer_code) return message.warning('请选择所属客户')
    if (!str(form.product_category)) return message.warning('请填产品类别')
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
        // 保留客户/类别/品牌, 清空其余, 方便连续录入同类物料
        setForm((f) => ({ ...EMPTY, customer_code: f.customer_code, product_category: f.product_category, brand: f.brand }))
        setSpec('')
        specDirty.current = false
        setInch('')
        inchDirty.current = false
        mmCountDirty.current = false
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
      <Col span={4}>
        <Statistic
          title={<span>{label}{isComputed && <Tag icon={<ToolOutlined />} color="blue" style={{ marginLeft: 4 }}>自动</Tag>}</span>}
          value={shown}
          valueStyle={{ fontSize: 18, color: isComputed ? '#1677ff' : undefined }}
        />
      </Col>
    )
  }

  const warns = (derive?.msgs || []).filter((m) => m.level !== 'info')

  const numField = (
    key: keyof FormState, label: string, step = 0.1, span = 4,
  ) => (
    <Col span={span}>
      <Text type="secondary">{label}</Text>
      <InputNumber
        style={{ width: '100%' }} min={0} step={step}
        value={form[key] as number | null}
        onChange={(v) => set(key, v as never)}
      />
    </Col>
  )

  const strField = (
    key: keyof FormState, label: string, placeholder = '', span = 4, opts?: string[],
  ) => (
    <Col span={span}>
      <Text type="secondary">{label}</Text>
      {opts ? (
        <AutoComplete
          style={{ width: '100%' }}
          value={form[key] as string} placeholder={placeholder}
          onChange={(v) => set(key, v as never)}
          options={opts.map((o) => ({ value: o }))}
          filterOption={(input, option) => (option?.value as string)?.includes(input)}
        />
      ) : (
        <Input
          value={form[key] as string} placeholder={placeholder}
          onChange={(e) => set(key, e.target.value as never)}
        />
      )}
    </Col>
  )

  return (
    <div style={{ maxWidth: 1080, margin: '0 auto' }}>
      <Title level={4}>🧱 物料录入 <Text type="secondary" style={{ fontSize: 14, fontWeight: 'normal' }}>字段与 products 表全列对齐 ｜ 边填边算实时派生</Text></Title>

      {/* ── A. 基本信息 ── */}
      <Card size="small" title="基本信息" style={{ marginBottom: 16 }}>
        <Row gutter={16}>
          <Col span={8}>
            <Text type="secondary">所属客户 *</Text>
            <Select
              style={{ width: '100%' }} placeholder="选择客户"
              value={form.customer_code}
              onChange={onCustomerChange}
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
            <Text type="secondary">品牌（该客户用过的品牌，可手填新品牌）</Text>
            <AutoComplete
              style={{ width: '100%' }} placeholder={form.customer_code ? '选择或输入品牌' : '先选客户'}
              value={form.brand}
              onChange={(v) => set('brand', v)}
              options={brands.map((b) => ({ value: b }))}
              filterOption={(input, option) => (option?.value as string)?.includes(input)}
            />
          </Col>
          <Col span={8}>
            <Text type="secondary">物料类型（档案库下拉，可手填；成本指导价预留）</Text>
            <AutoComplete
              style={{ width: '100%' }}
              value={form.material_type} placeholder="如 出口线管-小内径"
              onChange={(v) => set('material_type', v)}
              options={[...new Set([...mtArchive, ...(fieldOpts.material_type || [])])].map((o) => ({ value: o }))}
              filterOption={(input, option) => (option?.value as string)?.includes(input)}
            />
          </Col>
          <Col span={4}>
            <Text type="secondary">内径 (mm) *</Text>
            <InputNumber style={{ width: '100%' }} min={0} step={0.5} value={form.inner_diameter} onChange={(v) => set('inner_diameter', v)} />
          </Col>
          <Col span={4}>
            <Text type="secondary">标称英寸（自动=向上取，可改）</Text>
            <AutoComplete
              style={{ width: '100%' }} placeholder='如 1-1/4"'
              value={inch}
              onChange={(v) => { inchDirty.current = true; setInch(v) }}
              options={inchOptions.map((o) => ({ value: o }))}
              filterOption={(input, option) => (option?.value as string)?.includes(input)}
            />
          </Col>
        </Row>
      </Card>

      {/* ── B/C. 几何与重量 ── */}
      <Card size="small" title="几何与重量" style={{ marginBottom: 16 }}
        extra={<Text type="secondary" style={{ fontSize: 12 }}>路径① 填厚度→出外径 ｜ ② 填外径→反推厚度 ｜ ③ 内径+厚度+长度→出米重/单重</Text>}>
        <Row gutter={16}>
          {numField('thickness', '厚度 (mm)', 0.05)}
          {numField('length', '长度 (M)', 1)}
          {numField('spec_meter', '标称米数 (M, 空=按长度算)', 1)}
          {numField('outer_diameter', '外径 (mm)', 0.1)}
          {numField('weight_per_meter', '米重 (g/m)', 10)}
          {numField('weight', '单重 (KG)', 0.5)}
        </Row>
        <Row gutter={16} style={{ marginTop: 12 }}>
          {numField('virtual_weight', '虚重 (kg)', 0.5)}
          {numField('virtual_length', '虚米 (m)', 1)}
          {strField('wire_spacing', '线距/簧距', '如 32根 或 5mm')}
        </Row>
      </Card>

      {/* ── 实时派生面板 ── */}
      <Card size="small" title="实时派生" style={{ marginBottom: 16, borderColor: '#1677ff' }}>
        <Space style={{ marginBottom: 12 }} wrap>
          {derive?.category_group && <Tag color="geekblue">大类 {derive.category_group}</Tag>}
          {derive?.density != null
            ? <Tag color="green">密度 {derive.density}</Tag>
            : form.product_category && <Tag color="orange">密度待客户补充（该类别暂无密度规则，重量无法自动算）</Tag>}
          {derivedRow.inner_diameter_inch != null && (
            <Tag color="purple">标称 {String(derivedRow.inner_diameter_inch)}（向上取标准管型）</Tag>
          )}
        </Space>
        <Row gutter={16}>
          {metric('outer_diameter', '外径 (mm)')}
          {metric('thickness', '厚度 (mm)')}
          {metric('weight_per_meter', '米重 (g/m)', 0)}
          {metric('weight', '单重 (KG)')}
          {metric('spec_meter', '标称米数 (M)', 0)}
          {metric('volume', '体积 (m³)', 4)}
        </Row>
        <Text type="secondary" style={{ fontSize: 12 }}>
          「自动」= 本次按公式算出；无标记 = 你手填的值。体积需外观外径+高度，不补也能入库（影响装箱校验）。
        </Text>
        {warns.length > 0 && (
          <Alert style={{ marginTop: 12 }} type={warns.some((m) => m.level === 'error') ? 'error' : 'warning'}
            message="手填值与公式有偏差（提交时保留手填值，偏差会写入备注）"
            description={<ul style={{ margin: 0, paddingLeft: 18 }}>{warns.map((m, i) => <li key={i}>{m.msg}</li>)}</ul>}
          />
        )}
      </Card>

      {/* ── D/E/F. 外观包装 + 工艺标识 (折叠) ── */}
      <Collapse
        style={{ marginBottom: 16 }}
        defaultActiveKey={['craft']}
        items={[
          {
            key: 'appearance',
            label: '外观与包装（量盘后再补也行）',
            children: (
              <>
                <Row gutter={16}>
                  {numField('appearance_inner', '外观内径 (mm)', 1)}
                  {numField('appearance_outer', '外观外径 (mm)', 1)}
                  {numField('appearance_height', '外观高度 (mm)', 1)}
                  {strField('package', '包装', '如 PE膜')}
                  {strField('label_paper', '标签纸', 'R=长方 C=圆环')}
                  {strField('coil_type', '盘型', '如 内径30高7层')}
                </Row>
              </>
            ),
          },
          {
            key: 'craft',
            label: '工艺与标识（喷码 / 米标 / 用料 / 打线）',
            children: (
              <>
                <Row gutter={16}>
                  {strField('spray_code', '喷码（该客户用过的，可手填）', '喷在产品上的标识文字', 12, fieldOpts.spray_code)}
                  {strField('meter_mark', '米标（该客户用过的，可手填）', '如 每1.02米一个循环米', 8, fieldOpts.meter_mark)}
                  <Col span={4}>
                    <Text type="secondary">印花循环次数（默认=标称米数，可改）</Text>
                    <InputNumber
                      style={{ width: '100%' }} min={0} step={1}
                      value={form.meter_mark_count}
                      onChange={(v) => { mmCountDirty.current = true; set('meter_mark_count', v) }}
                    />
                  </Col>
                </Row>
                <Row gutter={16} style={{ marginTop: 12 }}>
                  {strField('material_used', '用料（该客户用过的，可手填）', '如 A25橙', 8, fieldOpts.material_used)}
                  {strField('wire_pattern', '打线（该客户用过的，可手填）', '如 红蓝双线', 8, fieldOpts.wire_pattern)}
                  {numField('pressure', '压力 (Bar)', 1, 4)}
                </Row>
              </>
            ),
          },
        ]}
      />

      {/* ── 规格 + 备注 ── */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Text type="secondary">规格描述（自动推算，可改；手改后不再跟随）</Text>
        <Input
          value={spec}
          onChange={(e) => { specDirty.current = true; setSpec(e.target.value) }}
          placeholder='格式: 英寸 ID内径mm -米数M (短/中/长)，如 1-1/4" ID32 -100M'
        />
        <div style={{ marginTop: 12 }}>
          <Text type="secondary">备注</Text>
          <Input.TextArea rows={2} value={form.remark} onChange={(e) => set('remark', e.target.value)} />
        </div>
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
