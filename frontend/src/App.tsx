import { useCallback, useEffect, useState } from "react";
import { errorMessage, getHealth, listExperiments, listPackageValidations, listPipelineRuns, scanPackages } from "./api";
import { Shell, type ViewKey } from "./components/Shell";
import { DataLabeling } from "./pages/DataLabeling";
import { Experiments } from "./pages/Experiments";
import { Overview } from "./pages/Overview";
import { Packages } from "./pages/Packages";
import { Pipeline } from "./pages/Pipeline";
import type { ExperimentRecord, Health, PackageValidation, PackageValidationRecord, PipelineRunRecord } from "./types";

function dedupeExperiments(records: ExperimentRecord[], index: ExperimentRecord[]): ExperimentRecord[] {
  // DB 记录优先，index.yml 仅补充 DB 中不存在的实验，避免同 id 重复渲染。
  const merged = new Map<string, ExperimentRecord>();
  for (const record of index) {
    merged.set(record.id, record);
  }
  for (const record of records) {
    merged.set(record.id, record);
  }
  return Array.from(merged.values());
}

export function App() {
  const [activeView, setActiveView] = useState<ViewKey>("overview");
  const [health, setHealth] = useState<Health>();
  const [packages, setPackages] = useState<PackageValidation[]>([]);
  const [validations, setValidations] = useState<PackageValidationRecord[]>([]);
  const [experiments, setExperiments] = useState<ExperimentRecord[]>([]);
  const [pipelineRuns, setPipelineRuns] = useState<PipelineRunRecord[]>([]);
  const [apiStatus, setApiStatus] = useState("接口连接中");

  const refresh = useCallback(async () => {
    // allSettled：单个端点失败不影响其他数据更新。
    const [healthResult, packageResult, validationResult, experimentResult, pipelineResult] = await Promise.allSettled([
      getHealth(),
      scanPackages(),
      listPackageValidations(),
      listExperiments(),
      listPipelineRuns()
    ]);
    if (healthResult.status === "fulfilled") {
      setHealth(healthResult.value);
      setApiStatus("接口在线");
    } else {
      setApiStatus(errorMessage(healthResult.reason));
    }
    if (packageResult.status === "fulfilled") {
      setPackages(packageResult.value.packages);
    }
    if (validationResult.status === "fulfilled") {
      setValidations(validationResult.value.validations);
    }
    if (experimentResult.status === "fulfilled") {
      setExperiments(dedupeExperiments(experimentResult.value.experiments, experimentResult.value.index));
    }
    if (pipelineResult.status === "fulfilled") {
      setPipelineRuns(pipelineResult.value.runs);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <Shell activeView={activeView} onViewChange={setActiveView} onRefresh={refresh} apiStatus={apiStatus}>
      {activeView === "overview" ? (
        <Overview health={health} packages={packages} validations={validations} experiments={experiments} pipelineRuns={pipelineRuns} />
      ) : null}
      {activeView === "packages" ? <Packages packages={packages} onRefresh={refresh} /> : null}
      {activeView === "pipeline" ? <Pipeline runs={pipelineRuns} onRefresh={refresh} /> : null}
      {activeView === "experiments" ? <Experiments experiments={experiments} onRefresh={refresh} /> : null}
      {activeView === "data" ? <DataLabeling /> : null}
    </Shell>
  );
}
