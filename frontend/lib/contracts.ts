import type { Impact } from "./api";
export type Actor = { subject: string; role: string };
export type Product = { id: string; sku: string; name: string };
export type Location = { id: string; code: string; name: string; type: string };
export type Incident = {
  id: string;
  title: string;
  description: string | null;
  status: string;
  sku: string;
  plant_name: string;
  plant_code: string;
  product_id: string;
  plant_id: string;
  created_at: string;
};
export type Page<T> = { items: T[]; next_offset: number | null };
export type Proposal = {
  id: string;
  incident_id: string;
  version: number;
  action_type: string;
  status: string;
  assessed_at: string;
  expires_at: string;
  plan_snapshot: Record<string, unknown>;
  evidence_snapshot: Record<string, unknown>;
};
export type Execution = {
  id: string;
  proposal_id: string;
  status: string;
  failure_reason: string | null;
  result: {
    mode?: string;
    external_ref?: string;
    quantity?: string;
    order_status?: string;
    physical_receipt_recorded?: boolean;
  };
};
export type OptionPlan = {
  arrival_at: string;
  transfer_qty?: string;
  purchase_qty?: string;
  transport_cost?: string;
  total_cost?: string;
  currency?: string;
  warehouse_name?: string;
  allocations?: unknown[];
};
export type Assessment = {
  status: string;
  assessed_at: string;
  explanation: string;
  impact: Impact;
  transfer: null | {
    status: string;
    plan: OptionPlan | null;
    issues: { message: string }[];
  };
  purchase: null | {
    status: string;
    options: {
      offer_id: string;
      supplier_name: string;
      status: string;
      currency: string;
      reasons: string[];
      plan: OptionPlan | null;
    }[];
  };
  ai_explanation?: { summary: string };
  limitations: string[];
};
export type Run = {
  id: string;
  status: string;
  created_at: string;
  result: Assessment | null;
  error_code?: string | null;
  steps?: { name: string; status: string }[];
};
export type HistoryItem = {
  proposal: {
    id: string;
    version: number;
    action_type: string;
    current_status: string;
    created_at: string;
  };
  decision: null | {
    decision: string;
    manager_subject: string;
    reason: string;
    decided_at: string;
  };
  resume_job: null | { current_status: string };
  execution:
    | null
    | (Execution["result"] & { status: string; failure_reason: string | null });
};
export type Records = {
  items: HistoryItem[];
  next_before_version: number | null;
};
