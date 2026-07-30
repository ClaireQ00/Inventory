# 远程团队使用指南（不看代码也能用）

> 本指南面向**不写代码**的同事。照着做完，你就能在自己电脑上用浏览器看库存、合同、应收等所有业务数据。
>
> 全程只需要 4 步，每步都写得很细。遇到问题直接跳到最后的【常见问题】。

---

## 你需要准备什么

- 一台电脑（Windows / Mac 都行）
- 管理员权限（装软件要用）
- 同事给你的两个文件：`docker-compose.yml` 和 `.env`
  （或者同事把 GitHub 仓库地址给你，你自己下载整个项目也行）

---

## 第 1 步：安装 Docker Desktop（只装一次）

这是唯一需要安装的软件。装完之后，以后都不用再装。

### Windows
1. 打开 https://www.docker.com/products/docker-desktop/
2. 点 **Download for Windows**，下载后双击安装
3. 一路"下一步"，装完后**重启电脑**
4. 打开 Docker Desktop（开始菜单里找），等左下角图标变成**绿色**（说明已启动）

### Mac
1. 打开 https://www.docker.com/products/docker-desktop/
2. 点 **Download for Mac**，选你电脑的芯片（Apple 芯片选 **Apple Silicon**，老款选 **Intel**）
3. 下载后把 Docker 拖进"应用程序"文件夹
4. 打开 Docker，等右上角鲸鱼图标显示 **"Docker Desktop is running"**

> ✅ **怎么算装好了？**
> 打开"终端"（Mac）或"命令提示符"（Win），输入 `docker --version`，
> 如果显示 `Docker version ...` 就成功了。如果提示"找不到命令"，说明 Docker 没启动，去打开 Docker Desktop。

---

## 第 2 步：拿到项目文件

同事会二选一给你：

**方式 A：同事直接发了文件给你**
1. 新建一个文件夹，比如叫 `inventory`
2. 把 `docker-compose.yml` 和 `.env` 放进去

**方式 B：同事给了 GitHub 仓库地址**
1. 下载整个项目压缩包，解压
2. 确保里面有 `docker-compose.yml` 和 `.env` 这两个文件

> ⚠️ `.env` 文件里有数据库密码，**这个文件别外传**。

---

## 第 3 步：启动系统（就一条命令）

1. 打开**终端**（Mac：启动台搜"终端"；Win：开始菜单搜"命令提示符"）
2. 进入你放文件的文件夹。比如文件在桌面 `inventory` 文件夹：
   ```
   cd Desktop/inventory
   ```
3. 输入这一条命令，回车：
   ```
   docker compose up -d
   ```
4. **第一次启动会下载 MySQL（约 1-2 分钟），耐心等。**

> ✅ **怎么算启动成功？**
> 输入 `docker compose ps`，看到 `db` 和 `adminer` 两个服务都是 `running` / `healthy`，就成了。

---

## 第 4 步：用浏览器看数据 🎉

1. 打开浏览器（Chrome / Edge 都行）
2. 地址栏输入：**http://localhost:8080**
3. 会出现登录页面，填：
   | 字段 | 填什么 |
   |---|---|
   | 数据库系统 | 选 **MySQL** |
   | 服务器 | `db`（就这两个字母） |
   | 用户名 | 同事告诉你（通常 `inventory`） |
   | 密码 | 同事告诉你（就是 `.env` 里的 `MYSQL_PASSWORD`） |
   | 数据库 | `inventory_db` |
4. 点**登录**

进去之后：
- 左边能看到所有表（点表名看数据）
- 点**选数据**可以加条件查询
- 点**导出**可以把数据存成 Excel

---

## 以后每次用，就两步

不用再装软件了。只要：

1. 启动：终端里 `cd` 到文件夹，敲 `docker compose up -d`
2. 浏览器打开 http://localhost:8080

**用完想关掉**（节省电脑内存）：
```
docker compose down
```
> 数据不会丢，下次启动还在。

---

## 常见问题

### Q1：`docker compose up -d` 报错 "port is already allocated"（端口被占用）
3306 或 8080 端口被别的程序占了。
打开 `.env` 文件，把 `MYSQL_PORT=3306` 改成 `MYSQL_PORT=33060`，
或把 `ADMINER_PORT=8080` 改成 `ADMINER_PORT=8081`，重新启动。

### Q2：启动后浏览器打不开，或一直转圈
MySQL 还在初始化（第一次较慢）。终端敲 `docker compose logs db` 看日志，
等到出现 `ready for connections` 就能用了（通常 30 秒内）。

### Q3：登录页提示"Access denied"（拒绝访问）
用户名或密码错了。检查 `.env` 文件里的 `MYSQL_USER` 和 `MYSQL_PASSWORD`，
和登录页填的是否一致。

### Q4：我想彻底重来（清空所有数据）
```
docker compose down -v
docker compose up -d
```
> ⚠️ `-v` 会删除所有数据，重新从空数据库开始。确定要清空再用。

### Q5：Mac 上命令找不到 `docker`
Docker Desktop 没启动。打开"应用程序" → Docker，等它跑起来再试。

### Q6：数据是空的 / 想看演示数据
说明还没有数据灌进去。联系给你项目的同事，让他跑 `bash scripts/load-csv-to-db.sh --demo` 给你准备演示数据。

---

## 不明白就问

以上任何一步卡住，截图发给给你项目的同事，他懂技术能帮你解决。
