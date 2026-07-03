import { useCallback, useEffect, useState } from "react";
import { getHealth, listExperiments, listPackageValidations, listPipelineRuns, scanPackages } from "./api";
import { Shell, type ViewKey } from "./components/Shell";
import { DataLabeling } from "./pages/DataLabeling";
import { Experiments } from "./pages/Experiments";
import { Overview } from "./pages/Overview";
import { Packages } from "./pages/Packages";
import { Pipeline } from "./pages/Pipeline";
import type { ExperimentRecord, Health, PackageValidation, PackageValidationRecord, PipelineRunRecord } from "./types";

export function App() {
  const [activeView, setActiveView] = useState<ViewKey>("overview");
  const [health, setHealth] = useState<Health>();
  const [packages, setPackages] = useState<PackageValidation[]>([]);
  const [validations, setValidations] = useState<PackageValidationRecord[]>([]);
  const [experiments, setExperiments] = useState<ExperimentRecord[]>([]);
  const [pipelineRuns, setPipelineRuns] = useState<PipelineRunRecord[]>([]);
  const [apiStatus, setApiStatus] = useState("接口连接中");

  const refresh = useCallback(async () => {
    try {
      const [healthResponse, packageResponse, validationResponse, experimentResponse, pipelineResponse] = await Promise.all([
        getHealth(),
        scanPackages(),
        listPackageValidations(),
        listExperiments(),
        listPipelineRuns()
      ]);
      setHealth(healthResponse);
      setPackages(packageResponse.packages);
      setValidations(validationResponse.validations);
      setExperiments([...experimentResponse.experiments, ...experimentResponse.index]);
      setPipelineRuns(pipelineResponse.runs);
      setApiStatus("接口在线");
    } catch (error) {
      setApiStatus(error instanceof Error && error.message.startsWith("请求失败") ? error.message : "接口异常");
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
