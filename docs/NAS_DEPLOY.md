# NAS 部署手册（绿联 DXP4800 Plus）

> 本手册面向**部署者**（你，会 SSH 的人）。部署完成后，团队（非技术同事）看 [REMOTE_ACCESS.md](REMOTE_ACCESS.md) 即可。
>
> 目标：把进销存系统部署到绿联 NAS 上，让团队通过互联网用浏览器查看数据。

---

## 整体流程（5 步）

1. 验证公网 IP（前提，必做）
2. NAS 上放好项目文件
3. SSH 登录 NAS 启动容器
4. 配置 DDNS 域名
5. 路由器端口转发

---

## ⚠️ 第 1 步：验证你有没有公网 IP（成败关键）

公网 IP + DDNS 这条路的**前提是真有公网 IP**。国内很多宽带是"大内网"（运营商 NAT），没有公网 IP 这条路走不通。**不验证就做后面，全是白工。**

### 验证方法（5 分钟）

1. 在你**电脑**浏览器打开 https://www.ip138.com ，记下显示的 IP（比如 `114.114.114.114`）

2. SSH 登录 NAS（见第 3 步先开 SSH），执行：
   ```bash
   curl -s ip.sb && echo
   ```
   记下 NAS 看到的出口 IP

3. 对比两个 IP：

   | 情况 | 含义 | 能否用本方案 |
   |---|---|---|
   | 两个 IP **相同** | ✅ 你有公网 IP | 可以，继续往下 |
   | 两个 IP **不同** | ❌ 大内网（运营商 NAT） | **不行**，换 frp 穿透 |
   | IP 是 `10.x` / `100.64.x` / `172.16-31.x` | ❌ 内网地址 | **不行**，换 frp 穿透 |

> **如果没有公网 IP**：停在这里，告诉我（或在搜索里搜"绿联 frp 内网穿透"），改用第三方穿透方案。本手册后面步骤不适用。

---

## 第 2 步：在 NAS 上放好项目文件

### 2.1 建目录
在 UGOS Pro 文件管理里，建：
```
/Docker/inventory/
```

### 2.2 上传文件
把你电脑上 `/Users/guixinqie/inventory` 的这些文件传到 NAS 的 `/Docker/inventory/`：

**必需文件：**
- `docker-compose.yml`
- `.env.example`
- `sql/` 整个目录（含 01/02/03 三个 .sql）

> 上传方式：UGOS 文件管理拖拽上传，或用 scp：
> ```bash
> scp -r docker-compose.yml .env.example sql/ 你的NAS用户名@NAS内网IP:/Docker/inventory/
> ```

---

## 第 3 步：SSH 登录 NAS 启动容器

### 3.1 开启 SSH
UGOS Pro → **控制面板 → 终端和 SNMP → 启用 SSH**，记下端口号（通常 22）和你的 NAS 用户名。

### 3.2 SSH 登录
```bash
ssh 你的NAS用户名@NAS内网IP
# 例如: ssh admin@192.168.1.100
```

### 3.3 准备 .env 配置
```bash
cd /Docker/inventory
cp .env.example .env
```
编辑 `.env`，**改掉两个密码**（务必改成 16 位以上强密码，因为要暴露公网）：
```bash
vi .env
# 或用 nano .env
```
把这两行的"请改成..."换成你的强密码：
```
MYSQL_ROOT_PASSWORD=你的强密码A
MYSQL_PASSWORD=你的强密码B
```

### 3.4 启动容器
```bash
docker compose up -d
```
第一次会拉取 MySQL + Adminer 镜像（约 2-3 分钟）。

### 3.5 确认启动成功
```bash
docker compose ps
```
看到 `db` 和 `adminer` 都是 `Up (healthy)` 就成功了。

验证数据库表已建好：
```bash
docker exec inventory-db mysql -uroot -p你的强密码A inventory_db \
  -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='inventory_db';"
```
应该显示 `25`。

### 3.6 局域网验证
在你电脑浏览器打开：`http://NAS内网IP:8080`
能出现 Adminer 登录页 = 容器层 OK，继续下一步。

---

## 第 4 步：配置 DDNS 域名

家庭宽带公网 IP 会变（重启路由器/运营商更换），需要 DDNS 把域名自动指向当前 IP。

### 选一个方式：

### 方式 A：路由器自带 DDNS（最省事）
很多路由器（华硕、小米、华为、openwrt）后台有 DDNS 功能：
- 进路由器管理页 → 找"DDNS"或"动态域名"
- 注册一个账号（路由器厂商通常送免费二级域名）
- 得到类似 `yourname.asuscomm.com` 的域名，路由器自动更新 IP

### 方式 B：阿里云 / 腾讯云 DDNS（推荐，稳定可控）
1. 买一个域名（阿里云/腾讯云，约 30-50 元/年）
2. NAS 上跑一个 DDNS 客户端容器，自动更新解析。常用镜像如 `jeessy/ddns-go`：
   ```bash
   docker run -d --name ddns-go --restart=always --net=host \
     -v /Docker/ddns-go:/root jeessy/ddns-go
   ```
3. 浏览器打开 `http://NAS内网IP:9876` 配置（填域名、API 密钥）

### 方式 C：DuckDNS / No-IP（免费）
注册 https://www.duckdns.org ，免费得一个二级域名如 `yourname.duckdns.org`，按官网给的 docker 命令部署客户端。

> 配好后，测试：在你电脑上 `ping 你的域名`，看解析出的 IP 是不是你第 1 步查到的公网 IP。一致就成了。

---

## 第 5 步：路由器端口转发

这是让公网访问能到达 NAS 的关键。

### 5.1 在路由器添加转发规则
进路由器管理页 → **端口转发 / 虚拟服务器 / NAT**，加一条：

| 字段 | 填什么 |
|---|---|
| 外部端口 | `8080`（或你设的 ADMINER_PORT） |
| 内部 IP | NAS 的内网 IP（如 192.168.1.100） |
| 内部端口 | `8080` |
| 协议 | TCP |

> ⚠️ **绝对不要**转发 3306（MySQL）！数据库直连公网极危险。
> compose 里 MySQL 已绑 127.0.0.1，即使误转发也连不上，但别开。

### 5.2 光猫桥接问题（很多人卡在这）
如果你家是**光猫拨号**（不是路由器拨号），存在两层 NAT：
- 光猫 → 路由器 → NAS

此时只在路由器转发没用，还要：
- 进光猫管理页（通常 192.168.1.1），也加一条 8080 的端口转发到路由器
- 或打运营商电话，让光猫改**桥接模式**（改完由你的路由器拨号，只剩一层 NAT，最干净）

判断方法：路由器 WAN 口 IP 如果是 `192.168.x.x` 或 `100.64.x.x`，说明光猫没桥接，有双层 NAT。

---

## 第 6 步：外网验证（必须用外网测）

⚠️ 在**家里 WiFi 下**访问你的域名往往会失败（NAT 回环问题），必须用**外网**测：

- 手机**关掉 WiFi，用 4G/5G**，浏览器打开 `http://你的域名:8080`
- 或让外地同事打开 `http://你的域名:8080`

看到 Adminer 登录页 = 部署成功！🎉

登录信息（填这些）：
| 字段 | 值 |
|---|---|
| 数据库系统 | MySQL |
| 服务器 | `db` |
| 用户名 | `inventory`（或你 .env 里的 MYSQL_USER） |
| 密码 | 你 .env 里的 MYSQL_PASSWORD |
| 数据库 | `inventory_db` |

---

## 灌入业务数据（部署后做一次）

容器只是空库 + 基础字典数据。要让团队看到真实业务数据，在**你本机**跑：
```bash
cd /Users/guixinqie/inventory
# 把 .env 里的连接信息指向 NAS（临时），或直接用 load 脚本
bash scripts/load-csv-to-db.sh         # 灌 data/csv 下的真实数据
```
> 注：`load-csv-to-db.sh` 默认连本地容器。灌到 NAS 需让它连 NAS 的数据库——因为 MySQL 只绑了 127.0.0.1，**灌数要在 NAS 上执行**（SSH 进去后把 CSV 也传上去再跑）。

---

## 常见问题

### Q1：`docker compose` 命令找不到
绿联 UGOS Pro 的 Docker 可能需要 SSH 进去后用 `sudo docker compose`，或镜像较老时是 `docker-compose`（带横线）。

### Q2：外网访问超时，但局域网 OK
99% 是端口转发 / 光猫桥接问题。看第 5.2 节，检查是否有双层 NAT。

### Q3：外网访问提示"连接被重置"
- 检查路由器端口转发协议选了 TCP（不是 UDP）
- 部分地区运营商封 80/8080 端口，换个高端口（如 18080），同步改 `.env` 的 `ADMINER_PORT` 和转发规则

### Q4：DDNS 域名解析的 IP 不对
等 5-10 分钟 DNS 生效，或手动在 DDNS 客户端触发更新。

### Q5：怎么备份数据库
```bash
docker exec inventory-db mysqldump -uroot -p你的密码A inventory_db > backup_$(date +%F).sql
```
建议设个定时任务（UGOS 任务计划）每天备份到另一个目录。

> **2026-08-01 辅料模块起，备份范围多了一个目录**：辅料附件（标签纸图纸/样张）落盘在
> `./data/attachments/`（DB 里只存路径+哈希，文件本身不进 mysqldump）。
> 备份脚本要连 `./data/attachments/` 一起打包，否则恢复后附件记录还在、文件没了。

### Q6：怎么更新代码/重新部署
改完文件传到 NAS，然后：
```bash
cd /Docker/inventory
docker compose down
docker compose up -d
```
数据在 `./mysql-data`，不会丢。

### Q7：MySQL 改了密码容器起不来
`.env` 里的密码**只在首次创建数据卷时生效**。改密码要：
1. `docker compose down`
2. `rm -rf mysql-data`（⚠️ 会清空数据，先备份！）
3. 改 `.env`
4. `docker compose up -d`

---

## 安全清单（部署完自查）

- [ ] `.env` 里两个密码都是 16 位以上强密码
- [ ] 路由器**只**转发了 8080，没转发 3306
- [ ] MySQL 端口绑的是 127.0.0.1（`docker port inventory-db` 应显示 `127.0.0.1:3306`）
- [ ] 团队用 `inventory` 账号登录，不是 root
- [ ] 数据库已设置定期备份
