import { Boxes, Play, RotateCcw, Search, XCircle } from "lucide-react";
import { Fragment, useEffect, useMemo, useState } from "react";
import {
  analyzeErrors,
  cancelPipelineJob,
  createPackage,
  getPipelineJob,
  listAdapters,
  listAuditEvents,
  listPipelineJobs,
  retryPipelineJob,
  runPipeline,
  uploadArtifact
} from "../api";
import { StatusBadge } from "../components/StatusBadge";
import type { AdapterInfo, AuditEvent, ErrorAnalysis, PipelineArtifact, PipelineJobLog, PipelineJobRecord, PipelineRunRecord } from "../types";
import { zhStatus } from "../i18n";

const configOptions = [
  { label: "YOLO ????", value: "configs/experiments/detection_yolo_baseline.yml" },
  { label: "ReID ??", value: "configs/experiments/reid_baseline.yml" },
  { label: "????", value: "configs/experiments/classification_baseline.yml" },
  { label: "????", value: "configs/experiments/segmentation_baseline.yml" }
];

const terminalStatuses = new Set(["completed", "failed", "cancelled"]);
const cancellableStatuses = new Set(["queued", "running"]);

type PipelineProps = {
  runs: PipelineRunRecord[];
  onRefresh: () => void;
};

function metricsText(run?: PipelineRunRecord) {
  const metrics = run?.report?.evaluation?.metrics;
  if (!metrics) {
    return "-";
  }
  return Object.entries(metrics)
    .map(([key, value]) => `${key}:${value}`)
    .join(" / ");
}

type StatusTone = "ok" | "warn" | "neutral" | "fail";

type JobDetailField = {
  label: string;
  value: string;
  mono?: boolean;
};

function jobStatusTone(status: string): StatusTone {
  if (status === "completed") {
    return "ok";
  }
  if (status === "cancelled") {
    return "neutral";
  }
  if (status === "cancellation_requested" || status === "running" || status === "queued") {
    return "warn";
  }
  return "fail";
}

function pipelineStageLabel(value?: string | null) {
  const map: Record<string, string> = {
    training: "训练",
    export: "导出",
    evaluation: "评估",
    package: "打包"
  };
  return value ? map[value] ?? value : "-";
}

function cancellationReasonLabel(value?: string | null) {
  const map: Record<string, string> = {
    "Cancellation requested before training started": "在训练开始前已请求取消",
    "Cancellation requested after training": "训练完成后已请求取消",
    "Cancellation requested after export": "导出完成后已请求取消",
    "Cancellation requested before package creation": "在打包开始前已请求取消",
    "Training was cancelled": "训练已取消",
    "Export was cancelled": "导出已取消",
    "Evaluation was cancelled": "评估已取消"
  };
  return value ? map[value] ?? value : "-";
}

function jobCancellationNote(job: PipelineJobRecord) {
  if (job.status === "cancellation_requested") {
    return "取消请求已提交，当前任务正在停止。";
  }
  if (job.status === "cancelled") {
    const stage = job.result?.cancelled_stage ? `，终止于${pipelineStageLabel(job.result.cancelled_stage)}阶段` : "";
    return `任务已取消${stage}。`;
  }
  return "";
}

function jobDetailFields(job: PipelineJobRecord): JobDetailField[] {
  const fields: Array<JobDetailField | null> = [
    { label: "任务编号", value: `#${job.id}` },
    { label: "配置路径", value: job.config_path, mono: true },
    { label: "开始时间", value: job.started_at ?? job.created_at },
    { label: "完成时间", value: job.completed_at ?? "-" },
    job.cancelled_at || job.status === "cancelled" ? { label: "取消时间", value: job.cancelled_at ?? "-" } : null,
    job.result?.cancelled_stage ? { label: "取消阶段", value: pipelineStageLabel(job.result.cancelled_stage) } : null,
    job.result?.cancelled_reason ? { label: "取消原因", value: cancellationReasonLabel(job.result.cancelled_reason) } : null,
    { label: "错误", value: job.error ?? "-" }
  ];
  return fields.filter((field): field is JobDetailField => field !== null);
}

function errorMessage(error: unknown) {

  return error instanceof Error ? error.message : "????";
}

function detailSummary(detail: Record<string, unknown>) {
  const value = JSON.stringify(detail);
  return value.length > 180 ? `${value.slice(0, 180)}...` : value;
}

function artifactHref(artifact: PipelineArtifact) {
  return artifact.uri ?? artifact.path ?? "";
}

function logKey(log: PipelineJobLog) {
  return `${log.id}-${log.stream}-${log.created_at}`;
}

export function Pipeline({ runs, onRefresh }: PipelineProps) {
  const [configPath, setConfigPath] = useState(configOptions[0].value);
  const [withPackage, setWithPackage] = useState(true);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [adapters, setAdapters] = useState<AdapterInfo[]>([]);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [jobs, setJobs] = useState<PipelineJobRecord[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null);
  const [selectedJob, setSelectedJob] = useState<PipelineJobRecord | null>(null);
  const [errorPath, setErrorPath] = useState("data/manifests/example_train_v1.jsonl");
  const [analysis, setAnalysis] = useState<ErrorAnalysis | null>(null);
  const latest = runs[0];
  const latestJob = jobs[0];

  async function refreshJobs() {
    const response = await listPipelineJobs();
    setJobs(response.jobs);
  }

  useEffect(() => {
    void Promise.all([listAdapters(), listAuditEvents(), listPipelineJobs()]).then(([adapterResponse, eventResponse, jobResponse]) => {
      setAdapters(adapterResponse.adapters);
      setEvents(eventResponse.events);
      setJobs(jobResponse.jobs);
    });
  }, [runs.length]);

  useEffect(() => {
    if (!selectedJobId && jobs[0]) {
      setSelectedJobId(jobs[0].id);
    }
  }, [jobs, selectedJobId]);

  useEffect(() => {
    if (!selectedJobId) {
      setSelectedJob(null);
      return;
    }
    void getPipelineJob(selectedJobId)
      .then((response) => setSelectedJob(response.job))
      .catch(() => setSelectedJob(null));
  }, [selectedJobId, jobs]);

  useEffect(() => {
    if (!jobs.some((job) => !terminalStatuses.has(job.status))) {
      return;
    }
    const timer = window.setInterval(() => {
      void refreshJobs().then(onRefresh);
    }, 1500);
    return () => window.clearInterval(timer);
  }, [jobs, onRefresh]);

  async function startPipeline() {
    setBusy(true);
    setMessage("?????");
    try {
      const response = await runPipeline({ config_path: configPath, package: withPackage, async_run: true });
      if (response.job) {
        setSelectedJobId(response.job.id);
        setMessage(`?? #${response.job.id} ???`);
      } else {
        setMessage("??????");
      }
      await refreshJobs();
      onRefresh();
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function buildPackage() {
    setBusy(true);
    setMessage("??????");
    try {
      await createPackage({ config_path: configPath });
      setMessage("??????");
      onRefresh();
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function submitUpload(file?: File | null) {
    if (!file) {
      return;
    }
    setBusy(true);
    setMessage("???");
    try {
      await uploadArtifact(file);
      setMessage("?????");
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function inspectErrors() {
    try {
      const response = await analyzeErrors(errorPath);
      setAnalysis(response.analysis);
    } catch (error) {
      setMessage(errorMessage(error));
    }
  }

  async function cancelJob(jobId: number) {
    try {
      await cancelPipelineJob(jobId);
      setSelectedJobId(jobId);
      await refreshJobs();
    } catch (error) {
      setMessage(errorMessage(error));
    }
  }

  async function retryJob(jobId: number) {
    try {
      const response = await retryPipelineJob(jobId);
      setSelectedJobId(response.job.id);
      await refreshJobs();
    } catch (error) {
      setMessage(errorMessage(error));
    }
  }

  const groupedAdapters = useMemo(
    () => adapters.map((adapter) => `${adapter.task}:${adapter.name}`).join(" / "),
    [adapters]
  );
  const selectedJobCancellationNote = selectedJob ? jobCancellationNote(selectedJob) : "";
  const selectedJobDetails = selectedJob ? jobDetailFields(selectedJob) : [];

  return (
    <div className="page-grid">
      <section className="panel">
        <div className="panel-header">
          <h1>??????</h1>
          <button className="primary-button" onClick={startPipeline} title="?????" disabled={busy}>
            <Play size={17} />
            <span>??</span>
          </button>
        </div>
        <div className="form-grid">
          <label>
            <span>??</span>
            <select value={configPath} onChange={(event) => setConfigPath(event.target.value)} disabled={busy}>
              {configOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label className="check-row">
            <input type="checkbox" checked={withPackage} onChange={(event) => setWithPackage(event.target.checked)} disabled={busy} />
            <span>?????</span>
          </label>
        </div>
        <div className="summary-line">
          <span>????{groupedAdapters || "-"}</span>
          {latestJob ? <StatusBadge tone={jobStatusTone(latestJob.status)} label={zhStatus(latestJob.status)} /> : null}
        </div>
        {message ? <p className="inline-message">{message}</p> : null}
      </section>

      <section className="panel">
        <div className="panel-header">
          <h1>?????</h1>
          <button className="primary-button" onClick={buildPackage} title="?????" disabled={busy}>
            <Boxes size={17} />
            <span>??</span>
          </button>
        </div>
        <div className="form-grid single">
          <label>
            <span>????</span>
            <input type="file" onChange={(event) => void submitUpload(event.target.files?.item(0))} disabled={busy} />
          </label>
        </div>
      </section>

      <section className="panel">
        <h1>??</h1>
        <div className="table compact-table">
          <div className="table-row job-row table-head">
            <span>??</span>
            <span>??</span>
            <span>??</span>
            <span>??</span>
          </div>
          {jobs.slice(0, 8).map((job) => (
            <div
              className={`table-row job-row ${selectedJobId === job.id ? "selected-row" : ""}`}
              key={job.id}
              role="button"
              tabIndex={0}
              onClick={() => setSelectedJobId(job.id)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  setSelectedJobId(job.id);
                }
              }}
            >
              <span>#{job.id}</span>
              <span className="mono">{job.config_path}</span>
              <StatusBadge tone={jobStatusTone(job.status)} label={zhStatus(job.status)} />
              <span className="row-actions">
                {cancellableStatuses.has(job.status) ? (
                  <button className="icon-button" onClick={(event) => { event.stopPropagation(); void cancelJob(job.id); }} title="取消任务">
                    <XCircle size={16} />
                  </button>
                ) : null}
                {job.status === "failed" || job.status === "cancelled" ? (
                  <button className="icon-button" onClick={(event) => { event.stopPropagation(); void retryJob(job.id); }} title="重新运行">
                    <RotateCcw size={16} />
                  </button>
                ) : null}
              </span>
            </div>
          ))}
          {!jobs.length ? <div className="empty-row">????</div> : null}
        </div>
      </section>

      <section className="panel wide-panel">
        <div className="panel-header">
          <h1>????</h1>
          {selectedJob ? <StatusBadge tone={jobStatusTone(selectedJob.status)} label={zhStatus(selectedJob.status)} /> : null}
        </div>
        {selectedJob ? (
          <>
                        {selectedJobCancellationNote ? <p className="inline-message">{selectedJobCancellationNote}</p> : null}
            <div className="detail-grid">
              {selectedJobDetails.map((field) => (
                <Fragment key={field.label}>
                  <span>{field.label}</span>
                  <strong className={field.mono ? "mono" : undefined}>{field.value}</strong>
                </Fragment>
              ))}
            </div>
            <div className="detail-columns">
              <div>
                <h2>????</h2>
                <div className="log-list">
                  {(selectedJob.logs ?? []).slice(-8).map((log) => (
                    <div className="log-row" key={logKey(log)}>
                      <span>{log.stream}</span>
                      <strong>{log.message}</strong>
                      <code>{detailSummary(log.detail)}</code>
                    </div>
                  ))}
                  {!(selectedJob.logs ?? []).length ? <div className="empty-row">????</div> : null}
                </div>
              </div>
              <div>
                <h2>??</h2>
                <div className="artifact-list">
                  {(selectedJob.artifacts ?? []).map((artifact) => (
                    <a key={artifact.id} href={artifactHref(artifact)} title={artifact.path ?? artifact.uri ?? artifact.name}>
                      <span>{artifact.kind}</span>
                      <strong>{artifact.name}</strong>
                      <small>{artifact.size ? `${artifact.size} bytes` : "-"}</small>
                    </a>
                  ))}
                  {!(selectedJob.artifacts ?? []).length ? <div className="empty-row">????</div> : null}
                </div>
              </div>
            </div>
          </>
        ) : (
          <div className="empty-row">??????</div>
        )}
      </section>

      <section className="panel">
        <h1>????</h1>
        <div className="summary-line">
          {latest ? <StatusBadge tone={jobStatusTone(latest.status)} label={zhStatus(latest.status)} /> : null}
          <span>{latest?.config_path ?? latest?.report.config ?? "-"}</span>
          <span>{metricsText(latest)}</span>
        </div>
        <div className="table compact-table">
          <div className="table-row table-head">
            <span>??</span>
            <span>??</span>
            <span>??</span>
          </div>
          {runs.map((run) => (
            <div className="table-row" key={`${run.id}-${run.created_at}`}>
              <span className="mono">{run.config_path ?? run.report.config ?? "-"}</span>
              <StatusBadge tone={jobStatusTone(run.status)} label={zhStatus(run.status)} />
              <span>{metricsText(run)}</span>
            </div>
          ))}
          {!runs.length ? <div className="empty-row">???????</div> : null}
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h1>????</h1>
          <button className="icon-button" onClick={inspectErrors} title="??">
            <Search size={18} />
          </button>
        </div>
        <div className="form-grid single">
          <label>
            <span>????</span>
            <input value={errorPath} onChange={(event) => setErrorPath(event.target.value)} />
          </label>
        </div>
        <div className="summary-line">
          <span>???{analysis?.total ?? 0}</span>
          <span>{analysis ? Object.entries(analysis.by_type).map(([key, value]) => `${key}:${value}`).join(" / ") || "???" : "-"}</span>
        </div>
      </section>

      <section className="panel">
        <h1>????</h1>
        <div className="table compact-table">
          <div className="table-row table-head">
            <span>??</span>
            <span>??</span>
            <span>??</span>
          </div>
          {events.slice(0, 6).map((event) => (
            <div className="table-row" key={event.id}>
              <span>{event.action}</span>
              <span className="mono">{event.target}</span>
              <span>{event.created_at}</span>
            </div>
          ))}
          {!events.length ? <div className="empty-row">??????</div> : null}
        </div>
      </section>
    </div>
  );
}
