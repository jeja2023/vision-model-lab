# 更新日志

本文件记录 `vision-model-lab` 的主要功能变更、交付状态和验证结果。格式参考 Keep a Changelog，版本号遵循语义化版本。

## [0.4.0] - 2026-07-03

### 新增

- 新增流水线 job 阶段日志和产物索引表：`pipeline_job_logs`、`pipeline_artifacts`，job 详情接口会返回日志和产物。
- 新增数据集版本库、模型注册表、发布审批和灰度/回滚记录表及 API：`/api/datasets/versions`、`/api/models/registry`、`/api/releases/approvals`、`/api/deployments/rollouts`。
- 新增 S3/MinIO 对象存储 provider，`VMLAB_STORAGE_BACKEND=s3|minio` 时通过可选 `boto3` 上传到 bucket/prefix。
- 新增 PostgreSQL 元数据存储入口，`VMLAB_METADATA_DB=postgresql://...` 时通过可选 `psycopg` 使用外部数据库。
- 新增 Alembic 迁移目录和 `vmlab storage migrate`，支持正式迁移流程和轻量运行时初始化。
- 新增生产框架 adapter 入口：`ultralytics_yolo`、`torchreid`、`torchvision_classifier`、`segmentation_framework`，可通过 argv 外部命令接入真实训练框架。
- 新增前端任务运行详情面板，展示阶段日志、失败原因、产物链接和任务状态。
- 新增 `docs/RELEASE_0.4.0.md`，汇总本次 MLOps、存储、校验和前端增强。

### 变更

- 版本号统一升级到 `0.4.0`，同步 Python 包、运行时 `__version__`、前端包版本和可编辑安装元数据。
- 异步流水线运行会记录 training/export/evaluation/package 阶段事件，并在同步/异步运行后索引 ONNX、导出报告和模型包产物。
- 数据集注册将 `labels` 作为版本元数据，另以 `allowed_labels` 控制 manifest label 白名单，避免把检测标注 URI 误判为类别值。
- `pyproject.toml` 增加 `s3`、`postgres`、`migrations` 可选依赖组，默认安装仍保持轻量。

### 校验增强

- manifest 校验支持最小 split 样本数和可选 label 白名单。
- 模型包 expected output 校验支持 detections/predictions/embedding/mask 结构检查，并校验 expected label 必须存在于 labels.txt。
- 模型卡支持 `metric_thresholds`，可要求指标存在、为数值并达到门槛。
- 新增 S3 key 逃逸、MLOps 元数据、job 日志/产物、manifest 门槛和 expected label 一致性的回归测试。

### 验证

- `.venv\Scripts\python.exe -m pytest` 通过：37 passed。
- `npm run build` 通过，前端包版本为 `0.4.0`。
- `.venv\Scripts\python.exe -m pip check` 和 `python -m pip check` 均通过。
- `npm audit --omit dev` 通过：0 vulnerabilities。
- `.venv\Scripts\python.exe scripts\acceptance_check.py` 通过。
- `docker build -t vision-model-lab:0.4.0 .` 通过。
- `docker run --rm vision-model-lab:0.4.0 python -c "from vision_model_lab import __version__; from vision_model_lab.api import app; print(__version__, app.title)"` 输出 `0.4.0 Vision Model Lab`。
- `.venv\Scripts\python.exe -m pip install -e ".[dev]"` 已更新为 `vision-model-lab==0.4.0`。

### 已知事项

- S3/MinIO、PostgreSQL 和 Alembic 依赖为可选 extra；默认开发环境不会安装这些外部服务依赖。
- 生产框架 adapter 采用命令入口，具体 Ultralytics/TorchReID/TorchVision/MMSegmentation 环境仍需由部署侧安装和配置 argv 命令。

## [0.3.0] - 2026-07-03

### 新增

- 新增流水线异步任务能力：`POST /api/pipelines/run` 支持 `{"async": true}`，并提供 `/api/pipelines/jobs` 的列表、详情、取消和重试接口。
- 新增 `pipeline_jobs` 元数据表，用于记录 queued、running、completed、failed、cancelled 和 cancellation_requested 等任务状态。
- 新增前端流水线任务视图，支持异步启动、轮询任务状态、查看最新结果、取消和重试。
- 新增对象存储抽象与本地实现，上传文件会写入受限本地对象存储根目录，禁止对象 key 逃逸。
- 新增上传大小限制、流水线 worker 数、外部命令超时、外部命令日志长度、对象存储根路径和 shell 命令开关等环境变量。
- 新增项目专用 `.venv` 开发环境流程，`dev` 依赖补充 `pytest-asyncio>=0.25`，用于隔离全局机器学习工具链。
- 新增 `docs/RELEASE_0.3.0.md`，汇总本次安全、任务、存储、验证和环境修复内容。

### 变更

- 版本号统一升级到 `0.3.0`，同步 Python 包、运行时 `__version__` 和前端包版本。
- Dockerfile 默认基础镜像切换为当前网络可访问的华为云 Docker Hub 镜像源；仍保留 `NODE_IMAGE`、`PYTHON_IMAGE` build args，可按部署环境覆盖为官方镜像或企业镜像。
- SQLite 连接策略改为 `MEMORY -> WAL -> DELETE -> OFF` 的 journal mode 逐级回退，并保留 busy timeout、foreign key 和进程内线程锁，避免受限 Windows 环境下产生 WAL 探针残留或初始化失败。
- API 响应模型统一使用 `ApiModel`，规避 Pydantic `model_id` protected namespace warning。
- `/health` 增加存储 URI、pipeline worker、外部 shell 命令开关等运行时信息。
- 前端 API 客户端支持异步流水线返回 `run` 或 `job` 两种结果，并补充任务管理接口类型。
- 测试临时目录统一由 `tests/conftest.py` 的 `workspace_tmp_path` 管理，避免依赖系统 Temp 或 pytest basetemp 权限。
- 验证文档从“直接使用全局 Python”更新为优先使用项目 `.venv`，同时保留全局 Python 验证说明。

### 安全加固

- 前端静态文件 fallback 增加路径边界检查，防止编码后的 `..` 读取工作区或系统文件。
- API 工作区路径解析统一限制在 `VMLAB_WORKSPACE` 内，模型包 `model_id` 禁止绝对路径和 `..` 逃逸。
- 本地对象存储对 key 做绝对路径和父目录逃逸校验，写入前确认目标仍在存储根目录内。
- 外部训练/导出/评估命令默认只允许 argv list；字符串 shell 命令默认禁用，需显式设置 `VMLAB_ALLOW_SHELL_COMMANDS=true` 才能兼容旧配置。
- 外部命令增加 cwd 边界校验、执行超时和日志截断，导出产物路径也会校验在工作区内。
- 上传接口增加 `VMLAB_MAX_UPLOAD_BYTES` 限制，超限时返回 413 并删除部分写入文件。

### 校验增强

- 模型包校验新增 `package.model_outside_package`，拒绝包目录外模型文件。
- 模型包样例校验新增图片签名检查和 expected JSON 根结构检查。
- 模型卡校验新增输入 shape 正整数、layout、dtype、deployment max batch size 和 limitations 列表检查。
- 数据 manifest 校验新增图片扩展名、非空字段、label 类型和 tags 列表检查。
- 交付契约校验新增 input/output/artifact 对象类型、sidecar 引用非空、上线判定列表去重和非空检查。
- 流水线合成样例图片改为写入 JPEG 签名占位内容，避免严格样例校验失败。

### 环境修复

- 创建项目 `.venv` 并安装 `.[dev]`，项目环境 `pip check` 已通过。
- 修复全局 Python 环境冲突：对齐 `protobuf`、`sympy`、`aiosqlite`、`torchaudio`、`torchvision`，并清理损坏的 `~elery` 残留；全局 `python -m pip check` 已通过。
- 清理 Windows 用户代理残留的 `ProxyServer=127.0.0.1:10808` 和 PAC 配置，原值备份到 `artifacts/windows-proxy-before-20260703184731.txt`。
- Docker 默认构建已验证通过，镜像 `vision-model-lab:0.3.0` 可正常导入 `vision_model_lab.api`。

### 验证

- `.venv\Scripts\python.exe -m pip check` 通过。
- `python -m pip check` 通过。
- `.venv\Scripts\python.exe -m pytest` 通过：32 passed。
- `python -m pytest` 通过：32 passed。
- `npm run build` 通过。
- `npm audit --omit dev` 通过：0 vulnerabilities。
- `python scripts\acceptance_check.py` 通过。
- `docker build -t vision-model-lab:0.3.0 .` 通过。
- `docker run --rm vision-model-lab:0.3.0 python -c "from vision_model_lab.api import app; print(app.title)"` 输出 `Vision Model Lab`。

### 已知事项

- 完整 `npm audit` 仍会报告 Vite/esbuild 开发依赖 advisory；生产检查 `npm audit --omit dev` 为 0，最终 Docker 后端镜像不携带 Node 开发依赖。
- 当前目录不是 Git 仓库，无法提供 git tag 或提交记录；版本号已在项目文件中启用。

## [0.2.0] - 2026-06-09

### 新增

- 新增任务适配器注册表，训练、导出和评估脚本不再只支持 `reference_identity`。
- 新增 YOLO 检测、ReID、分类、分割本地基线适配器，均可运行训练记录、ONNX 导出和评估报告流程，并支持执行外部训练、导出、评估命令。
- 新增流水线脚本 `scripts/run_pipeline.py`，支持一键训练、导出、评估和创建标准模型包。
- 新增真实可校验的 `shared-models/cross_camera_tracking/person_detector_yolov8n_v1.0.0_fp32.onnx` 示例模型包。
- 新增 FastAPI 流水线、模型包创建、上传、误差分析、审计事件和适配器接口。
- 新增管理台“流水线”视图，支持启动流水线、创建模型包、上传制品、查看指标、误差分析和审计记录。
- 新增 SQLite 流水线运行表和审计事件表，新增本地对象存储入口与可选 Bearer Token 鉴权。

### 变更

- `configs/experiments/detection_yolo_baseline.yml` 绑定可执行 `detection_yolo_baseline` 适配器。
- `python scripts/validate_model_package.py shared-models --allow-missing-sidecars --allow-missing-examples` 支持递归扫描模型仓库根目录。
- 文档更新为当前能力：内置本地基线适配器，真实生产训练框架仍通过后续适配器或外部命令接入。

### 验证

- `python -m pytest` 通过，当时结果为 23 个测试通过。
- `npm run build` 通过。
- `python scripts/run_pipeline.py --config configs/experiments/detection_yolo_baseline.yml --package` 通过。
- `python scripts/validate_model_package.py shared-models --allow-missing-sidecars --allow-missing-examples` 通过。

### 仍需生产化

- 内置 YOLO/ReID/分类/分割适配器是可运行本地基线；真实训练可先通过外部命令接入，长期仍建议接入 Ultralytics、TorchReID、具体分类/分割框架或内部训练平台的专用适配器。
- 分布式任务队列、PostgreSQL、MinIO/S3 原生后端、统一身份认证和细粒度权限仍需按部署环境接入。

## [0.1.0] - 2026-06-08

### 新增

- 搭建视觉模型研发与交付仓库骨架，覆盖数据清单、标注规范、实验配置、模型评估、ONNX 导出和标准模型包交付。
- 新增 Python 核心包 `vision_model_lab`，提供模型命名解析、模型卡校验、模型包创建与校验、数据清单校验、交付契约校验和工具函数。
- 新增 FastAPI 管理接口，包含健康检查、模型包扫描、模型包校验、数据清单校验、交付契约校验、实验记录和模板入口。
- 新增 React + TypeScript 管理台，提供概览、模型包、实验和数据标注视图。
- 新增 SQLite 元数据存储，用于记录实验信息和模型包校验历史。
- 新增参考身份模型流程，支持本地训练、导出和评估的最小闭环验证。
- 新增 Dockerfile、docker-compose、运行态检查脚本和离线验收脚本，便于本地和容器化验证。
- 新增生产准备、架构、交付标准和运维文档。

### 变更

- 管理台可见文案统一调整为中文，包括导航、标题、按钮、状态、表头、默认选项和校验结果。
- 默认模型目录、示例数据清单和交付契约模板改为中文选项展示，内部仍使用原路径和契约枚举调用接口。
- OpenAPI 标题和接口描述调整为中文，并和管理台品牌保持一致。
- 运行态检查脚本兼容中文品牌标题，同时保留旧英文标题的兼容判断。
- 管理台网络异常提示收敛为中文，避免直接展示浏览器英文错误。

### 修复

- 修复数据清单和交付契约校验结果中直接透出英文错误消息的问题，改为按错误码展示中文问题和中文处理建议。
- 修复实验页残留英文 `ID` 表头和英文示例值的问题。
- 修复前端默认路径直接暴露在初始界面的问题。

### 验证

- `npm run build` 通过。
- `python -m pytest` 通过，当时结果为 19 个测试通过。
- `python scripts/runtime_check.py --base-url http://127.0.0.1:8080` 通过。
- `python scripts/acceptance_check.py --runtime-base-url http://127.0.0.1:8080` 通过。
- 本地管理台 `http://127.0.0.1:8080/` 已完成浏览器实测，标题和主要可见文案为中文。
- OpenAPI `http://127.0.0.1:8080/docs` 对应的接口标题已更新为 `视觉模型研发平台`。

### 已知事项

- 元数据存储当时使用 SQLite；生产多实例部署前建议迁移到 PostgreSQL 或内部统一元数据服务。
- 大模型文件和数据集仍建议放在 NAS、MinIO、S3 或本地挂载目录，不进入 Git 仓库。
- CLI 文档当时仍以开发者命令使用为主，后续如面向非开发用户开放，可继续补中文帮助文本。





