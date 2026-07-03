import { FileSearch } from "lucide-react";
import { useState } from "react";
import { validateContract, validateManifest } from "../api";
import { StatusBadge } from "../components/StatusBadge";
import type { ContractValidation, ManifestValidation } from "../types";
import { zhContractKind, zhIssue, zhIssueDetail, zhSplit } from "../i18n";

const manifestOptions = [
  { label: "示例训练清单", value: "data/manifests/example_train_v1.jsonl" },
  { label: "自定义清单", value: "custom" }
] as const;

const contractTemplates: Record<"models-fragment" | "release-decision", string> = {
  "models-fragment": "configs/export/models.fragment.template.yml",
  "release-decision": "configs/export/release-decision.template.yml"
};

export function DataLabeling() {
  const [manifestMode, setManifestMode] = useState<(typeof manifestOptions)[number]["value"]>("data/manifests/example_train_v1.jsonl");
  const [manifestPath, setManifestPath] = useState<string>(manifestOptions[0].value);
  const [result, setResult] = useState<ManifestValidation | null>(null);
  const [contractKind, setContractKind] = useState<"models-fragment" | "release-decision">("models-fragment");
  const [contractPath, setContractPath] = useState<string>(contractTemplates["models-fragment"]);
  const [customContractPath, setCustomContractPath] = useState(false);
  const [contractResult, setContractResult] = useState<ContractValidation | null>(null);

  async function submit() {
    const response = await validateManifest(manifestPath);
    setResult(response.manifest);
  }

  async function submitContract() {
    const response = await validateContract(contractKind, contractPath);
    setContractResult(response.contract);
  }

  return (
    <div className="page-grid">
      <section className="panel">
        <div className="panel-header">
          <h1>数据清单</h1>
          <button className="primary-button" onClick={submit} title="校验">
            <FileSearch size={17} />
            <span>校验</span>
          </button>
        </div>
        <div className="form-grid single">
          <label>
            <span>清单</span>
            <select
              value={manifestMode}
              onChange={(event) => {
                const nextMode = event.target.value as (typeof manifestOptions)[number]["value"];
                setManifestMode(nextMode);
                if (nextMode !== "custom") {
                  setManifestPath(nextMode);
                }
              }}
            >
              {manifestOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          {manifestMode === "custom" ? (
            <label>
              <span>自定义路径</span>
              <input value={manifestPath} onChange={(event) => setManifestPath(event.target.value)} />
            </label>
          ) : null}
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h1>交付契约</h1>
          <button className="primary-button" onClick={submitContract} title="校验">
            <FileSearch size={17} />
            <span>校验</span>
          </button>
        </div>
        <div className="form-grid">
          <label>
            <span>类型</span>
            <select
              value={contractKind}
              onChange={(event) => {
                const nextKind = event.target.value as "models-fragment" | "release-decision";
                setContractKind(nextKind);
                if (!customContractPath) {
                  setContractPath(contractTemplates[nextKind]);
                }
              }}
            >
              <option value="models-fragment">{zhContractKind("models-fragment")}</option>
              <option value="release-decision">{zhContractKind("release-decision")}</option>
            </select>
          </label>
          <label>
            <span>模板</span>
            <select
              value={customContractPath ? "custom" : "template"}
              onChange={(event) => {
                const useCustom = event.target.value === "custom";
                setCustomContractPath(useCustom);
                if (!useCustom) {
                  setContractPath(contractTemplates[contractKind]);
                }
              }}
            >
              <option value="template">默认模板</option>
              <option value="custom">自定义路径</option>
            </select>
          </label>
          {customContractPath ? (
            <label>
              <span>自定义路径</span>
              <input value={contractPath} onChange={(event) => setContractPath(event.target.value)} />
            </label>
          ) : null}
        </div>
      </section>

      <section className="panel">
        <h1>结果</h1>
        {result ? (
          <>
            <div className="summary-line">
              <StatusBadge ok={result.ok} />
              <span>{result.total_rows} 行</span>
              <span>{Object.entries(result.split_counts).map(([key, value]) => `${zhSplit(key)}:${value}`).join(" · ")}</span>
            </div>
            <div className="issue-list">
              {result.issues.map((issue) => (
                <div className="issue" key={`${issue.code}-${issue.line}-${issue.field}`}>
                  <strong>{zhIssue(issue.code)}</strong>
                  <span>{zhIssueDetail(issue)}</span>
                </div>
              ))}
            </div>
          </>
        ) : (
          <div className="empty-row">暂无结果</div>
        )}
      </section>

      <section className="panel">
        <h1>契约结果</h1>
        {contractResult ? (
          <>
            <div className="summary-line">
              <StatusBadge ok={contractResult.ok} />
              <span className="mono">{contractResult.path}</span>
            </div>
            <div className="issue-list">
              {contractResult.issues.map((issue) => (
                <div className="issue" key={`${issue.code}-${issue.path}`}>
                  <strong>{zhIssue(issue.code)}</strong>
                  <span>{zhIssueDetail(issue)}</span>
                </div>
              ))}
            </div>
          </>
        ) : (
          <div className="empty-row">暂无结果</div>
        )}
      </section>
    </div>
  );
}
