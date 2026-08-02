// 收款录入页 — 汇率按到账日期自动带出, 金额自动折 CNY;
// 写后校验: 累计收款 > 合同总额 → 自动回滚拦截 (第13步校验同口径)
import { useCallback, useEffect, useState } from 'react'
import {
  Alert, App, Button, Card, Col, DatePicker, Input, InputNumber, Modal, Row,
  Select, Space, Table, Typography,
} from 'antd'
import dayjs from 'dayjs'
import { api, type Customer, type PreviewResp } from '@/api/client'

const { Text, Title } = Typography

const PAY_METHODS = ['T/T', 'L/C', 'D/P', 'D/A', 'other']

export default function ReceiptEntry() {
  const { message } = App.useApp()
  const [customers, setCustomers] = useState<Customer[]>([])
  const [contracts, setContracts] = useState<Record<string, unknown>[]>([])
  const [summary, setSummary] = useState<Record<string, unknown> | null>(null)
  const [form, setForm] = useState({
    customer_code: null as string | null,
    contract_no: '',
    receipt_no: `RC${dayjs().format('YYYYMMDD')}`,
    amount: null as number | null,
    currency: 'USD',
    paid_date: dayjs(),
    pay_method: 'T/T',
    bank_ref: '',
    remark: '',
  })
  const [operator, setOperator] = useState('')
  const [preview, setPreview] = useState<PreviewResp | null>(null)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  const set = (patch: Partial<typeof form>) => setForm((f) => ({ ...f, ...patch }))

  useEffect(() => {
    api.customers().then(setCustomers).catch((e) => message.error(`客户列表加载失败: ${e.message}`))
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const onCustomerChange = (code: string) => {
    set({ customer_code: code, contract_no: '' })
    setSummary(null)
    api.contracts(code).then(setContracts).catch(() => setContracts([]))
  }

  const onContractChange = useCallback((no: string) => {
    set({ contract_no: no })
    if (no) {
      api.contractReceiptSummary(no).then((s) => setSummary(s as unknown as Record<string, unknown>)).catch(() => setSummary(null))
    } else {
      setSummary(null)
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const buildData = () => ({
    receipt_no: form.receipt_no.trim(),
    customer_code: form.customer_code,
    contract_no: form.contract_no || null,
    amount: form.amount,
    currency: form.currency,
    paid_date: form.paid_date.format('YYYY-MM-DD'),
    pay_method: form.pay_method,
    bank_ref: form.bank_ref.trim(),
    status: 'confirmed',
    remark: form.remark.trim(),
  })

  const onSubmit = async () => {
    if (!form.receipt_no.trim()) return message.warning('请填收款单号')
    if (!form.customer_code) return message.warning('请选择客户')
    if (!form.amount || form.amount <= 0) return message.warning('请填收款金额')
    try {
      const pv = await api.preview('receipts', buildData())
      setPreview(pv)
      setPreviewOpen(true)
    } catch (e) {
      message.error(`预览失败: ${(e as Error).message}`)
    }
  }

  const onConfirm = async () => {
    setSubmitting(true)
    try {
      const r = await api.insert('receipts', buildData(), operator || 'frontend-react')
      if (r.ok) {
        message.success(`✅ 收款已入库 (#${r.record_id})`)
        r.warnings.forEach((w) => message.warning(w, 6))
        setPreviewOpen(false)
        setForm({ ...form, receipt_no: `RC${dayjs().format('YYYYMMDD')}`, amount: null, bank_ref: '', remark: '' })
        if (form.contract_no) onContractChange(form.contract_no) // 刷新收款进度
      } else {
        Modal.error({ title: '写入被拒绝（数据库未改动，已回滚）', content: r.errors.join('\n') })
      }
    } catch (e) {
      message.error(`提交失败: ${(e as Error).message}`)
    } finally {
      setSubmitting(false)
    }
  }

  const contractOptions = [
    { value: '', label: '（不关联合同 · 预收款）' },
    ...contracts.map((c) => ({
      value: c.contract_no as string,
      label: `${c.contract_no}（${c.total_amount} ${c.currency} · ${c.status}）`,
    })),
  ]

  return (
    <div style={{ maxWidth: 960, margin: '0 auto' }}>
      <Title level={4}>💰 收款录入 <Text type="secondary" style={{ fontSize: 14, fontWeight: 'normal' }}>汇率按到账日期自动带出 ｜ 超额收款自动回滚拦截</Text></Title>

      <Card size="small" style={{ marginBottom: 16 }}>
        <Row gutter={16}>
          <Col span={8}><Text type="secondary">客户 *</Text>
            <Select style={{ width: '100%' }} placeholder="选择客户" value={form.customer_code} onChange={onCustomerChange}
              options={customers.map((c) => ({ value: c.code, label: `${c.code} - ${c.name}` }))} /></Col>
          <Col span={10}><Text type="secondary">关联合同（预收款留空）</Text>
            <Select style={{ width: '100%' }} value={form.contract_no} onChange={onContractChange} options={contractOptions} /></Col>
          <Col span={6}><Text type="secondary">收款单号 *</Text>
            <Input value={form.receipt_no} onChange={(e) => set({ receipt_no: e.target.value })} /></Col>
        </Row>

        {summary != null && (
          <Alert style={{ marginTop: 12 }}
            type={summary.fully_received ? 'success' : 'info'}
            message={`合同 ${summary.contract_no}（${summary.customer_name}）：总额 ${Number(summary.total_amount).toLocaleString()} ${summary.currency} ｜ 已收 ${Number(summary.received).toLocaleString()} ｜ 未收 ${Number(summary.remaining).toLocaleString()}${summary.fully_received ? '（已收满，再收将被超额拦截）' : ''}`}
          />
        )}

        <Row gutter={16} style={{ marginTop: 12 }}>
          <Col span={6}><Text type="secondary">收款金额（原币）*</Text>
            <InputNumber style={{ width: '100%' }} min={0} step={100} value={form.amount} onChange={(v) => set({ amount: v })} /></Col>
          <Col span={4}><Text type="secondary">币种 *</Text>
            <Select style={{ width: '100%' }} value={form.currency} onChange={(v) => set({ currency: v })}
              options={['USD', 'EUR', 'IDR', 'CNY'].map((c) => ({ value: c, label: c }))} /></Col>
          <Col span={5}><Text type="secondary">实际到账日期 *</Text>
            <DatePicker style={{ width: '100%' }} value={form.paid_date} onChange={(v) => v && set({ paid_date: v })} /></Col>
          <Col span={4}><Text type="secondary">付款方式</Text>
            <Select style={{ width: '100%' }} value={form.pay_method} onChange={(v) => set({ pay_method: v })}
              options={PAY_METHODS.map((m) => ({ value: m, label: m }))} /></Col>
          <Col span={5}><Text type="secondary">银行水单号</Text>
            <Input value={form.bank_ref} onChange={(e) => set({ bank_ref: e.target.value })} /></Col>
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
              ['收款单号', form.receipt_no],
              ['客户', form.customer_code],
              ['合同', form.contract_no || '（预收款）'],
              ['金额', `${Number(form.amount).toLocaleString()} ${form.currency}`],
              ['汇率', preview.derived_row.exchange_rate ? String(preview.derived_row.exchange_rate) : '（未带出）'],
              ['折 CNY', preview.derived_row.amount_cny ? `¥ ${Number(preview.derived_row.amount_cny).toLocaleString()}` : '—'],
              ['到账日期', form.paid_date.format('YYYY-MM-DD')],
              ['付款方式', form.pay_method],
            ].map(([k, v], i) => ({ k, v, i }))}
            columns={[
              { dataIndex: 'k', width: 110, render: (v) => <Text type="secondary">{v}</Text> },
              { dataIndex: 'v', render: (v) => <b>{v}</b> },
            ]}
            rowKey="i"
          />
        )}
      </Modal>
    </div>
  )
}
