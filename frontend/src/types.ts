export type Health = {
  status: string;
  version: string;
  workspace: string;
  storage_backend?: string;
  storage_uri?: string;
  auth_required?: boolean;
  pipeline_workers?: number;
  external_shell_commands_allowed?: boolean;
};

export type PackageIssue = {
  severity: "error" | "warning" | string;
  code: string;
  message: string;
  path?: string;
};

export type PackageValidation = {
  package_dir: string;
  ok: boolean;
  model_file?: string | null;
  model_card?: string | null;
  labels_file?: string | null;
  examples_dir?: string | null;
  sha256?: string | null;
  onnx_checked: boolean;
  ort_checked: boolean;
  issues: PackageIssue[];
};

export type PackageValidationRecord = {
  id: number;
  package_dir: string;
  model_file?: string | null;
  ok: boolean;
  sha256?: string | null;
  created_at: string;
  report: PackageValidation;
};

export type ExperimentRecord = {
  id: string;
  task: string;
  dataset: string;
  model: string;
  status: string;
  package?: string | null;
  metrics?: Record<string, unknown>;
};

export type ManifestValidation = {
  path: string;
  ok: boolean;
  total_rows: number;
  split_counts: Record<string, number>;
  issues: Array<{
    code: string;
    message: string;
    line?: number | null;
    field?: string | null;
  }>;
};

export type ContractValidation = {
  path: string;
  ok: boolean;
  issues: Array<{
    code: string;
    message: string;
    path?: string;
  }>;
};

export type AdapterInfo = {
  name: string;
  task: string;
  description: string;
};

export type PipelineRunReport = {
  status: string;
  config?: string;
  training?: Record<string, unknown>;
  export?: Record<string, unknown>;
  evaluation?: {
    metrics?: Record<string, number>;
    [key: string]: unknown;
  };
  package?: {
    artifact_name?: string;
    validation?: PackageValidation;
    [key: string]: unknown;
  };
  cancelled_stage?: string | null;
  cancelled_reason?: string | null;
  artifacts?: PipelineArtifact[];
  [key: string]: unknown;
};

export type PipelineRunRecord = {
  id?: number;
  config_path?: string;
  status: string;
  created_at?: string;
  report: PipelineRunReport;
};


export type PipelineJobLog = {
  id: number;
  job_id: number;
  stream: string;
  message: string;
  detail: Record<string, unknown>;
  created_at: string;
};

export type PipelineArtifact = {
  id: number;
  job_id?: number | null;
  run_id?: number | null;
  name: string;
  kind: string;
  path?: string | null;
  uri?: string | null;
  size?: number | null;
  created_at: string;
};

export type PipelineJobRecord = {
  id: number;
  config_path: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled" | "cancellation_requested" | string;
  request: {
    config_path?: string;
    package?: boolean;
    output_root?: string;
    persist?: boolean;
    [key: string]: unknown;
  };
  result?: PipelineRunReport | null;
  error?: string | null;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  cancelled_at?: string | null;
  updated_at: string;
  logs?: PipelineJobLog[];
  artifacts?: PipelineArtifact[];
};
export type AuditEvent = {
  id: number;
  actor: string;
  action: string;
  target: string;
  detail: Record<string, unknown>;
  created_at: string;
};

export type ErrorAnalysis = {
  path: string;
  total: number;
  by_type: Record<string, number>;
  cases: Array<Record<string, unknown>>;
};

export type DatasetVersion = {
  id: number;
  dataset_id: string;
  name: string;
  version: string;
  task: string;
  manifest_path: string;
  split_counts: Record<string, number>;
  labels: string[];
  status: string;
  created_at: string;
  updated_at: string;
};

export type ModelRegistryEntry = {
  id: number;
  model_id: string;
  package_dir: string;
  artifact_name: string;
  version: string;
  task: string;
  metrics: Record<string, number>;
  stage: string;
  created_at: string;
  updated_at: string;
};

export type ReleaseApproval = {
  id: number;
  model_id: string;
  recommendation: string;
  status: string;
  decision: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type DeploymentRollout = {
  id: number;
  model_id: string;
  environment: string;
  strategy: string;
  status: string;
  traffic_percent: number;
  rollback_target?: string | null;
  created_at: string;
  updated_at: string;
};
