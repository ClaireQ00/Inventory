# Inventory API — FastAPI 包装层
# 构建上下文是项目根目录 (docker-compose build.context: .)
FROM python:3.11-slim

WORKDIR /app

# pip 走清华镜像 (NAS 国内网络环境, 与 streamlit 容器一致)
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

COPY api/requirements.txt /app/api/requirements.txt
RUN pip install --no-cache-dir -r /app/api/requirements.txt

COPY api/ /app/api/
# tools/ 运行期以 ro 挂载提供 (docker-compose volumes), 与 streamlit 容器同款,
# 保证 db_writer/csv_to_sql/local_validator 改动即时生效不用重建镜像

EXPOSE 8000
CMD ["python", "/app/api/main.py"]
