"use client";
import { Activity, ArrowRight, Box, CheckCircle2, Clock3, Database, FileCheck2, GitBranch, ShieldCheck, Sparkles, TriangleAlert, Truck } from "lucide-react";
import type { Assessment, Proposal, Records, Run } from "@/lib/contracts";

type Props = { assessment: Assessment | null; proposals: Proposal[]; records: Records | null; runs: Run[]; running: boolean; onPlan: () => void; onProposals: () => void; onApprovals: () => void; onHistory: () => void; onRuns: () => void; };
export default function WorkflowDashboard({ assessment, proposals, records, runs, running, onPlan, onProposals, onApprovals, onHistory, onRuns }: Props) {
  const issues = assessment?.impact?.issues ?? [];
  const pending = proposals.filter(p => p.status === "PROPOSED");
  const approved = proposals.filter(p => p.status === "APPROVED");
  const executed = records?.items.filter(r => r.execution?.status === "SUCCEEDED") ?? [];
  const assessed = assessment?.impact?.status === "ASSESSED";
  const stages = [
    { Icon: TriangleAlert, title: "Disruption", sub: "Product & plant selected", state: "Selected", action: onPlan },
    { Icon: Database, title: "Supply check", sub: "Stock, shipments & deadlines", state: running ? "Running" : !assessment ? "Not assessed" : issues.length ? "Needs evidence" : assessment.impact.status.replaceAll("_", " "), action: onPlan },
    { Icon: GitBranch, title: "Recovery plan", sub: "Transfer or purchase", state: proposals.length ? `${proposals.length} loaded` : assessment?.status === "OPTIONS_READY" ? "Options ready" : "Awaiting plan", action: onProposals },
    { Icon: ShieldCheck, title: "Human approval", sub: "Manager reviews evidence", state: approved.length ? "Approved record" : pending.length ? "Review needed" : "Awaiting proposal", action: onApprovals },
    { Icon: FileCheck2, title: "Mock execution", sub: "Separate confirmed action", state: executed.length ? "Success recorded" : "No success loaded", action: onHistory },
  ];
  return <div className="command-grid">
    <div className="command-main">
      <section className="panel pipeline-panel">
        <div className="card-heading"><div><h2><GitBranch size={19} className="heading-icon" /> Recovery workflow</h2><p className="subtitle">Follow the decision from disruption to approved action.</p></div><span className="flow-chip">FLOW VIEW</span></div>
        <div className="pipeline-stages">{stages.map(({ Icon, title, sub, state, action }, i) => <button key={title} onClick={action} className={`pipeline-stage stage-${i}`}><span className="stage-number">0{i + 1}</span><span className="stage-symbol"><Icon size={27} /></span><strong>{title}</strong><span className="stage-sub">{sub}</span><span className="stage-state">{state}</span>{i < 4 && <ArrowRight className="stage-connector" size={18} />}</button>)}</div>
        <div className="pipeline-note"><Database size={15} /> Stored evidence → deterministic checks → human decision <span>Selected incident · loaded records</span></div>
        <div className="pipeline-action"><p>{running ? "Supply analysis is running." : issues.length ? "Update the flagged evidence, then check supply again." : !assessment ? "Start by checking whether available supply can meet demand." : "Review the assessment and choose the next action below."}</p><button className="button primary" onClick={onPlan}><Activity size={16} /> Check supply <ArrowRight size={15} /></button></div>
      </section>
      <section className="panel recent-panel"><div className="card-heading"><div><h2><Clock3 size={18} className="heading-icon" /> Recent planning runs</h2><p className="subtitle">Saved assessments for this incident</p></div><button className="text-button" onClick={onRuns}>View all <ArrowRight size={14} /></button></div>
        {runs.length ? <div className="table-scroll"><table className="run-table"><thead><tr><th>Run</th><th>Started</th><th>Status</th><th>Details</th></tr></thead><tbody>{runs.slice(0, 4).map(r => <tr key={r.id}><td><span className="run-name"><Activity size={15} /> {r.id.slice(0,8)}</span></td><td>{new Date(r.created_at).toLocaleString()}</td><td><span className={`badge ${r.status === "COMPLETED" ? "green" : "blue"}`}>{r.status.replaceAll("_", " ")}</span></td><td><button className="text-button" onClick={onRuns}>View runs</button></td></tr>)}</tbody></table></div> : <div className="command-empty"><Activity size={25} /><p>No saved runs yet. Check supply to create your first assessment.</p></div>}
      </section>
    </div>
    <aside className="command-side">
      <section className="panel alerts-panel"><div className="card-heading"><h2><TriangleAlert size={18} className="heading-icon" /> Attention needed</h2><span className="alert-count">{issues.length + pending.length}</span></div>
        {!assessment && <div className="insight-item"><Box size={18} /><div><strong>Supply not assessed</strong><p>Run a supply check to discover shortages and evidence issues.</p></div></div>}
        {issues.slice(0,3).map((issue,i) => <div className="insight-item warning" key={i}><Clock3 size={18} /><div><strong>{issue.code.replaceAll("_", " ")}</strong><p>{issue.message}</p></div></div>)}
        {issues.length > 3 && <p className="tiny">{issues.length - 3} more issues in the supply assessment below.</p>}
        {pending.length > 0 && <button className="insight-item insight-button" onClick={onApprovals}><ShieldCheck size={18} /><div><strong>{pending.length} proposal(s) awaiting review</strong><p>Open approvals to inspect validity and evidence.</p></div><ArrowRight size={14} /></button>}
        {assessed && !issues.length && <div className="insight-item success"><CheckCircle2 size={18} /><div><strong>Evidence passed at assessment time</strong><p>Approval and execution revalidate the records.</p></div></div>}
      </section>
      <section className="panel command-ai"><div className="card-heading"><h2><Sparkles size={19} /> Recovery brief</h2><span className="flow-chip">{assessment?.ai_explanation ? "AI ASSISTED" : "ASSESSMENT"}</span></div><p>{assessment?.ai_explanation?.summary || assessment?.explanation || "Select your warehouse and delivery estimates. OpsFlow will check supply coverage and explain the available recovery options."}</p><div className="brief-footer"><ShieldCheck size={15} /> Advisory only · manager approval required</div></section>
      <div className="mock-note"><Truck size={20} /><div><strong>Mock ERP environment</strong><p>Orders are simulated. No physical delivery is recorded.</p></div></div>
    </aside>
  </div>;
}
