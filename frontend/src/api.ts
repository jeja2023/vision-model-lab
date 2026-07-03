import type {
  ExperimentRecord,
  Health,
  AdapterInfo,
  AuditEvent,
  ContractValidation,
  ErrorAnalysis,
  ManifestValidation,
  PackageValidation,
  PackageValidationRecord,
  PipelineArtifact,
  PipelineJobLog,
  PipelineJobRecord,
  PipelineRunRecord,
  DatasetVersion,
  DeploymentRollout,
  ModelRegistryEntry,
  ReleaseApproval
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";
const API_TOKEN = import.meta.env.VITE_API_TOKEN ?? "";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(API_TOKEN ? { Authorization: `Bearer ${API_TOKEN}` } : {}),
      ...(options?.headers ?? {})
    },
    ...options
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function getHealth() {
  return request<Health>("/health");
}

export function scanPackages(root = "shared-models") {
  return request<{ root: string; packages: PackageValidation[] }>(`/api/packages/scan?root=${encodeURIComponent(root)}`);
}

export function validatePackage(payload: {
  package_dir: string;
  model_id?: string;
  strict_hash: boolean;
  strict_examples: boolean;
  strict_onnx: boolean;
}) {
  return request<{ validation: PackageValidation | PackageValidationRecord }>("/api/packages/validate", {
    method: "POST",
    body: JSON.stringify({ ...payload, persist: true })
  });
}

export function listPackageValidations() {
  return request<{ validations: PackageValidationRecord[] }>("/api/package-validations");
}

export function validateManifest(path: string) {
  return request<{ manifest: ManifestValidation }>("/api/manifests/validate", {
    method: "POST",
    body: JSON.stringify({ path })
  });
}

export function validateContract(kind: "models-fragment" | "release-decision", path: string) {
  return request<{ contract: ContractValidation }>("/api/contracts/validate", {
    method: "POST",
    body: JSON.stringify({ kind, path })
  });
}

export function listExperiments() {
  return request<{ experiments: ExperimentRecord[]; index: ExperimentRecord[] }>("/api/experiments");
}

export function saveExperiment(record: ExperimentRecord) {
  return request<{ experiment: ExperimentRecord }>("/api/experiments", {
    method: "POST",
    body: JSON.stringify(record)
  });
}

export function listAdapters() {
  return request<{ adapters: AdapterInfo[] }>("/api/adapters");
}

export function runPipeline(payload: { config_path: string; package: boolean; output_root?: string; async_run?: boolean }) {
  return request<{ run?: PipelineRunRecord; job?: PipelineJobRecord }>("/api/pipelines/run", {
    method: "POST",
    body: JSON.stringify({
      config_path: payload.config_path,
      package: payload.package,
      output_root: payload.output_root ?? "shared-models",
      persist: true,
      async: payload.async_run ?? false
    })
  });
}

export function listPipelineRuns() {
  return request<{ runs: PipelineRunRecord[] }>("/api/pipelines/runs");
}

export function listPipelineJobs() {
  return request<{ jobs: PipelineJobRecord[] }>("/api/pipelines/jobs");
}

export function getPipelineJob(jobId: number) {
  return request<{ job: PipelineJobRecord }>(`/api/pipelines/jobs/${jobId}`);
}

export function cancelPipelineJob(jobId: number) {
  return request<{ job: PipelineJobRecord }>(`/api/pipelines/jobs/${jobId}/cancel`, { method: "POST" });
}

export function listPipelineJobLogs(jobId: number) {
  return request<{ logs: PipelineJobLog[] }>(`/api/pipelines/jobs/${jobId}/logs`);
}

export function listPipelineJobArtifacts(jobId: number) {
  return request<{ artifacts: PipelineArtifact[] }>(`/api/pipelines/jobs/${jobId}/artifacts`);
}

export function retryPipelineJob(jobId: number) {
  return request<{ job: PipelineJobRecord }>(`/api/pipelines/jobs/${jobId}/retry`, { method: "POST" });
}

export function createPackage(payload: { config_path: string; onnx_path?: string; project_name?: string; output_root?: string }) {
  return request<{ package: { artifact_name: string; validation: PackageValidation } }>("/api/packages/create", {
    method: "POST",
    body: JSON.stringify({ ...payload, output_root: payload.output_root ?? "shared-models", overwrite: true })
  });
}

export function uploadArtifact(file: File, targetDir = "artifacts/uploads") {
  const form = new FormData();
  form.append("file", file);
  return fetch(`${API_BASE}/api/uploads?target_dir=${encodeURIComponent(targetDir)}`, {
    method: "POST",
    headers: API_TOKEN ? { Authorization: `Bearer ${API_TOKEN}` } : undefined,
    body: form
  }).then(async (response) => {
    if (!response.ok) {
      throw new Error(await response.text());
    }
    return response.json() as Promise<{ upload: { path: string } }>;
  });
}

export function analyzeErrors(path: string) {
  return request<{ analysis: ErrorAnalysis }>("/api/error-analysis", {
    method: "POST",
    body: JSON.stringify({ path })
  });
}

export function listAuditEvents() {
  return request<{ events: AuditEvent[] }>("/api/audit-events");
}
export function listDatasetVersions() {
  return request<{ datasets: DatasetVersion[] }>("/api/datasets/versions");
}

export function listModelRegistry() {
  return request<{ models: ModelRegistryEntry[] }>("/api/models/registry");
}

export function listReleaseApprovals() {
  return request<{ approvals: ReleaseApproval[] }>("/api/releases/approvals");
}

export function listDeploymentRollouts() {
  return request<{ rollouts: DeploymentRollout[] }>("/api/deployments/rollouts");
}
