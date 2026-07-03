# Vision Model Lab 0.4.0 发布说明

发布日期：2026-07-03

## 发布主题

`0.4.0` 补齐 0.3.0 后仍未完成的扩展路线：任务日志与产物索引、MLOps 基础 API、S3/MinIO、PostgreSQL、Alembic 迁移、校验深度、前端运行详情和生产框架 adapter 入口。

## 主要能力

- 异步流水线 job 现在记录阶段日志，并索引 ONNX、导出报告和模型包产物。
- 管理台流水线页新增运行详情，展示阶段日志、错误、产物链接、取消和重试状态。
- 元数据层新增数据集版本库、模型注册表、发布审批和灰度/回滚记录。
- 对象存储支持 `local`、`s3`、`minio` 三类 backend；S3/MinIO 通过 `vision-model-lab[s3]` 启用。
- 元数据存储支持 SQLite 默认模式和 PostgreSQL 可选模式；PostgreSQL 通过 `vision-model-lab[postgres]` 启用。
- 新增 Alembic 迁移脚本，部署环境可使用 `vision-model-lab[migrations]` 执行正式迁移。
- 新增 `ultralytics_yolo`、`torchreid`、`torchvision_classifier`、`segmentation_framework` adapter 入口。

## API 增量

- `GET /api/pipelines/jobs/{job_id}/logs`
- `GET /api/pipelines/jobs/{job_id}/artifacts`
- `GET|POST /api/datasets/versions`
- `GET|POST /api/models/registry`
- `GET|POST /api/releases/approvals`
- `GET|POST /api/deployments/rollouts`

## 环境变量

- `VMLAB_STORAGE_BACKEND=local|s3|minio`
- `VMLAB_STORAGE_URI=artifacts/object-store|s3://bucket/prefix|minio://bucket/prefix`
- `VMLAB_S3_ENDPOINT_URL`：MinIO 或兼容 S3 endpoint。
- `VMLAB_S3_REGION`：S3 区域。
- `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` 或 `VMLAB_S3_ACCESS_KEY_ID` / `VMLAB_S3_SECRET_ACCESS_KEY`。
- `VMLAB_METADATA_DB=artifacts/vision_model_lab.sqlite3|postgresql://user:pass@host/db`。

## 迁移

轻量初始化：

```powershell
vmlab storage migrate
```

Alembic：

```powershell
python -m pip install -e ".[migrations]"
$env:VMLAB_METADATA_DB="postgresql://user:pass@host:5432/vision_model_lab"
alembic upgrade head
```

## 验证结果

- `.venv\Scripts\python.exe -m pytest`：37 passed。
- `npm run build`：通过。
- `.venv\Scripts\python.exe -m pip check` 和 `python -m pip check`：通过。
- `npm audit --omit dev`：0 vulnerabilities。
- `.venv\Scripts\python.exe scripts\acceptance_check.py`：通过。
- `docker build -t vision-model-lab:0.4.0 .`：通过。
- Docker 镜像 smoke test：输出 `0.4.0 Vision Model Lab`。
- `.venv\Scripts\python.exe -m pip install -e ".[dev]"`：安装为 `vision-model-lab==0.4.0`。

## 升级注意

- 默认安装不包含 `boto3`、`psycopg`、`alembic`、`SQLAlchemy`；只有使用对应 backend 时才需要安装 extra。
- 生产框架 adapter 不内置重型训练框架，部署侧需提供外部训练、导出、评估 argv 命令。
- 多实例部署建议使用 PostgreSQL 和 S3/MinIO，SQLite/local store 继续适合单机开发和离线验收。




