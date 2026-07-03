# 架构设计

## 分层

```text
frontend/
  React + TypeScript 管理台
  流水线、任务详情、模型包、实验、数据与契约入口

FastAPI management API
  包扫描、校验、manifest 校验、实验记录、异步流水线、任务日志、产物索引、上传、误差分析、MLOps 记录、审计、模板入口

Python core package
  命名规则、模型卡、模型包、数据 manifest、ONNX 检查、任务适配器、对象存储 provider、元数据存储

Storage
  SQLite 默认，PostgreSQL 可选
  local / S3 / MinIO 对象存储
  shared-models / artifacts / data manifests
```

## 边界

算法侧负责：

- 数据 manifest、数据集版本和质量记录。
- 标注规范和质检报告。
- 训练、评估、导出入口。
- YOLO 检测、ReID、分类、分割本地基线适配器；生产环境可通过 `ultralytics_yolo`、`torchreid`、`torchvision_classifier`、`segmentation_framework` adapter 配置外部 argv 命令接入真实框架。
- ONNX 文件和标准模型包。
- 模型卡、labels、样例、expected 输出。
- 模型注册、发布审批和灰度/回滚记录。

推理服务负责：

- 在线 API。
- 模型缓存、灰度、回滚执行。
- 鉴权、监控、业务适配。
- 基于 `models.yml` 的运行时配置。

## API

- `GET /health`
- `GET /api/packages/scan`
- `POST /api/packages/validate`
- `GET /api/package-validations`
- `POST /api/manifests/validate`
- `POST /api/contracts/validate`
- `GET /api/experiments`
- `POST /api/experiments`
- `GET /api/templates`
- `GET /api/adapters`
- `POST /api/pipelines/run`
- `GET /api/pipelines/runs`
- `GET /api/pipelines/jobs`
- `GET /api/pipelines/jobs/{job_id}`
- `GET /api/pipelines/jobs/{job_id}/logs`
- `GET /api/pipelines/jobs/{job_id}/artifacts`
- `POST /api/pipelines/jobs/{job_id}/cancel`
- `POST /api/pipelines/jobs/{job_id}/retry`
- `POST /api/packages/create`
- `POST /api/uploads`
- `POST /api/error-analysis`
- `GET /api/audit-events`
- `GET|POST /api/datasets/versions`
- `GET|POST /api/models/registry`
- `GET|POST /api/releases/approvals`
- `GET|POST /api/deployments/rollouts`

## 扩展边界

- SQLite/local store 适合单机开发和离线验收；多实例生产部署建议切 PostgreSQL 和 S3/MinIO。
- 当前 worker 是进程内线程池；如果需要跨机器调度、优先级队列或 GPU 资源编排，可继续接 RQ、Celery、Kubernetes Job 或内部任务平台。
- 生产 adapter 只提供平台入口和安全执行约束，具体训练框架、模型代码、GPU 调度和依赖镜像由部署环境提供。
