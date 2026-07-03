# 数据目录

此目录只保存轻量索引和划分文件。原始图片、视频、权重和大型数据集应放在 NAS、MinIO、S3 或其他制品存储中。

推荐分层：

```text
datasets/
  raw/
  labeled/
  curated/
  evaluation/
  manifests/
```

Git 中只提交：

- manifest JSONL。
- split 定义。
- 数据集配置。
- 质检报告。

