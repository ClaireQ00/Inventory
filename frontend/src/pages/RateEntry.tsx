// 汇率录入页 — 汇率月固定 (R7): 每月 1 号录一次
// 两段式提交: 预览(派生) → 确认 → 落库 (查重: 币种+生效日期 唯一)
import { useCallback, useEffect, useState } from 'react'
import {
  App, Button, Card, Col, DatePicker, Input, InputNumber, Modal, Row, Select, Space, Table, Typography,
} from 'antd'
import dayjs from 'dayjs'
import { api } from '@/api/client'

const { Text, Title } = Typography

export default function RateEntry() {
  const { message } = App.useApp()
  const [currency, setCurrency] = useState('USD')
  const [rate, setRate] = useState<number | null>(null)
  const [effDate, setEffDate] = useState(dayjs().date(1))
  const [remark, setRemark] = useState('')
  const [operator, setOperator] = useState('')
  const [recent, setRecent] = useState<Record<string, unknown>[]>([])
  const [previewOpen, setPreviewOpen] = useState(false)
  const [previewErrors, setPreviewErrors] = useState<string[]>([])
  const [submitting, setSubmitting] = useState(false)

  const reload = useCallback(() => {
    api.exchangeRates().then(setRecent).catch(() => {})
  }, [])
  useEffect(reload, [reload])

  const buildData = () => ({
    currency, rate_to_cny: rate,
    effective_date: effDate.format('YYYY-MM-DD'),
    source: 'manual', remark: remark.trim(),
  })

  const onSubmit = async () => {
    if (!rate || rate <= 0) return message.warning('请填汇率')
    try {
      const pv = await api.preview('exchange_rates', buildData())
      setPreviewErrors(pv.errors)
      setPreviewOpen(true)
    } catch (e) {
      message.error(`预览失败: ${(e as Error).message}`)
    }
  }

  const onConfirm = async () => {
    setSubmitting(true)
    try {
      const r = await api.insert('exchange_rates', buildData(), operator || 'frontend-react')
      if (r.ok) {
        message.success(`✅ 汇率已入库 (#${r.record_id}): ${currency} = ${rate} CNY，自 ${effDate.format('YYYY-MM-DD')} 起`)
        setPreviewOpen(false)
        setRate(null)
        setRemark('')
        reload()
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
    <div style={{ maxWidth: 860, margin: '0 auto' }}>
      <Title level={4}>💱 汇率录入 <Text type="secondary" style={{ fontSize: 14, fontWeight: 'normal' }}>汇率月固定：每月 1 号录一次，收款/合同按日期自动取当月汇率</Text></Title>

      <Card size="small" style={{ marginBottom: 16 }}>
        <Row gutter={16}>
          <Col span={5}><Text type="secondary">币种 *</Text>
            <Select style={{ width: '100%' }} value={currency} onChange={setCurrency}
              options={['USD', 'EUR', 'IDR', 'CNY'].map((c) => ({ value: c, label: c }))} /></Col>
          <Col span={6}><Text type="secondary">汇率（1 原币 = ? CNY）*</Text>
            <InputNumber style={{ width: '100%' }} min={0} step={0.0001} precision={4} value={rate} onChange={setRate} /></Col>
          <Col span={5}><Text type="secondary">生效日期（每月 1 号）*</Text>
            <DatePicker style={{ width: '100%' }} value={effDate} onChange={(v) => v && setEffDate(v)} /></Col>
          <Col span={8}><Text type="secondary">备注</Text>
            <Input value={remark} onChange={(e) => setRemark(e.target.value)} /></Col>
        </Row>
        <Space style={{ marginTop: 16 }}>
          <Input placeholder="操作人（写入审计日志）" style={{ width: 200 }} value={operator} onChange={(e) => setOperator(e.target.value)} />
          <Button type="primary" size="large" onClick={onSubmit}>预览并提交</Button>
        </Space>
      </Card>

      <Card size="small" title="最近汇率">
        <Table size="small" rowKey={(r) => `${r.currency}-${r.effective_date}`} dataSource={recent} pagination={false}
          columns={[
            { title: '币种', dataIndex: 'currency', width: 80 },
            { title: '汇率', dataIndex: 'rate_to_cny', width: 100, render: (v) => Number(v).toFixed(4) },
            { title: '生效日期', dataIndex: 'effective_date', width: 120, render: (v) => String(v).slice(0, 10) },
            { title: '来源', dataIndex: 'source', width: 80 },
          ]} />
      </Card>

      <Modal
        title="确认入库"
        open={previewOpen}
        onOk={onConfirm}
        onCancel={() => setPreviewOpen(false)}
        okText="确认入库" cancelText="返回修改"
        confirmLoading={submitting}
        okButtonProps={{ disabled: previewErrors.length > 0 }}
      >
        {previewErrors.length > 0 ? (
          <ul style={{ color: '#cf1322', paddingLeft: 18 }}>
            {previewErrors.map((e, i) => <li key={i}>{e}</li>)}
          </ul>
        ) : (
          <p><b>{currency}</b> = {rate} CNY，自 <b>{effDate.format('YYYY-MM-DD')}</b> 起生效（同币种同日期的旧记录会被查重拦截）</p>
        )}
      </Modal>
    </div>
  )
}
