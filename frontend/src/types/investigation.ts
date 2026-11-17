export type Progress = Record<string, "pending" | "running" | "completed" | "error">;
export type Diagnosis = {
  root_cause: string; explanation: string; fix: string;
  kubectl_commands?: string[]; kubectl_command?: string;
  confidence: number; confidence_reasoning?: string;
  prevention_recommendation?: string; missing_evidence?: string[];
};
export type Investigation = {
  id: string; created_at: string; completed_at?: string; namespace: string;
  status: "running" | "completed" | "partial" | "error";
  cluster_context?: string; cluster_name?: string; summary?: CollectionSummary;
  root_cause?: string; confidence?: number; diagnosis?: Diagnosis;
  ai_error?: string; progress: Progress; revision: number;
};
export type InvestigationResponse = {
  investigation_id: string; run_status: Investigation["status"];
  cluster: Cluster; summary: CollectionSummary;
  history_saved: boolean; diagnosis: Diagnosis | null;
  ai: {status: string; error?: string}; investigation: Record<string, unknown>;
};
export type User = {id: string; email: string};

export type Cluster = {context: string; cluster: string; namespace: string; current: boolean};
export type CollectionSummary = {state: "incomplete" | "findings" | "no_findings"; message: string; failed_checks: string[]};
