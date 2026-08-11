# 家庭部署完整方案：绿联 DXP4800 Plus + Windows 电脑（IPv6 环境）

> **这份文档给谁看**：老板本人（不假设有部署经验）。
> **目标**：系统跑起来后，同事在任何地方都能用浏览器访问；家里网络出问题时，整套设备搬到办公室插电就能继续用。
> **读完你能得到**：① 正常运行方案 ② 应急搬迁方案 ③ 各种意外情况的处置表。
>
> 相关旧文档：[NAS_DEPLOY.md](NAS_DEPLOY.md)（早期只装 Adminer 的版本，已被本文取代）、[REMOTE_ACCESS.md](REMOTE_ACCESS.md)（同事用速查卡，需按本文更新）。

---

## 0. 一张图看懂最终形态

```
同事浏览器（公司/外地/手机）
        │
        │  http://你的域名:8082   ← IPv6 + DDNS 域名
        ▼
家里路由器（IPv6 防火墙放行 8082/8501）
        │
        ▼
绿联 NAS DXP4800 Plus（7×24 开机）
   └─ Docker 跑 4 个服务：
      inventory-db        MySQL 数据库（数据在 NAS 硬盘上）
      inventory-api       后端规则层
      inventory-frontend  录入端（同事主要用这个，端口 8082）
      inventory-streamlit 查询/报表端（端口 8501）

Windows 电脑（家里的维护终端，平时可以关机）
   └─ 用途：改配置、更新代码、做备份、出事时救场
```

**为什么系统跑 NAS 而不是 Windows 电脑**：

| | 绿联 NAS | Windows 电脑 |
|---|---|---|
| 设计用途 | 7×24 服务器 | 办公机 |
| 断电后来电 | ✅ 可设自动开机+容器自启 | ❌ 要人工按电源 |
| Windows 自动更新 | 没有 | ❌ 半夜重启，服务全停 |
| 合盖/休眠 | 没有 | ❌ 一休眠同事全断线 |
| Docker 稳定性 | 原生 Linux | Docker Desktop 需登录才启动 |

Windows 电脑不是没用——它是你的**维护终端**：改东西、更新、备份、救场都靠它。但"跑服务"这件事交给 NAS。

---

## 1. 一次性准备工作（Windows 电脑侧）

### 1.1 装三个软件（各约 10 分钟）

| 软件 | 干什么用 | 下载 |
|---|---|---|
| **Git** | 把项目从 Mac 搬到 Windows | https://git-scm.com/download/win |
| **Docker Desktop** | 备用运行环境（应急时 Windows 也能跑系统） | https://www.docker.com/products/docker-desktop/ |
| **Termius 或 PuTTY** | SSH 连 NAS 的工具（图形界面，不用记命令） | https://termius.com/ |

> Docker Desktop 安装时会要求启用 WSL2，一路点"是"即可，装完重启一次电脑。

### 1.2 把项目搬到 Windows

在 Windows 上打开"Git Bash"（装完 Git 后右键菜单里有）：

```bash
# 方式一：如果 Mac 还能用，从 git 仓库克隆最新代码
git clone /Users/guixinqie/inventory  # 或从你们的远程仓库克隆

# 方式二：U盘/局域网直接拷贝整个 inventory 文件夹
```

**必须额外拷贝的数据文件**（这些不在 git 里，丢了等于系统白装）：

| 文件/目录 | 里面是什么 | 丢了会怎样 |
|---|---|---|
| `data/csv/*.csv` | 全部业务数据（14,352 物料/596 客户/单据） | 系统变空壳 |
| `data/attachments/` | 标签纸图纸/样张 | 附件记录还在、文件没了 |
| `.env` | 数据库密码 | 连不上数据库（可重建但要重设） |
| `data/logs/material_remap_20260811.csv` | 物料新旧编码对照 | 历史单据对不上新编码 |

> **建议做法**：在 Mac 上先把这些打个压缩包——`tar -czf inventory-data-20260811.tar.gz data/ .env`，U盘拷到 Windows 解压。

---

## 2. 正式部署：系统跑在 NAS 上

### 2.1 NAS 准备（在 UGOS 网页后台操作）

1. **开 SSH**：控制面板 → 终端和 SNMP → 启用 SSH，记下端口（通常 22）
2. **建目录**：文件管理里建 `/Docker/inventory/`
3. **传文件**：把 Windows 上的项目文件传到这个目录。必需：
   - `docker-compose.yml`、`api/`、`frontend/`、`tools/`、`sql/`、`scripts/`
   - `data/csv/`（真实数据）、`data/attachments/`（附件）
   - `.env`（密码文件，改名叫 `.env` 放根目录）

### 2.2 修改 NAS 上的 .env（关键三处）

用 UGOS 文件管理的文本编辑器，或 SSH 进去用 `vi` 改：

```ini
# ① 数据库密码：换成 16 位以上强密码（系统要暴露到公网，弱密码=裸奔）
MYSQL_ROOT_PASSWORD=你的强密码A
MYSQL_PASSWORD=你的强密码B

# ② 跳转按钮的目标地址：填你的 DDNS 域名（第 3 步会配）
#    这样同事点"➕新增"按钮才能跳到正确的录入端
ENTRY_BASE=http://你的域名:8082

# ③ 端口保持默认即可
FRONTEND_PORT=8082
STREAMLIT_PORT=8501
```

### 2.3 启动（SSH 进 NAS 执行）

```bash
cd /Docker/inventory
docker compose up -d --build
```

第一次要构建镜像+拉取依赖，约 10-20 分钟（前端 npm 安装最慢，耐心等）。

### 2.4 验证（在家里电脑浏览器）

| 检查 | 地址 | 成功标志 |
|---|---|---|
| 录入端 | `http://NAS的内网IP:8082` | 看到录入端首页 |
| 查询端 | `http://NAS的内网IP:8501` | 看到进销存工作台 |
| 后端连通 | `http://NAS的内网IP:8082/api/health` | `{"ok":true,"db":"connected"}` |

> NAS 内网 IP 在 UGOS 控制面板 → 网络里能看到，一般是 `192.168.x.x`。

### 2.5 灌入真实数据（只做一次）

因为 MySQL 容器只监听内部地址，灌数要在 NAS 上执行（SSH 进去）：

```bash
cd /Docker/inventory
bash scripts/load-csv-to-db.sh
```

跑完进 8501 基础资料页，产品物料应该显示 14,000+ 行。

### 2.6 设置容器自动重启（断电/重启后自动恢复）

确认 `docker-compose.yml` 里每个服务都有 `restart: unless-stopped`（项目已带）。再在 UGOS 里：
- 控制面板 → 硬件和电源 → **来电自动开机** 打开
- 这样停电后来电：NAS 自启 → Docker 自启 → 4 个容器自启，全程无人值守

---

## 3. 让同事能访问：IPv6 + DDNS 域名

### 3.1 为什么用 IPv6，和 IPv4 方案的区别

你家宽带没有公网 IPv4（国内常态），但**有公网 IPv6**——这是好事：

| | IPv4 方案 | IPv6 方案（你用这个） |
|---|---|---|
| 公网地址 | 大多没有（大内网） | ✅ 每台设备都有公网 IPv6 |
| 端口转发 | 需要路由器+光猫两层配置 | ❌ 不需要，地址直达 |
| 要配什么 | 端口转发+桥接 | 只需路由器**防火墙放行** |

### 3.2 找到 NAS 的 IPv6 地址

UGOS 控制面板 → 网络 → 看到类似 `240e:3a1:xxxx:xxxx::xxxx` 的地址（`240e`/`2408`/`2409` 开头的是公网 IPv6；`fe80` 开头的是内网地址，不是它）。

浏览器测试：`http://[你的IPv6地址]:8082`（**IPv6 地址要用方括号包起来**），家里能开就说明通了。

### 3.3 防火墙放行（关键一步）

国内路由器的 IPv6 默认**只出不进**（安全策略），要在路由器后台把 NAS 的两个端口放行：

1. 进路由器管理页 → 找 **IPv6 防火墙 / 端口开放 / 访问控制**
2. 加规则：允许外部访问 NAS 的 IPv6 地址的 **8082** 和 **8501** 端口（TCP）
3. ⚠️ **不要**放行 3306（数据库）和 8080（Adminer）

> 不同品牌路由器叫法不同：华为叫"IPv6 防火墙规则"，小米在"安全中心"，华硕在"防火墙→IPv6"。找不到就搜"你的路由器型号 IPv6 端口放行"。

### 3.4 DDNS：给会变的 IPv6 一个固定域名

运营商会定期更换你家 IPv6 前缀（重启光猫必换），所以需要一个域名自动跟着变：

1. **买域名**（推荐）或免费用 DuckDNS：阿里云/腾讯云买 `.com`/`.cn` 约 30-50 元/年
2. **NAS 上跑 ddns-go**（自动把域名指向当前 IPv6）：
   ```bash
   docker run -d --name ddns-go --restart=always --net=host \
     -v /Docker/ddns-go:/root jeessy/ddns-go
   ```
3. 浏览器开 `http://NAS内网IP:9876`，选你的 DNS 服务商（阿里云/腾讯云/Cloudflare），**记录类型选 AAAA（IPv6）**，填入 API 密钥
4. 等 5 分钟，手机**关 WiFi 用流量**开 `http://你的域名:8082`——能开就成了

> ⚠️ **为什么必须用手机流量测**：家里 WiFi 下访问自己的公网地址经常不通（NAT 回环问题），不是配置错了。

### 3.5 一个重要提醒：同事的网络可能没有 IPv6

这是 IPv6 方案唯一的软肋：**同事那边如果只有 IPv4**（部分公司网络、老旧宽带），就打不开你的系统。应对：

- 先让同事打开手机流量测——**手机 4G/5G 全都有 IPv6**，流量能开说明系统没问题
- 公司网络不行的话：让 IT 开通 IPv6（2026 年大多数企业网已支持），或者给关键同事备用方案——见第 5 节"办公室局域网模式"
- 如果主要用户都在一个 IPv4-only 的公司网络，那就考虑 frp 内网穿透兜底（到时叫我配）

---

## 4. 日常使用与维护

### 4.1 给同事的地址（就两个）

| 用途 | 地址 | 给谁 |
|---|---|---|
| 录入端（录物料/报价/合同/出入库） | `http://你的域名:8082` | 所有同事 |
| 查询报表端（查库存/报表/校验日志） | `http://你的域名:8501` | 业务/财务 |

把 [REMOTE_ACCESS.md](REMOTE_ACCESS.md) 按这两个地址更新后发给同事即可。

### 4.2 每周备份（重要！）

SSH 进 NAS，建个备份脚本 `/Docker/inventory/backup.sh`：

```bash
#!/bin/bash
cd /Docker/inventory
D=$(date +%F)
mkdir -p /Docker/backups/$D
# ① 数据库导出
docker exec inventory-db mysqldump -uinventory -p你的密码B inventory_db \
  > /Docker/backups/$D/inventory_db.sql
# ② 数据文件（CSV 双轨 + 附件 + 日志）
tar -czf /Docker/backups/$D/data.tar.gz data/
# ③ 只保留最近 30 天
find /Docker/backups -maxdepth 1 -mtime +30 -exec rm -rf {} \;
```

然后在 UGOS **任务计划**里加一条：每天凌晨 3 点跑这个脚本。

> 绿联 NAS 如果用 RAID1（两块硬盘镜像），单盘坏不丢数据；但 RAID 不防误删，**备份脚本才是底线**。条件允许的话，每月把 `/Docker/backups` 拷贝一份到 Windows 电脑或 U盘（异地副本）。

### 4.3 更新系统（我改完代码后）

我在 Mac 这边改完代码提交后，你把最新代码和 `data/csv` 同步到 NAS，然后：

```bash
cd /Docker/inventory
docker compose up -d --build   # 改了 api/frontend 才需要 --build
docker compose restart api     # 只改了 tools/db_writer.py 时这条就够
```

数据在 `mysql-data` 卷和 `data/` 目录里，更新不会丢。

---

## 5. 应急方案：搬到办公室变局域网系统

**触发场景**：家里断网/断电一时半会修不好、运营商出问题、IPv6 被运营商收回。

**核心思想**：系统的全部家当都在 NAS 硬盘上（数据库 + 数据文件 + 配置），搬过去插电就能用，唯一要处理的是"地址变了"。

### 5.1 搬迁前准备（现在就做，5 分钟）

把这几样**打印出来贴在 NAS 上**：

```
应急搬迁清单
─────────────
1. NAS 电源线、网线 x1
2. Windows 笔记本（或任意一台电脑）
3. 本指南第 5 节
4. 数据库密码位置：NAS 上 /Docker/inventory/.env
```

### 5.2 搬到办公室后的操作（15 分钟）

1. **接线**：NAS 用网线插办公室路由器/交换机，按电源开机
2. **查新 IP**：等 2 分钟开机完成，然后：
   - 方法一：办公室路由器后台 → 设备列表 → 找"UGREEN"或"DXP4800"，看它的 IP（比如变成 `192.168.31.88`）
   - 方法二：Windows 笔记本装个"Advanced IP Scanner"扫一遍网段
3. **验证**：笔记本浏览器开 `http://新IP:8082` → 能开 = 系统活了，数据都在
4. **改跳转地址**：SSH 进 NAS（用新 IP），把 `.env` 里的 `ENTRY_BASE` 改成 `http://新IP:8082`，然后 `docker compose restart streamlit`
5. **发通知**：告诉同事"系统临时地址 `http://新IP:8082` 和 `http://新IP:8501`"

就这些。**数据库、数据文件、配置全部原样**，因为都在 NAS 上。

### 5.3 搬回家之后

1. NAS 接回家里的网，DDNS 客户端（ddns-go）检测到 IP 变化会**自动更新域名解析**，一般 5-10 分钟恢复
2. 把 `.env` 的 `ENTRY_BASE` 改回 `http://你的域名:8082`，重启 streamlit
3. 同事继续用域名访问，不用记新地址

> 💡 **更省心的进阶做法**（可选）：让同事**永远只用域名**访问。在办公室局域网里，临时在路由器把域名指到 NAS 的内网 IP（一条本地 DNS 记录），同事那边什么都不用改。这个到时我可以远程帮你配。

---

## 6. 意外情况处置表

| 意外 | 现象 | 处置 |
|---|---|---|
| **家里停电** | 全员断线 | 等来电：NAS 自启→容器自启，无需操作（前提是 2.6 步做了） |
| **家里断网** | 外网同事断线 | 短期：同事先用手机流量（流量有 IPv6 可能绕开故障）；长期不好：启动第 5 节搬迁 |
| **IPv6 前缀变了** | 域名暂时打不开 | ddns-go 5-10 分钟自动更新，等一等；超过 30 分钟检查 ddns-go 容器是否还活着 |
| **域名突然全部打不开** | 先判断是域名还是系统问题 | 用内网 IP 开 `http://NAS内网IP:8082`：能开=域名/DDNS 问题（查 ddns-go）；不能开=NAS/容器问题（SSH 上去 `docker compose ps`） |
| **NAS 硬盘报警** | UGOS 提示硬盘故障 | RAID1 的话买同型号硬盘热插拔更换；同时确认备份脚本最近在正常跑 |
| **误删了数据** | 某张单/某个客户没了 | 用最近备份恢复：`docker exec -i inventory-db mysql -uinventory -p密码 inventory_db < 备份.sql`；或叫我从 `data/csv` 重建（双轨的意义就在这） |
| **Windows 电脑坏了** | 无法维护 NAS | 不影响系统运行！换任何一台电脑装 Termius 都能 SSH 维护 |
| **忘了数据库密码** | Adminer 登不上 | 打开 NAS 上 `.env` 文件直接看，永远不会丢 |
| **路由器坏了/换路由器** | 端口放行规则丢失 | 换路由器后重做第 3.3 步（IPv6 防火墙放行 8082/8501） |
| **整个项目要换 NAS** | 硬件升级 | 拷走 `/Docker/inventory` 整个目录 + 备份，新 NAS 原样放回，`docker compose up -d` 即可 |

### 判断故障的三板斧（顺序执行，能解决 90% 问题）

```bash
# ① 容器活着吗？（SSH 进 NAS）
docker compose ps          # 4 个服务应该都是 Up

# ② 数据库通吗？
curl http://localhost:8082/api/health   # 应返回 {"ok":true,"db":"connected"}

# ③ 都没问题但外面打不开？那是网络层：查 IPv6 防火墙 + ddns-go 解析
```

---

## 7. 部署 checklist（打勾用）

**首次部署**
- [ ] Windows 装好 Git / Docker Desktop / Termius
- [ ] Mac 上的 `data/` 和 `.env` 已拷到 Windows 再传到 NAS
- [ ] NAS 上 `.env` 改了强密码、填了 `ENTRY_BASE`
- [ ] `docker compose up -d --build` 成功，4 容器 Up
- [ ] 内网能开 8082 和 8501
- [ ] 数据已灌入（products 14,000+ 行）
- [ ] IPv6 防火墙放行 8082/8501
- [ ] ddns-go 运行中，域名解析正确（手机流量验证）
- [ ] 备份脚本 + UGOS 定时任务已设置
- [ ] NAS 来电自启已打开
- [ ] 应急搬迁清单已打印贴 NAS 上

**每月例行**
- [ ] 抽查一次备份目录有新文件
- [ ] 备份拷一份到 U盘/另一台电脑（异地副本）

---

> **维护分工**：这份指南覆盖的是"部署和运维"。系统功能层面的改动（加页面、改规则）照旧由我（Kimi）在 Mac 开发环境完成后，你按 4.3 节同步到 NAS。遇到这份文档没覆盖的状况，描述现象发给我即可。
