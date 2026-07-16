ARG NODE_IMAGE=node:22-alpine
ARG PYTHON_IMAGE=python:3.12-slim

FROM ${NODE_IMAGE} AS frontend

WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend ./
RUN npm run build

FROM ${PYTHON_IMAGE} AS backend

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VMLAB_WORKSPACE=/app \
    VMLAB_METADATA_DB=artifacts/vision_model_lab.sqlite3 \
    VMLAB_SERVE_FRONTEND=true

WORKDIR /app

# 先只拷贝依赖描述文件建立独立依赖层：源码改动不再触发依赖全量重装。
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

COPY configs ./configs
COPY data ./data
COPY labeling ./labeling
COPY experiments ./experiments
COPY scripts ./scripts
COPY migrations ./migrations
COPY alembic.ini ./
COPY --from=frontend /app/frontend/dist ./frontend/dist

# 平台会执行外部训练命令，必须以非 root 运行以限制越权面。
RUN useradd --create-home --shell /usr/sbin/nologin vmlab \
    && mkdir -p /app/artifacts /app/shared-models \
    && chown -R vmlab:vmlab /app
USER vmlab

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3)"]

CMD ["uvicorn", "vision_model_lab.api:app", "--host", "0.0.0.0", "--port", "8080"]
