import { Save } from "lucide-react";
import { useState } from "react";
import { saveExperiment } from "../api";
import type { ExperimentRecord } from "../types";
import { zhField, zhStatus } from "../i18n";

type ExperimentsProps = {
  experiments: ExperimentRecord[];
  onRefresh: () => void;
};

export function Experiments({ experiments, onRefresh }: ExperimentsProps) {
  const [record, setRecord] = useState<ExperimentRecord>({
    id: "行人检测实验_20260603_001",
    task: "目标检测",
    dataset: "行人检测数据集_v1.0.0",
    model: "小型目标检测基线",
    status: "计划中",
    package: ""
  });

  async function submit() {
    await saveExperiment(record);
    onRefresh();
  }

  return (
    <div className="page-grid">
      <section className="panel">
        <div className="panel-header">
          <h1>实验记录</h1>
          <button className="primary-button" onClick={submit} title="保存">
            <Save size={17} />
            <span>保存</span>
          </button>
        </div>
        <div className="form-grid">
          {(["id", "task", "dataset", "model", "status", "package"] as const).map((field) => (
            <label key={field}>
              <span>{zhField(field)}</span>
              <input
                value={(record[field] as string | null | undefined) ?? ""}
                onChange={(event) => setRecord({ ...record, [field]: event.target.value })}
              />
            </label>
          ))}
        </div>
      </section>

      <section className="panel">
        <h1>实验列表</h1>
        <div className="table">
          <div className="table-row table-head">
            <span>编号</span>
            <span>任务</span>
            <span>状态</span>
          </div>
          {experiments.map((item) => (
            <div className="table-row" key={item.id}>
              <span className="mono">{item.id}</span>
              <span>{zhStatus(item.task)}</span>
              <span>{zhStatus(item.status)}</span>
            </div>
          ))}
          {!experiments.length ? <div className="empty-row">暂无实验</div> : null}
        </div>
      </section>
    </div>
  );
}
