"use client";
import { useRef, useState } from "react";
import axios from "axios";
import { useQuery } from "@tanstack/react-query";
import { api, errorMessage } from "@/services/api";
import { useHealth } from "@/hooks/use-health";
import { useInvestigation } from "@/hooks/use-investigation";
import { useProgress } from "@/hooks/use-progress";
import { DiagnosisCard } from "@/components/diagnosis-card";
import type { Cluster, Investigation, Progress, User } from "@/types/investigation";
const stages = [["pods", "Checking Pods"], ["logs", "Reading Logs"], ["events", "Analyzing Events"],
  ["deployments", "Inspecting Deployments"], ["network", "Checking Networking"], ["ai", "AI Reasoning"]];
const pending = () => Object.fromEntries(stages.map(([key]) => [key, "pending"])) as Progress;

export function Dashboard({user, onLogout}: {user: User; onLogout: () => void}) {
  const health = useHealth();
  const investigation = useInvestigation();
  const [chosenContext, setChosenContext] = useState("");
  const clusters = useQuery({queryKey: ["clusters", user.id], queryFn: async () => {
    const {data} = await api.get<{clusters: Cluster[]}>("/clusters");
    if (!Array.isArray(data.clusters)) throw new Error("Cluster list was invalid.");
    return data.clusters;
  }, retry: false});
  const selectedContext = chosenContext || clusters.data?.find(row => row.current)?.context || clusters.data?.[0]?.context || "";
  const [selected, setSelected] = useState<Investigation | null>(null);
  const [warning, setWarning] = useState("");
  const activeId = useRef<string | null>(null);
  const history = useQuery({queryKey: ["history", user.id], queryFn: async () => {
    const {data} = await api.get<{investigations: Investigation[]}>("/investigations");
    if (!Array.isArray(data.investigations)) throw new Error("History response was invalid");
    return data.investigations;
  }, retry: false});
  async function recover() {
    const id = activeId.current;
    if (!id) return;
    try {
      const {data} = await api.get<Investigation>(`/investigations/${id}`);
      setSelected(old => !old || old.id === id && data.revision >= old.revision ? data : old);
      if (data.status !== "running") {activeId.current = null; void history.refetch();}
    } catch { /* The run may not have been inserted yet; POST still delivers its result. */ }
  }
  const connection = useProgress(user.id, row => {
    if (row.id === activeId.current) {
      setSelected(old => old && old.id === row.id && old.revision <= row.revision ? {...old, ...row} : old);
      if (row.status !== "running") void recover();
    }
  }, () => {void recover(); void history.refetch();});
  async function start() {
    setWarning("");
    if (!clusters.data?.some(row => row.context === selectedContext)) {setWarning("Select an available cluster first."); return;}
    const id = crypto.randomUUID();
    activeId.current = id;
    setSelected({id, created_at: new Date().toISOString(), namespace: "All namespaces", cluster_context: selectedContext, status: "running", progress: pending(), revision: -1});
    try {
      const result = await investigation.mutateAsync({id, context: selectedContext});
      setSelected(old => old?.id === id ? {...old, status: result.run_status, diagnosis: result.diagnosis ?? undefined,
        summary: result.summary, ai_error: result.ai.error, root_cause: result.diagnosis?.root_cause, confidence: result.diagnosis?.confidence} : old);
      // Recover final per-stage status from durable state, including events missed on reconnect.
      await recover();
      if (!result.history_saved) setWarning("The result is available, but some history or progress writes failed. Check InsForge before relying on saved history.");
    } catch (err) {
      setWarning(errorMessage(err));
      await recover();
      // A failed POST may have stopped before inserting history. Do not show a false running state.
      const uncertain = axios.isAxiosError(err) && ["ECONNABORTED", "ETIMEDOUT", "ERR_NETWORK"].includes(err.code || "");
      if (!uncertain) {
        setSelected(old => old?.id === id ? {...old, status: old.status === "running" ? "error" : old.status} : old);
        activeId.current = null;
      }
    } finally {void history.refetch();}
  }
  const ready = health.data?.status === "healthy";
  return <main className="dashboard">
    <header className="header"><div><p className="eyebrow">On-demand diagnostics</p><h1>AI Kubernetes Agent</h1></div>
      <div className="account"><span>{user.email}</span><button className="secondary" onClick={onLogout} disabled={investigation.isPending}>Sign out</button></div></header>
    <section className="panel" aria-labelledby="cluster-title">
      <div className="section-heading"><h2 id="cluster-title">Kubernetes clusters</h2><button className="secondary" disabled={investigation.isPending} onClick={() => void clusters.refetch()}>Refresh clusters</button></div>
      <p className="muted">Contexts from the kubeconfig mounted into the backend. Select the cluster to investigate. A listed context does not guarantee network access.</p>
      {clusters.isPending ? <p>Loading clusters…</p> : clusters.isError ? <p className="notice" role="alert">{errorMessage(clusters.error)}</p> : !clusters.data?.length ? <p className="notice">No clusters found. Export your kubeconfig and check the backend mount.</p> :
      <div className="cluster-list" role="group" aria-label="Select Kubernetes context">{clusters.data.map(row => <button key={row.context} className={`cluster-option ${selectedContext === row.context ? "chosen" : ""}`} aria-pressed={selectedContext === row.context} disabled={investigation.isPending} onClick={() => setChosenContext(row.context)}>
        <strong>{row.cluster}</strong><span>{row.context}</span><small>{row.current ? "Default context · " : ""}Investigation scope: all namespaces</small>
      </button>)}</div>}
    </section>
    <section className="panel intro"><div><h2>Troubleshoot Kubernetes with AI</h2><p>Collect evidence, understand failures, and review suggested fixes.</p>
      <p className="muted">System status: {health.isPending ? "Checking…" : ready ? "Ready" : "Backend unavailable"}</p></div>
      <button className="primary" onClick={() => void start()} disabled={!ready || investigation.isPending || clusters.isError || clusters.isFetching || !clusters.data?.some(row => row.context === selectedContext)}>{investigation.isPending ? "Investigating Kubernetes Cluster…" : "Investigate Cluster"}</button></section>
    {warning && <p className="notice" role="alert">{warning}</p>}
    {selected && <section className="panel" aria-labelledby="progress-title"><div className="section-heading"><h2 id="progress-title">Investigation status</h2><span className="badge">{selected.status}</span></div>
      <p><strong>Cluster context:</strong> {selected.cluster_context || "Not recorded (older investigation)"}</p>
      <p className="muted">{connection}</p><ol className="steps" aria-live="polite">{stages.map(([key, label]) => {
        const state = selected.progress[key] || "pending";
        return <li key={key}><span className={`step-dot ${state}`} aria-hidden="true">{state === "completed" ? "✓" : state === "error" ? "!" : state === "running" ? "…" : "·"}</span><span>{label}</span><span className="muted">{state}</span></li>;
      })}</ol><p className="muted">A completed step means collection finished, not that the resource is healthy.</p>
      {selected.status === "running" && !investigation.isPending && <p className="notice">This run has not reported completion. Refresh history to check it; a backend restart can leave a run interrupted.</p>}
    </section>}
    {selected?.summary && <p className="notice" role="status">{selected.summary.message}</p>}
    {selected?.ai_error && <p className="notice" role="alert">Diagnosis unavailable: {selected.ai_error}</p>}
    {selected?.diagnosis && <DiagnosisCard diagnosis={selected.diagnosis} context={selected.cluster_context}/>}
    {investigation.data && selected?.id === investigation.data.investigation_id && <details className="panel"><summary>Collected Kubernetes evidence</summary><pre>{JSON.stringify(investigation.data.investigation, null, 2)}</pre></details>}
    <section className="panel"><div className="section-heading"><h2>Recent investigations</h2><button className="secondary" onClick={() => {void history.refetch(); void recover();}}>Refresh history</button></div>
      {history.isPending ? <p>Loading history…</p> : history.isError ? <p role="alert">{errorMessage(history.error)}</p> : !history.data?.length ? <p className="muted">No investigations yet. Start your first check above.</p> :
      <div className="table-wrap"><table><thead><tr><th>Timestamp</th><th>Root cause / observation</th><th>Cluster context</th><th>Namespace</th><th>Confidence</th><th>Status</th><th>Details</th></tr></thead>
        <tbody>{history.data.map(row => <tr key={row.id}><td>{new Date(row.created_at).toLocaleString()}</td><td>{row.root_cause || "No diagnosis available"}</td><td>{row.cluster_context || "Not recorded"}</td><td>{row.namespace}</td><td>{row.confidence == null ? "—" : `${row.confidence}%`}</td><td>{row.status}</td><td><button className="text-button" disabled={investigation.isPending} onClick={() => {setWarning(""); setSelected(row); activeId.current = row.status === "running" ? row.id : null;}}>View</button></td></tr>)}</tbody></table></div>}
    </section>
  </main>;
}
