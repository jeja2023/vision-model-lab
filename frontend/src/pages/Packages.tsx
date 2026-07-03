import { Play, Search } from "lucide-react";
import { useState } from "react";
import { validatePackage } from "../api";
import { StatusBadge } from "../components/StatusBadge";
import type { PackageValidation } from "../types";
import { zhIssue } from "../i18n";

type PackagesProps = {
  packages: PackageValidation[];
  onRefresh: () => void;
};

const packageDirectoryOptions = [
  { label: "默认模型仓库", value: "shared-models" },
  { label: "自定义目录", value: "custom" }
] as const;

export function Packages({ packages, onRefresh }: PackagesProps) {
  const [packageDir, setPackageDir] = useState("shared-models");
  const [packageDirMode, setPackageDirMode] = useState<(typeof packageDirectoryOptions)[number]["value"]>("shared-models");
  const [modelId, setModelId] = useState("");
  const [strictHash, setStrictHash] = useState(true);
  const [strictExamples, setStrictExamples] = useState(true);
  const [strictOnnx, setStrictOnnx] = useState(false);
  const [message, setMessage] = useState("");

  async function runValidation() {
    setMessage("校验中");
    await validatePackage({
      package_dir: packageDir,
      model_id: modelId || undefined,
      strict_hash: strictHash,
      strict_examples: strictExamples,
      strict_onnx: strictOnnx
    });
    setMessage("已完成");
    onRefresh();
  }

  return (
    <div className="page-grid">
      <section className="panel">
        <div className="panel-header">
          <h1>模型包校验</h1>
          <button className="primary-button" onClick={runValidation} title="执行校验">
            <Play size={17} />
            <span>执行</span>
          </button>
        </div>
        <div className="form-grid">
          <label>
            <span>目录</span>
            <select
              value={packageDirMode}
              onChange={(event) => {
                const nextMode = event.target.value as (typeof packageDirectoryOptions)[number]["value"];
                setPackageDirMode(nextMode);
                if (nextMode !== "custom") {
                  setPackageDir(nextMode);
                }
              }}
            >
              {packageDirectoryOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          {packageDirMode === "custom" ? (
            <label>
              <span>自定义目录</span>
              <input value={packageDir} onChange={(event) => setPackageDir(event.target.value)} />
            </label>
          ) : null}
          <label>
            <span>模型文件</span>
            <input value={modelId} onChange={(event) => setModelId(event.target.value)} placeholder="可选" />
          </label>
          <label className="check-row">
            <input type="checkbox" checked={strictHash} onChange={(event) => setStrictHash(event.target.checked)} />
            <span>文件哈希</span>
          </label>
          <label className="check-row">
            <input type="checkbox" checked={strictExamples} onChange={(event) => setStrictExamples(event.target.checked)} />
            <span>样例</span>
          </label>
          <label className="check-row">
            <input type="checkbox" checked={strictOnnx} onChange={(event) => setStrictOnnx(event.target.checked)} />
            <span>模型格式</span>
          </label>
        </div>
        {message ? <p className="inline-message">{message}</p> : null}
      </section>

      <section className="panel">
        <div className="panel-header">
          <h1>扫描结果</h1>
          <button className="icon-button" onClick={onRefresh} title="扫描">
            <Search size={18} />
          </button>
        </div>
        <div className="table">
          <div className="table-row table-head">
            <span>模型</span>
            <span>状态</span>
            <span>问题</span>
          </div>
          {packages.map((item) => (
            <div className="table-row" key={item.model_file ?? item.package_dir}>
              <span className="mono">{item.model_file ?? item.package_dir}</span>
              <StatusBadge ok={item.ok} />
              <span>{item.issues.length ? zhIssue(item.issues[0].code) : "无"}</span>
            </div>
          ))}
          {!packages.length ? <div className="empty-row">暂无模型包</div> : null}
        </div>
      </section>
    </div>
  );
}
