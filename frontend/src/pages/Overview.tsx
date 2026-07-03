import { CheckCircle2, Clock, PackageCheck, ShieldCheck } from "lucide-react";
import type { ExperimentRecord, Health, PackageValidation, PackageValidationRecord, PipelineRunRecord } from "../types";
import { zhStatus } from "../i18n";

type OverviewProps = {
  health?: Health;
  packages: PackageValidation[];
  validations: PackageValidationRecord[];
  experiments: ExperimentRecord[];
  pipelineRuns: PipelineRunRecord[];
};

export function Overview({ health, packages, validations, experiments, pipelineRuns }: OverviewProps) {
  const validPackages = packages.filter((item) => item.ok).length;
  const lastValidation = validations[0];
  const lastRun = pipelineRuns[0];
  return (
    <div className="page-grid">
      <section className="metric-strip">
        <div className="metric">
          <PackageCheck size={20} />
          <span>模型包</span>
          <strong>{packages.length}</strong>
        </div>
        <div className="metric">
          <ShieldCheck size={20} />
          <span>通过</span>
          <strong>{validPackages}</strong>
        </div>
        <div className="metric">
          <Clock size={20} />
          <span>流水线</span>
          <strong>{pipelineRuns.length}</strong>
        </div>
        <div className="metric">
          <CheckCircle2 size={20} />
          <span>接口</span>
          <strong>{zhStatus(health?.status)}</strong>
        </div>
      </section>

      <section className="panel">
        <h1>工作区</h1>
        <dl className="detail-list">
          <div>
            <dt>版本</dt>
            <dd>{health?.version ?? "-"}</dd>
          </div>
          <div>
            <dt>路径</dt>
            <dd>{health?.workspace ?? "-"}</dd>
          </div>
          <div>
            <dt>最近校验</dt>
            <dd>{lastValidation ? `${lastValidation.package_dir} · ${lastValidation.ok ? "通过" : "失败"}` : "-"}</dd>
          </div>
          <div>
            <dt>最近流水线</dt>
            <dd>{lastRun ? `${lastRun.config_path ?? lastRun.report.config ?? "-"} · ${zhStatus(lastRun.status)}` : "-"}</dd>
          </div>
          <div>
            <dt>存储</dt>
            <dd>{health?.storage_backend ?? "-"}</dd>
          </div>
        </dl>
      </section>
    </div>
  );
}
