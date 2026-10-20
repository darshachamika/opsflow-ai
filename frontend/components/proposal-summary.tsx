import { Box, Clock3, ShieldCheck, ShoppingCart, Truck, Wallet } from "lucide-react";
import type { Proposal } from "@/lib/contracts";
const obj = (v: unknown): Record<string, unknown> => v !== null && typeof v === "object" && !Array.isArray(v) ? v as Record<string, unknown> : {};
const label = (v: unknown) => typeof v === "string" || typeof v === "number" ? String(v) : "Not recorded";
const qty = (v: unknown) => v !== undefined && v !== null && Number.isFinite(Number(v)) ? Number(v).toLocaleString("en-GB", { maximumFractionDigits: 4 }) : "Not recorded";
export default function ProposalSummary({ proposal, destination }: { proposal: Proposal; destination?: string }) {
 const transfer = proposal.action_type === "WAREHOUSE_TRANSFER";
 const snapshot = proposal.plan_snapshot;
 const evaluation = obj(snapshot.evaluation);
 // A purchase must show the selected option, never another supplier's evaluated plan.
 const option = transfer ? evaluation : obj(snapshot.selected_option);
 const plan = obj(option.plan);
 const parameters = obj(snapshot.parameters);
 const currency = label(plan.currency ?? option.currency ?? parameters.currency);
 const origin = transfer ? label(plan.warehouse_name ?? evaluation.warehouse_name ?? parameters.warehouse_code) : label(option.supplier_name);
 const arrival = typeof plan.arrival_at === "string" && Number.isFinite(Date.parse(plan.arrival_at)) ? new Date(plan.arrival_at).toLocaleString() : "Not recorded";
 const allocations = Array.isArray(plan.allocations) ? plan.allocations.map(obj) : [];
 return <div className="human-proposal">
  <div className="proposal-intro"><span className="proposal-type-icon">{transfer ? <Truck size={25}/> : <ShoppingCart size={25}/>}</span><div><span className="eyebrow-small">PROPOSED RECOVERY · VERSION {proposal.version}</span><h3>{transfer ? "Move stock from a warehouse" : "Purchase stock from a supplier"}</h3><p>{origin} <span>→</span> {destination || "Incident destination"}</p></div></div>
  <div className="proposal-facts">
   <div><Box size={18}/><span>Quantity</span><strong>{qty(transfer ? plan.transfer_qty : plan.purchase_qty)} <small>units</small></strong></div>
   <div><Wallet size={18}/><span>{transfer ? "Transport cost" : "Total purchase cost"}</span><strong>{currency} {qty(transfer ? plan.transport_cost : plan.total_cost)}</strong></div>
   <div><Clock3 size={18}/><span>Expected arrival</span><strong>{arrival}</strong></div>
  </div>
  {!transfer && <div className="cost-breakdown"><span>Items <b>{currency} {qty(plan.items_cost)}</b></span><span>Freight <b>{currency} {qty(plan.freight_cost ?? parameters.freight_cost)}</b></span></div>}
  {allocations.length > 0 && <p className="proposal-context">This plan allocates supply across {allocations.length} demand record{allocations.length === 1 ? "" : "s"}. Review the saved demand coverage before approving.</p>}
  <details className="friendly-evidence"><summary>Demand coverage & validity</summary><p>Assessed: {new Date(proposal.assessed_at).toLocaleString()}</p><p>Valid until: {new Date(proposal.expires_at).toLocaleString()}</p>{allocations.map((a,i) => <div className="allocation-line" key={i}><span>{label(a.source_ref ?? `Demand ${i+1}`)}</span><span>{qty(a.allocated_qty ?? a.transfer_qty ?? a.purchase_qty ?? a.quantity)} units</span></div>)}<p>The backend checks the saved evidence again before approval and execution.</p></details>
  <div className="approval-explainer"><ShieldCheck size={19}/><p><strong>What does approval do?</strong> It authorizes this proposal. Mock execution is a separate action; approving does not place a real order or record a delivery.</p></div>
 </div>;
}
