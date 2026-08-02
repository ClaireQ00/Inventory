// Inventory 录入端 — 根组件 (antd 布局 + 路由)
// 定位: 录入/导入/操作全部在这里; Streamlit (8501) 只做查询、报表、校验日志
import { App as AntApp, ConfigProvider, Layout, Menu, Typography } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { FormOutlined, HomeOutlined } from '@ant-design/icons'
import { Link, Route, Routes, useLocation } from 'react-router'
import Home from './pages/Home'
import ProductEntry from './pages/ProductEntry'

const { Header, Sider, Content } = Layout

export default function App() {
  const location = useLocation()
  return (
    <ConfigProvider locale={zhCN}>
      <AntApp>
        <Layout style={{ minHeight: '100vh' }}>
          <Header style={{ display: 'flex', alignItems: 'center', background: '#001529' }}>
            <Typography.Text style={{ color: '#fff', fontSize: 16, fontWeight: 600 }}>
              📦 Inventory 录入端
            </Typography.Text>
            <Typography.Text style={{ color: '#ffffff88', fontSize: 12, marginLeft: 12 }}>
              查询/报表请用 Streamlit 工作台 (8501)
            </Typography.Text>
          </Header>
          <Layout>
            <Sider width={200} theme="light">
              <Menu
                mode="inline"
                selectedKeys={[location.pathname]}
                style={{ height: '100%', borderRight: 0 }}
                items={[
                  { key: '/', icon: <HomeOutlined />, label: <Link to="/">首页</Link> },
                  {
                    key: 'entry', icon: <FormOutlined />, label: '录入中心',
                    children: [
                      { key: '/entry/product', label: <Link to="/entry/product">🧱 物料</Link> },
                      { key: '/entry/receipt', label: '💰 收款（下一阶段）', disabled: true },
                      { key: '/entry/rate', label: '💱 汇率（下一阶段）', disabled: true },
                    ],
                  },
                ]}
              />
            </Sider>
            <Content style={{ padding: 24, background: '#f5f5f5' }}>
              <Routes>
                <Route path="/" element={<Home />} />
                <Route path="/entry/product" element={<ProductEntry />} />
              </Routes>
            </Content>
          </Layout>
        </Layout>
      </AntApp>
    </ConfigProvider>
  )
}
