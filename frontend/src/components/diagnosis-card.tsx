import type { Diagnosis } from "@/types/investigation";
export function DiagnosisCard({diagnosis, context}: {diagnosis: Diagnosis; context?: string}) {
  const commands = diagnosis.kubectl_commands ?? (diagnosis.kubectl_command ? [diagnosis.kubectl_command] : []);
  return <section className="panel" aria-labelledby="diagnosis-title">
    <div className="section-heading"><h2 id="diagnosis-title">Diagnosis</h2><span className="badge">Confidence estimate: {diagnosis.confidence}%</span></div>
    <h3>Root cause / observation</h3><p>{diagnosis.root_cause}</p>
    <h3>Explanation</h3><p>{diagnosis.explanation}</p>
    <h3>Suggested fix</h3><p>{diagnosis.fix}</p>
    <h3>Suggested kubectl commands</h3>
    {context && <p className="notice">These suggestions refer to context <strong>{context}</strong>. Before running a command manually, explicitly add <code>--context {JSON.stringify(context)}</code> after <code>kubectl</code> and verify its target and namespace.</p>}
    {commands.length ? commands.map((command, i) => <pre key={i}><code>{command}</code></pre>) : <p>No command recommended.</p>}
    <p className="muted">Suggestions only. This application does not execute fixes.</p>
    {diagnosis.prevention_recommendation && <><h3>Prevention</h3><p>{diagnosis.prevention_recommendation}</p></>}
    {diagnosis.missing_evidence?.length ? <details><summary>Missing evidence and limitations</summary><ul>{diagnosis.missing_evidence.map((item, i) => <li key={i}>{item}</li>)}</ul></details> : null}
    <p className="muted">Confidence is an uncalibrated estimate, not a measured probability. {diagnosis.confidence_reasoning}</p>
  </section>;
}
