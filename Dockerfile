ARG NODE_IMAGE=swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/node:22-alpine
ARG PYTHON_IMAGE=swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/python:3.12-slim

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

COPY pyproject.toml README.md ./
COPY src ./src
COPY configs ./configs
COPY data ./data
COPY docs ./docs
COPY labeling ./labeling
COPY experiments ./experiments
COPY scripts ./scripts
COPY --from=frontend /app/frontend/dist ./frontend/dist

RUN pip install --no-cache-dir .

EXPOSE 8080

CMD ["uvicorn", "vision_model_lab.api:app", "--host", "0.0.0.0", "--port", "8080"]
