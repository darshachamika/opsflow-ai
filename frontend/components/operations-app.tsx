"use client";
import {
  useState,
  useEffect,
  useRef,
  type ReactNode,
  type FormEvent,
} from "react";
import {
  Activity,
  ArrowRight,
  Box,
  CheckCircle2,
  ChevronRight,
  ClipboardList,
  Clock3,
  History,
  House,
  Layers3,
  Loader2,
  LogOut,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  ShoppingCart,
  Sparkles,
  TriangleAlert,
  Truck,
  UserCheck,
  Warehouse,
  X,
} from "lucide-react";
import "./sidebar-controls.css";
import ProposalSummary from "./proposal-summary";
import SupplyChart from "./supply-chart";
import WorkflowDashboard from "./workflow-dashboard";
import { request, mutation, ApiError } from "@/lib/client";
import { formatQty } from "@/lib/api";
import type {
  Actor,
  Incident,
  Product,
  Location,
  Page,
  Proposal,
  Assessment,
  Run,
  Execution,
  Records,
} from "@/lib/contracts";

type View =
  | "Overview"
  | "Incidents"
  | "Recovery proposals"
  | "Approvals"
  | "Workflow runs"
  | "Record history";
const nav = [
  { name: "Overview", Icon: House },
  { name: "Incidents", Icon: TriangleAlert },
  { name: "Recovery proposals", Icon: ClipboardList },
  { name: "Approvals", Icon: UserCheck },
  { name: "Workflow runs", Icon: Activity },
  { name: "Record history", Icon: History },
] as const;
const initialInputs = {
  warehouse_code: "",
  transfer_lead_time_hours: 6,
  transport_cost: "18000",
  purchase_freight_cost: "12000",
  currency: "LKR",
};
type Inputs = typeof initialInputs;
const date = (x: string) =>
  new Date(x).toLocaleString("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
  });
function Badge({ value }: { value: string }) {
  return (
    <span
      className={`badge ${["SUCCEEDED", "APPROVED", "ASSESSED", "FULL_COVERAGE", "COMPLETED"].includes(value) ? "green" : ["PROPOSED", "INCOMPLETE", "FAILED", "EXPIRED", "NEEDS_EVIDENCE"].includes(value) ? "amber" : "blue"}`}
    >
      {value.replaceAll("_", " ")}
    </span>
  );
}
function Modal({
  title,
  children,
  close,
}: {
  title: string;
  children: ReactNode;
  close: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    d?.showModal();
    return () => d?.close();
  }, []);
  return (
    <dialog
      ref={ref}
      aria-labelledby="modal-title"
      onCancel={(e) => {
        e.preventDefault();
        close();
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <header>
        <h2 id="modal-title">{title}</h2>
        <button aria-label="Close" className="icon-btn" onClick={close}>
          <X size={20} />
        </button>
      </header>
      <div className="dialog-body">{children}</div>
    </dialog>
  );
}
function Blank({ children }: { children: ReactNode }) {
  return (
    <div className="empty-state">
      <ClipboardList size={29} />
      <p>{children}</p>
    </div>
  );
}
export default function OperationsApp() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  useEffect(() => {
    try { setSidebarCollapsed(localStorage.getItem("opsflow.sidebar.collapsed") === "true"); } catch {}
  }, []);
  function toggleSidebar() {
    setSidebarCollapsed(previous => {
      const next = !previous;
      try { localStorage.setItem("opsflow.sidebar.collapsed", String(next)); } catch {}
      return next;
    });
  }
  const [showIncidentPicker, setShowIncidentPicker] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [runDetail, setRunDetail] = useState<Run | null>(null);
  const [incidentFilter, setIncidentFilter] = useState("ALL");
  const [openingId, setOpeningId] = useState<string | null>(null);
  const [actor, setActor] = useState<Actor | null>(null),
    [starting, setStarting] = useState(true),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const [username, setUsername] = useState(""),
    [password, setPassword] = useState(""),
    [view, setView] = useState<View>("Overview"),
    [mobile, setMobile] = useState(false);
  useEffect(() => {
    if (!mobile) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMobile(false);
        document.getElementById("sidebar-menu-toggle")?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [mobile]);
  const [items, setItems] = useState<Incident[]>([]),
    [next, setNext] = useState<number | null>(null),
    [query, setQuery] = useState(""),
    [activeQuery, setActiveQuery] = useState(""),
    [selected, setSelected] = useState<Incident | null>(null);
  const [warehouses, setWarehouses] = useState<Location[]>([]),
    [inputs, setInputs] = useState<Inputs>(initialInputs),
    [assessment, setAssessment] = useState<Assessment | null>(null),
    [assessedInputs, setAssessedInputs] = useState<Inputs | null>(null);
  const [proposals, setProposals] = useState<Proposal[]>([]),
    [proposalCursor, setProposalCursor] = useState<number | null>(null),
    [records, setRecords] = useState<Records | null>(null),
    [runs, setRuns] = useState<Run[]>([]),
    [runOffset, setRunOffset] = useState(0),
    [runMore, setRunMore] = useState(false),
    [running, setRunning] = useState<string | null>(null);
  const [newIncident, setNewIncident] = useState(false),
    [products, setProducts] = useState<Product[]>([]),
    [plants, setPlants] = useState<Location[]>([]),
    [productQuery, setProductQuery] = useState(""),
    [plantQuery, setPlantQuery] = useState(""),
    [warehouseQuery, setWarehouseQuery] = useState("");
  const [productId, setProductId] = useState(""),
    [plantId, setPlantId] = useState(""),
    [title, setTitle] = useState(""),
    [description, setDescription] = useState("");
  const creation = useRef<{ source_ref: string; detected_at: string } | null>(
    null,
  );
  const [review, setReview] = useState<Proposal | null>(null),
    [reason, setReason] = useState(""),
    [confirmExecution, setConfirmExecution] = useState<Proposal | null>(null),
    [execution, setExecution] = useState<Execution | null>(null);
  const [clock, setClock] = useState(0);
  const generation = useRef(0);
  const manager = actor?.role === "PROCUREMENT_MANAGER";
  const pending = proposals.filter(
    (p) => p.status === "PROPOSED" && Date.parse(p.expires_at) > clock,
  );
  const impact = assessment?.impact;
  const sums = impact?.allocations.reduce(
    (a, x) => ({
      demand: a.demand + Number(x.remaining_demand),
      stock: a.stock + Number(x.stock_allocated_qty),
      inbound: a.inbound + Number(x.inbound_allocated_qty),
      shortage: a.shortage + Number(x.shortage_qty),
    }),
    { demand: 0, stock: 0, inbound: 0, shortage: 0 },
  );
  function clearScope() {
    setAssessment(null);
    setAssessedInputs(null);
    setProposals([]);
    setRecords(null);
    setRuns([]);
    setRunning(null);
    setExecution(null);
    setProposalCursor(null);
    setRunOffset(0);
    setRunMore(false);
  }
  function resetSession() {
    generation.current++;
    setActor(null);
    setSelected(null);
    setItems([]);
    setWarehouses([]);
    setReview(null);
    setConfirmExecution(null);
    setNewIncident(false);
    clearScope();
  }
  function fail(e: unknown) {
    if (e instanceof ApiError && e.status === 401) resetSession();
    setError(
      e instanceof Error
        ? e.message
        : "Something went wrong. Please try again.",
    );
  }
  async function guarded(work: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await work();
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  }
  async function listing(offset = 0, q = activeQuery) {
    const page = await request<Page<Incident>>(
      `/workspace/incidents?offset=${offset}&q=${encodeURIComponent(q)}`,
    );
    setItems((prev) => (offset ? [...prev, ...page.items] : page.items));
    setNext(page.next_offset);
  }
  async function loadWarehouses(q = "") {
    const data = await request<Page<Location>>(
      `/workspace/locations?type=WAREHOUSE&q=${encodeURIComponent(q)}`,
    );
    setWarehouses(data.items);
    setInputs((prev) => ({
      ...prev,
      warehouse_code: prev.warehouse_code,
    }));
  }
  async function boot() {
    await Promise.all([listing(0, ""), loadWarehouses()]);
  }
  useEffect(() => {
    let live = true;
    request<Actor>("/auth/me")
      .then(async (a) => {
        if (!live) return;
        setActor(a);
        await boot();
      })
      .catch((e) => {
        if (live && (!(e instanceof ApiError) || e.status !== 401))
          setError(e.message);
      })
      .finally(() => {
        if (live) setStarting(false);
      });
    return () => {
      live = false;
    };
  }, []);
  useEffect(() => {
    setClock(Date.now());
    const timer = setInterval(() => setClock(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(""), 6000);
    return () => clearTimeout(timer);
  }, [notice]);
  async function scope(id: string) {
    const ticket = ++generation.current;
    const [p, h, r] = await Promise.all([
      request<{ items: Proposal[]; next_before_version: number | null }>(
        `/workspace/incidents/${id}/proposals`,
      ),
      request<Records>(`/incidents/${id}/history`),
      request<{ items: Run[] }>(`/incidents/${id}/runs?limit=20&offset=0`),
    ]);
    if (ticket !== generation.current) return;
    setProposals(p.items);
    setProposalCursor(p.next_before_version);
    setRecords(h);
    setRuns(r.items);
    setRunOffset(0);
    setRunMore(r.items.length === 20);
  }
  async function choose(i: Incident) {
    if (busy) return;
    clearScope();
    setSelected(i);
    setShowIncidentPicker(false);
    setInputs({ ...initialInputs });
    setRunDetail(null);
    await guarded(async () => {
      await scope(i.id);
      const page = await request<{ items: Run[] }>(`/incidents/${i.id}/runs?limit=1&offset=0`);
      if (page.items[0]) {
        const latest = await request<Run & { inputs: Inputs }>(`/runs/${page.items[0].id}`);
        setAssessment(latest.result);
        setAssessedInputs(latest.inputs);
        setInputs(latest.inputs);
      }
    });
  }
  async function refresh() {
    await guarded(async () => {
      await listing();
      if (selected) {
        const latest = await request<Incident>(`/incidents/${selected.id}`);
        setSelected({ ...selected, ...latest });
        await scope(selected.id);
      }
      setNotice(
        "Stored records refreshed. Run Analyze for a fresh assessment.",
      );
    });
  }
  async function login(e: FormEvent) {
    e.preventDefault();
    await guarded(async () => {
      const a = await request<Actor>("/auth/login", {
        subject: username,
        password,
      });
      setActor(a);
      setPassword("");
      await boot();
    });
  }
  async function logout() {
    await guarded(async () => {
      await request("/auth/logout", {});
      resetSession();
      setPassword("");
    });
  }
  useEffect(() => {
    if (!running || !selected) return;
    let stopped = false;
    const id = selected.id;
    const poll = setInterval(async () => {
      try {
        const run = await request<Run>(`/runs/${running}`);
        if (stopped) return;
        if (run.status !== "RUNNING") {
          setRunning(null);
          setAssessment(run.result);
          await scope(id);
          if (run.status === "FAILED")
            setError(
              `Assessment failed: ${run.error_code || "unknown error"}. Refresh evidence and try again.`,
            );
        }
      } catch (e) {
        if (!stopped) {
          setRunning(null);
          fail(e);
        }
      }
    }, 3000);
    return () => {
      stopped = true;
      clearInterval(poll);
    };
  }, [running, selected?.id]);
  function changeInput<K extends keyof Inputs>(key: K, value: Inputs[K]) {
    setInputs((prev) => ({ ...prev, [key]: value }));
    setAssessment(null);
    setAssessedInputs(null);
  }
  async function analyze(e: FormEvent) {
    e.preventDefault();
    if (!selected) return;
    const id = selected.id;
    const copy = { ...inputs };
    await guarded(async () => {
      setAssessment(null);
      const run = await mutation<Run>(`/incidents/${id}/runs`, copy);
      setAssessedInputs(copy);
      setAssessment(run.result);
      setRunning(run.status === "RUNNING" ? run.id : null);
      await scope(id);
      if (run.status === "FAILED")
        throw new Error(`Analysis failed: ${run.error_code}.`);
      setNotice(
        run.status === "RUNNING"
          ? "Analysis is running. Status will update automatically."
          : "Assessment saved. Review the evidence and recovery options.",
      );
    });
  }
  async function propose(type: "transfer" | "purchase", offer?: string) {
    if (!selected || !assessedInputs) return;
    const body =
      type === "transfer"
        ? {
            warehouse_code: assessedInputs.warehouse_code,
            lead_time_hours: assessedInputs.transfer_lead_time_hours,
            fixed_transport_cost: assessedInputs.transport_cost,
            currency: assessedInputs.currency,
          }
        : {
            offer_id: offer,
            freight_cost: assessedInputs.purchase_freight_cost,
            currency: assessedInputs.currency,
          };
    await guarded(async () => {
      await mutation(`/incidents/${selected.id}/proposals/${type}`, body);
      await scope(selected.id);
      setView("Approvals");
      setNotice("Proposal saved. A procurement manager can now review it.");
    });
  }
  async function decide(decision: "APPROVED" | "REJECTED") {
    if (!review || !selected) return;
    await guarded(async () => {
      await mutation(`/proposals/${review.id}/decision`, { decision, reason });
      setReview(null);
      setReason("");
      await scope(selected.id);
      setNotice(
        `Proposal ${decision.toLowerCase()}. ${decision === "APPROVED" ? "Ready for explicit mock execution." : ""}`,
      );
    });
  }
  async function execute() {
    if (!confirmExecution || !selected) return;
    const p = confirmExecution;
    await guarded(async () => {
      try {
        const result = await request<Execution>(
          `/proposals/${p.id}/execute-mock`,
          {},
        );
        setExecution(result);
        setConfirmExecution(null);
        await scope(selected.id);
        setNotice(
          "Mock execution recorded. Physical receipt has not been recorded.",
        );
      } catch (e) {
        if (
          e instanceof ApiError &&
          e.payload &&
          typeof e.payload === "object" &&
          "status" in e.payload
        ) {
          setExecution(e.payload as Execution);
          setConfirmExecution(null);
          await scope(selected.id);
        }
        throw e;
      }
    });
  }
  async function openNew() {
    creation.current = null;
    setTitle("");
    setDescription("");
    setProductId("");
    setPlantId("");
    await guarded(async () => {
      const [p, l] = await Promise.all([
        request<Page<Product>>("/workspace/products"),
        request<Page<Location>>("/workspace/locations?type=PLANT"),
      ]);
      setProducts(p.items);
      setPlants(l.items);
      setNewIncident(true);
    });
  }
  async function create(e: FormEvent) {
    e.preventDefault();
    creation.current ??= {
      source_ref: crypto.randomUUID(),
      detected_at: new Date().toISOString(),
    };
    await guarded(async () => {
      const item = await request<{ id: string }>("/incidents", {
        source_system: "WEB_UI",
        ...creation.current,
        title,
        description: description || null,
        product_id: productId,
        plant_id: plantId,
      });
      const product = products.find((p) => p.id === productId)!;
      const plant = plants.find((p) => p.id === plantId)!;
      setNewIncident(false);
      creation.current = null;
      await listing(0, "");
      setActiveQuery("");
      setQuery("");
      clearScope();
      setSelected({
        ...item,
        title,
        description,
        status: "OPEN",
        product_id: productId,
        plant_id: plantId,
        sku: product.sku,
        plant_code: plant.code,
        plant_name: plant.name,
        created_at: new Date().toISOString(),
      });
      await scope(item.id);
      setView("Overview");
      setNotice("Incident created. Review planning inputs and select Analyze.");
    });
  }
  const errorView = error && (
    <div className="error-banner" role="alert">
      <TriangleAlert size={18} />
      <span>{error}</span>
      <button
        className="icon-btn"
        aria-label="Dismiss error"
        onClick={() => setError("")}
      >
        <X size={16} />
      </button>
    </div>
  );
  if (starting)
    return (
      <div className="login-shell">
        <Loader2 className="spin" size={30} />
        <p>Opening your workspace…</p>
      </div>
    );
  if (!actor)
    return (
      <div className="login-shell login-redesign">
        <aside className="login-story"><div className="login-story-brand"><Layers3 size={30}/> OpsFlow AI</div><span className="login-kicker">SUPPLY CHAIN OPERATIONS</span><h2>From disruption.<br/>To a clear next move.</h2><p>Understand supply risks, compare recovery plans and keep every decision in view.</p><div className="login-journey">{[{Icon:Box,title:"Know your supply",text:"Inventory and shipment evidence"},{Icon:Truck,title:"Find a recovery path",text:"Warehouse transfers and supplier options"},{Icon:ShieldCheck,title:"Stay in control",text:"Human approval before mock execution"}].map(({Icon,title,text}) => <div key={title}><Icon size={24}/><span><strong>{title}</strong><small>{text}</small></span><CheckCircle2 size={17}/></div>)}</div><small>Demonstration workspace · Mock ERP integration</small></aside>
        <div className="login-card">
          <div className="login-brand">
            <Layers3 size={36} />
            <strong>OpsFlow AI</strong>
          </div>
          <Badge value="OPERATIONS WORKSPACE" />
          <h1>Welcome back.</h1>
          <p className="subtitle">
            Sign in to investigate disruptions and coordinate recovery.
          </p>
          {errorView}
          <form onSubmit={login}>
            <label>
              Username
              <input
                autoComplete="username"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Your workspace username"
                maxLength={128}
              />
            </label>
            <label>
              Password
              <input
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                maxLength={256}
              />
            </label>
            <button type="button" className="text-button" aria-pressed={showPassword} onClick={() => setShowPassword(v => !v)}>{showPassword ? "Hide password" : "Show password"}</button>
            <button className="button primary w-full" disabled={busy}>
              {busy ? (
                <Loader2 size={17} className="spin" />
              ) : (
                <ArrowRight size={17} />
              )}
              Sign in
            </button>
          </form>
          <p className="tiny">
            Your administrator creates your account and assigns your role.
            Contact them if you need access or a password reset.
          </p>
        </div>
        <p className="login-foot">
          Evidence-led decisions. Human-approved recovery.
        </p>
      </div>
    );
  const assessmentView = (
    <>
      {!assessment ? (
        <Blank>
          {running
            ? "Analysis is running…"
            : "Select Analyze to assess current evidence and recovery options."}
        </Blank>
      ) : (
        <>
          <div className="card-heading">
            <h2><Box size={19} className="heading-icon" /> Can we meet demand?</h2>
            <Badge value={assessment.status} />
          </div>
          <h3 className="incident-title">{selected?.title}</h3>
          <p className="subtitle">
            {selected?.plant_name} · {selected?.sku}
          </p>
          <p className="subtitle mt-3">{assessment.explanation}</p>
          {assessedInputs && <div className="assessment-context"><Warehouse size={16}/><span>Assessed transfer source: <strong>{warehouses.find(w => w.code === assessedInputs.warehouse_code)?.name || assessedInputs.warehouse_code}</strong><br/>Destination: {selected?.plant_name} · Snapshot: {date(assessment.assessed_at)}</span></div>}
          {assessment.status === "NEEDS_EVIDENCE" && (
            <div className="evidence-help"><Clock3 size={22} /><div><strong>Supply data needs an update</strong><p>The system cannot confirm a shortage using outdated or incomplete records. Ask your data administrator to update the inventory and shipment evidence listed below, then run the check again. Refresh only reloads stored records.</p></div></div>
          )}
          {impact?.status === "ASSESSED" && sums ? (
            <>
              <SupplyChart demand={sums.demand} stock={sums.stock} inbound={sums.inbound} shortage={sums.shortage} />
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Demand</th>
                      <th>Required by</th>
                      <th>Remaining</th>
                      <th>Allocated</th>
                      <th>Shortage</th>
                    </tr>
                  </thead>
                  <tbody>
                    {impact.allocations.map((d) => (
                      <tr key={d.demand_id}>
                        <td>{d.source_ref}</td>
                        <td>{date(d.required_at)}</td>
                        <td>{formatQty(d.remaining_demand)}</td>
                        <td>
                          {formatQty(
                            Number(d.stock_allocated_qty) +
                              Number(d.inbound_allocated_qty),
                          )}
                        </td>
                        <td className="shortage">
                          {formatQty(d.shortage_qty)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <div className="issues">
              {impact?.issues.map((issue, i) => (
                <div className="issue" key={i}>
                  <TriangleAlert size={17} />
                  <div>
                    <strong>{issue.code.replaceAll("_", " ")}</strong>
                    <p>{issue.message}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
          <p className="tiny mt-4">
            Assessed {date(assessment.assessed_at)}. This is a stored snapshot;
            revalidation occurs before approval and execution.
          </p>
        </>
      )}
    </>
  );
  const proposalList = (
    <section className="panel">
      <div className="card-heading">
        <h2>Proposals for this incident</h2>
        <span className="tiny">
          {manager
            ? "Manager review enabled"
            : "Read-only decisions · manager approval required"}
        </span>
      </div>
      {proposals.length === 0 ? (
        <Blank>
          No proposals yet. Analyze the incident and create a proposal from a
          usable option.
        </Blank>
      ) : (
        <div className="proposal-list">
          {proposals.map((p) => {
            const expired = Date.parse(p.expires_at) <= clock;
            return (
              <article key={p.id} className="proposal-row">
                <div>
                  <div className="flex items-center gap-3">
                    <h3>
                      Version {p.version} ·{" "}
                      {p.action_type === "WAREHOUSE_TRANSFER"
                        ? "Warehouse transfer"
                        : "Supplier purchase"}
                    </h3>
                    <Badge
                      value={
                        p.status === "PROPOSED" && expired
                          ? "EXPIRED"
                          : p.status
                      }
                    />
                  </div>
                  <p className="subtitle">Valid until {date(p.expires_at)}</p>
                  <ProposalSummary proposal={p} destination={selected?.plant_name} />
                </div>
                <div className="flex gap-2 flex-wrap mt-3">
                  {p.status === "PROPOSED" && (
                    <button
                      className="button primary"
                      disabled={!manager || expired || busy}
                      onClick={() => {
                        setReview(p);
                        setReason("");
                      }}
                    >
                      Review proposal
                    </button>
                  )}
                  {p.status === "APPROVED" && (
                    <button
                      className="button primary"
                      disabled={!manager || expired || busy}
                      onClick={() => setConfirmExecution(p)}
                    >
                      Execute mock recovery
                    </button>
                  )}
                  <button
                    className="button secondary"
                    disabled={busy}
                    onClick={() =>
                      void guarded(async () => {
                        setExecution(null);
                        try {
                          setExecution(
                            await request<Execution>(
                              `/proposals/${p.id}/execution`,
                            ),
                          );
                        } catch (e) {
                          if (e instanceof ApiError && e.status === 404) {
                            setNotice(
                              "No execution has been recorded for this proposal.",
                            );
                            return;
                          }
                          throw e;
                        }
                      })
                    }
                  >
                    Check execution
                  </button>
                </div>
                {expired && ["PROPOSED", "APPROVED"].includes(p.status) && (
                  <p className="tiny mt-2">
                    Validity window passed. Reassess and create a fresh
                    proposal; do not change the stored evidence.
                  </p>
                )}
              </article>
            );
          })}
        </div>
      )}
      {proposalCursor && (
        <button
          className="button secondary mt-4"
          disabled={busy}
          onClick={() =>
            void guarded(async () => {
              const p = await request<{
                items: Proposal[];
                next_before_version: number | null;
              }>(
                `/workspace/incidents/${selected!.id}/proposals?before_version=${proposalCursor}`,
              );
              setProposals((prev) => [...prev, ...p.items]);
              setProposalCursor(p.next_before_version);
            })
          }
        >
          Load older proposals
        </button>
      )}
    </section>
  );
  const options = (
    <section className="panel">
      <div className="card-heading">
        <h2>Recovery options</h2>
        <span className="tiny">
          Independent alternatives · cost bases differ
        </span>
      </div>
      {!assessment ? (
        <Blank>Run an analysis first.</Blank>
      ) : (
        <div className="option-grid">
          {assessment.transfer && (
            <div className="option-card">
              <div className="flex gap-3 items-center">
                <span className="option-icon transfer">
                  <Truck size={23} />
                </span>
                <div>
                  <strong>Warehouse transfer</strong>
                  <small>
                    {assessment.transfer.plan?.warehouse_name ||
                      "Selected warehouse"}
                  </small>
                </div>
              </div>
              <div className="mt-3">
                <Badge value={assessment.transfer.status} />
              </div>
              {assessment.transfer.plan ? (
                <>
                  <p>
                    {assessment.transfer.plan.transfer_qty} units · arrival{" "}
                    {date(assessment.transfer.plan.arrival_at)}
                  </p>
                  <p>
                    Transport: {assessment.transfer.plan.currency}{" "}
                    {assessment.transfer.plan.transport_cost}
                  </p>
                </>
              ) : (
                assessment.transfer.issues?.map((x, i) => (
                  <p key={i}>{x.message}</p>
                ))
              )}
              <button
                className="button primary mt-4"
                disabled={
                  busy ||
                  !["FULL_COVERAGE", "PARTIAL_COVERAGE"].includes(
                    assessment.transfer.status,
                  )
                }
                onClick={() => void propose("transfer")}
              >
                Create transfer proposal
              </button>
            </div>
          )}
          {assessment.purchase?.options.map((o) => (
            <div className="option-card" key={o.offer_id}>
              <div className="flex gap-3 items-center">
                <span className="option-icon purchase">
                  <ShoppingCart size={23} />
                </span>
                <div>
                  <strong>{o.supplier_name}</strong>
                  <small>Supplier purchase</small>
                </div>
              </div>
              <div className="mt-3">
                <Badge value={o.status} />
              </div>
              {o.plan ? (
                <>
                  <p>
                    {o.plan.purchase_qty} units · arrival{" "}
                    {date(o.plan.arrival_at)}
                  </p>
                  <p>
                    Order + freight: {o.currency} {o.plan.total_cost}
                  </p>
                </>
              ) : (
                o.reasons.map((r) => <p key={r}>{r.replaceAll("_", " ")}</p>)
              )}
              <button
                className="button primary mt-4"
                disabled={
                  busy ||
                  !["FULL_COVERAGE", "PARTIAL_COVERAGE"].includes(o.status)
                }
                onClick={() => void propose("purchase", o.offer_id)}
              >
                Create purchase proposal
              </button>
            </div>
          ))}
          {!assessment.transfer && !assessment.purchase && (
            <Blank>
              Recovery options are not available for this assessment. Resolve
              the evidence issues above.
            </Blank>
          )}
          {assessment.purchase?.options.length === 0 && (
            <Blank>No supplier offers were returned.</Blank>
          )}
        </div>
      )}
    </section>
  );
  return (
    <div className={`app-shell ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      {mobile && (
        <button
          className="nav-overlay"
          aria-label="Close menu"
          onClick={() => setMobile(false)}
        />
      )}
      <aside id="workspace-sidebar" aria-label="Workspace navigation" className={`sidebar ${mobile ? "open" : ""}`}>
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setView("Overview");
          }}
        >
          <Layers3 size={32} />
          <span>
            OpsFlow AI<small>Operations workspace</small>
          </span>
        </a>
        <button className="sidebar-mobile-close icon-btn" aria-label="Close menu" onClick={() => { setMobile(false); document.getElementById("sidebar-menu-toggle")?.focus(); }}><X size={20} /></button>
        <div className="nav-caption">WORKSPACE</div>
        <nav>
          {nav.map(({ name, Icon }) => (
            <button
              key={name}
              title={name}
              aria-label={name}
              className={view === name ? "active" : ""}
              aria-current={view === name ? "page" : undefined}
              onClick={() => {
                setView(name);
                setMobile(false);
                setShowIncidentPicker(false);
              }}
            >
              <Icon size={19} />
              <span>{name}</span>
              {name === "Approvals" && pending.length > 0 && (
                <b>{pending.length}</b>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="workspace">
            <Warehouse size={19} />
            <span>Connected workspace</span>
          </div>
          <div className="mock-pill">
            Mock ERP
            <span />
          </div>
          <div className="user-profile">
            <span className="avatar">
              {actor.subject.slice(0, 2).toUpperCase()}
            </span>
            <span>
              <strong>{actor.subject}</strong>
              <small>{actor.role.replaceAll("_", " ")}</small>
            </span>
            <button
              aria-label="Sign out"
              className="icon-btn"
              disabled={busy}
              onClick={() => void logout()}
            >
              <LogOut size={17} />
            </button>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="flex gap-3 items-center">
            <button
              id="sidebar-menu-toggle"
              aria-controls="workspace-sidebar"
              aria-expanded={mobile}
              className="icon-btn mobile-menu"
              aria-label="Open menu"
              onClick={() => setMobile(true)}
            >
              <Menu size={22} />
            </button>
            <button className="icon-btn sidebar-desktop-toggle" onClick={toggleSidebar} aria-controls="workspace-sidebar" aria-expanded={!sidebarCollapsed} aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"} title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}>
              {sidebarCollapsed ? <PanelLeftOpen size={22} /> : <PanelLeftClose size={22} />}
            </button>
            <span className="breadcrumb">
              Workspace / <strong>{view}</strong>
            </span>
          </div>
          <Badge value="LIVE WORKSPACE" />
        </header>
        <main id="main">
          <div className="page-title">
            <div>
              <h1>{view === "Overview" ? "Supply chain control center" : view}</h1>
              <p>Find stock shortages. Compare recovery options. Approve the next move.</p>
            </div>
            <div className="page-actions">
              <button
                className="button secondary"
                disabled={busy}
                onClick={() => void refresh()}
              >
                <RefreshCw size={16} className={busy ? "spin" : ""} />
                Refresh
              </button>
              <button
                className="button primary"
                disabled={busy}
                onClick={() => void openNew()}
              >
                <Plus size={17} />
                Report a disruption
              </button>
            </div>
          </div>
          {errorView}
          {selected && view !== "Incidents" && <div className="context-switch"><div><span className="eyebrow-small">SELECTED INCIDENT</span><strong>{selected.title}</strong><span>{selected.plant_name} · {selected.sku}</span></div><button className="button secondary" onClick={() => setShowIncidentPicker(v => !v)}>{showIncidentPicker ? "Close selector" : "Change incident"}</button></div>}
          <section className="panel incident-selector" hidden={!!selected && view !== "Incidents" && !showIncidentPicker}>
            <div className="selector-heading"><TriangleAlert size={19} /><div><h2>Which disruption needs attention?</h2><p>Select a record to view its supply assessment, recovery options and approvals.</p></div></div>
            <form
              className="flex gap-3"
              onSubmit={(e) => {
                e.preventDefault();
                setActiveQuery(query);
                void guarded(() => listing(0, query));
              }}
            >
              <label className="search grow">
                <Search size={16} />
                <input
                  aria-label="Search incidents"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search incident title or SKU"
                />
              </label>
              <button className="button secondary" disabled={busy}>
                Search
              </button>
            </form>
            <div className="incident-toolbar" aria-label="Filter loaded incidents">
              <div className="incident-filters">{["ALL", "OPEN", "INVESTIGATING", "RESOLVED"].map(status => <button type="button" key={status} aria-pressed={incidentFilter === status} className={incidentFilter === status ? "active" : ""} onClick={() => setIncidentFilter(status)}>{status === "ALL" ? "All incidents" : status === "INVESTIGATING" ? "Investigating" : status === "RESOLVED" ? "Resolved" : "Open"}<span>{items.filter(i => status === "ALL" || i.status === status).length}</span></button>)}</div>
              <span className="tiny">Filters apply to loaded records</span>
            </div>
            <div className="incident-chips">
              {items.filter(i => incidentFilter === "ALL" || i.status === incidentFilter).map((i) => (
                <button
                  disabled={busy || !!running || openingId !== null}
                  aria-pressed={selected?.id === i.id}
                  aria-busy={openingId === i.id}
                  key={i.id}
                  className={`incident-chip ${selected?.id === i.id ? "chosen" : ""}`}
                  onClick={async () => { setOpeningId(i.id); try { await choose(i); } finally { setOpeningId(null); } }}
                >
                  <span className={`incident-card-icon state-${i.status.toLowerCase()}`}>{openingId === i.id ? <Loader2 size={22} className="spin" /> : i.status === "RESOLVED" ? <CheckCircle2 size={22} /> : i.status === "INVESTIGATING" ? <Search size={22} /> : <Box size={22} />}</span><strong>{i.title}</strong>
                  <small>
                    {i.plant_name} · {i.sku}
                  </small>
                  <span className="incident-card-bottom"><Badge value={i.status} /><span className="incident-open">{openingId === i.id ? "Loading…" : selected?.id === i.id ? "Selected" : "View review"}{selected?.id === i.id ? <CheckCircle2 size={14} /> : <ArrowRight size={14} />}</span></span>
                </button>
              ))}
              {items.filter(i => incidentFilter === "ALL" || i.status === incidentFilter).length === 0 && (
                <Blank>
                  No loaded incidents match this filter. Select All incidents or change your search.
                </Blank>
              )}
            </div>
            {next !== null && (
              <button
                className="text-button mt-3"
                disabled={busy}
                onClick={() => void guarded(() => listing(next))}
              >
                Load more incidents
                <ArrowRight size={15} />
              </button>
            )}
          </section>
          {!selected ? (
            <section className="panel mt-5">
              <Blank>
                Select an incident above. The workspace shows only real records
                from your backend.
              </Blank>
            </section>
          ) : (
            <>
              <div className="scope-label">
                <span>
                  {selected.plant_name} / <strong>{selected.sku}</strong>
                </span>
                <Badge value={selected.status} />
              </div>
              {view === "Overview" && (
                <div className="metrics">
                  {[
                    {
                      label: "Remaining demand",
                      value:
                        impact?.status === "ASSESSED" && sums
                          ? formatQty(sums.demand)
                          : "—",
                      Icon: Box,
                    },
                    {
                      label: "Units at risk",
                      value:
                        impact?.status === "ASSESSED" && sums
                          ? formatQty(sums.shortage)
                          : "—",
                      Icon: TriangleAlert,
                    },
                    {
                      label: "Proposals awaiting review",
                      value: String(pending.length),
                      Icon: UserCheck,
                    },
                    {
                      label: "Loaded planning runs",
                      value: String(runs.length),
                      Icon: Activity,
                    },
                  ].map((x) => (
                    <div className="metric" key={x.label}>
                      <span className="metric-icon indigo">
                        <x.Icon size={24} />
                      </span>
                      <div>
                        <span>{x.label}</span>
                        <strong>{x.value}</strong>
                        <small>Selected incident · loaded records</small>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {view === "Overview" && <WorkflowDashboard assessment={assessment} proposals={proposals} records={records} runs={runs} running={!!running}
                onPlan={() => { const panel = document.getElementById("planning-estimates") as HTMLDetailsElement | null; if (panel) { panel.open = true; panel.scrollIntoView({ behavior: "smooth", block: "center" }); panel.querySelector("input")?.focus({ preventScroll: true }); } }}
                onProposals={() => setView("Recovery proposals")} onApprovals={() => setView("Approvals")} onHistory={() => setView("Record history")} onRuns={() => setView("Workflow runs")} />}
              {(view === "Overview" ||
                view === "Incidents" ||
                view === "Recovery proposals") && (
                <>
                  <div className="dashboard-grid">
                    <div className="left-column">
                      <section className="panel">{assessmentView}</section>
                      {options}
                    </div>
                    <div className="right-column">
                      <section className="panel planning-panel">
                        <details id="planning-estimates">
                        <summary><Truck size={19} /> Configure supply check <span>Warehouse, delivery time & costs</span></summary>
                        <div className="card-heading">
                          <h2><Truck size={19} className="heading-icon" /> Delivery & cost estimates</h2>
                          <Badge value="LKR" />
                        </div>
                        <div className="planning-context"><strong>Checking demand at {selected.plant_name}</strong><p>Product: {selected.sku}. Choose a source warehouse for a possible transfer. This does not change the incident destination.</p></div>
                        <form onSubmit={analyze} className="planning-form">
                          <label>
                            Warehouse search
                            <input
                              value={warehouseQuery}
                              onChange={(e) =>
                                setWarehouseQuery(e.target.value)
                              }
                              placeholder="Name or code"
                            />
                          </label>
                          <button
                            type="button"
                            className="text-button"
                            disabled={busy}
                            onClick={() =>
                              void guarded(() => loadWarehouses(warehouseQuery))
                            }
                          >
                            Find warehouses
                          </button>
                          <label>
                            Transfer source warehouse
                            <select
                              required
                              value={inputs.warehouse_code}
                              disabled={busy || !!running}
                              onChange={(e) =>
                                changeInput("warehouse_code", e.target.value)
                              }
                            >
                              <option value="">Select warehouse</option>
                              {warehouses.map((w) => (
                                <option key={w.id} value={w.code}>
                                  {w.name} ({w.code})
                                </option>
                              ))}
                            </select>
                          </label>
                          <label>
                            Transfer lead time (hours)
                            <input
                              type="number"
                              required
                              min={0}
                              max={8760}
                              value={inputs.transfer_lead_time_hours}
                              disabled={busy || !!running}
                              onChange={(e) =>
                                changeInput(
                                  "transfer_lead_time_hours",
                                  Number(e.target.value),
                                )
                              }
                            />
                          </label>
                          <label>
                            Transport cost (LKR)
                            <input
                              type="number"
                              step="0.0001"
                              required
                              min={0}
                              value={inputs.transport_cost}
                              disabled={busy || !!running}
                              onChange={(e) =>
                                changeInput("transport_cost", e.target.value)
                              }
                            />
                          </label>
                          <label>
                            Purchase freight (LKR)
                            <input
                              type="number"
                              step="0.0001"
                              required
                              min={0}
                              value={inputs.purchase_freight_cost}
                              disabled={busy || !!running}
                              onChange={(e) =>
                                changeInput(
                                  "purchase_freight_cost",
                                  e.target.value,
                                )
                              }
                            />
                          </label>
                          <button
                            className="button primary w-full"
                            disabled={
                              busy ||
                              !!running ||
                              !["OPEN", "INVESTIGATING"].includes(
                                selected.status,
                              )
                            }
                          >
                            {busy || running ? (
                              <Loader2 size={16} className="spin" />
                            ) : (
                              <Activity size={16} />
                            )}{" "}
                            {running ? "Analysis running" : "Check supply & options"}
                          </button>
                          {running && (
                            <button
                              type="button"
                              className="text-button"
                              onClick={() => {
                                setRunning(null);
                                setNotice(
                                  "Stopped watching this run. Its server-side state is unchanged.",
                                );
                              }}
                            >
                              Stop watching run
                            </button>
                          )}
                          <p className="tiny">
                            Review these estimates before analysis. They are not
                            automatically obtained from a carrier quote.
                          </p>
                        </form>
                        </details>
                      </section>
                      <section className={`panel ai-card ${view === "Overview" ? "overview-duplicate-brief" : ""}`}>
                        <div className="card-heading">
                          <h2 className="flex items-center gap-2">
                            <Sparkles size={20} />
                            Assessment brief
                          </h2>
                          <Badge value="ADVISORY" />
                        </div>
                        <p>
                          {assessment?.ai_explanation?.summary ||
                            assessment?.explanation ||
                            "Run an assessment to see evidence-based findings."}
                        </p>
                        <div className="ai-footnote">
                          <ShieldCheck size={14} />
                          Approval and execution rules remain deterministic.
                        </div>
                      </section>
                    </div>
                  </div>
                  {view === "Recovery proposals" && (
                    <div className="mt-5">{proposalList}</div>
                  )}
                </>
              )}
              {view === "Approvals" && proposalList}
              {view === "Workflow runs" && (
                <section className="panel">
                  <h2><Activity className="heading-icon" size={20}/> Planning activity</h2><p className="subtitle">{runs.length} loaded runs for {selected.plant_name}. Open details to inspect the actual workflow steps.</p>
                  {runs.length === 0 ? (
                    <Blank>No planning runs yet. Use Analyze incident.</Blank>
                  ) : (
                    runs.map((r) => (
                      <article className="proposal-row" key={r.id}>
                        <div className="flex justify-between gap-3">
                          <span>{date(r.created_at)}</span>
                          <Badge value={r.status} />
                        </div>
                        {r.error_code && (
                          <p className="form-error">{r.error_code}</p>
                        )}
                        <button className="button secondary mt-3" disabled={busy} onClick={() => void guarded(async () => setRunDetail(await request<Run>(`/runs/${r.id}`)))}>View workflow steps <ArrowRight size={15}/></button>
                        <button
                          className="text-button mt-3"
                          disabled={busy}
                          onClick={() =>
                            void guarded(async () => {
                              const run = await request<
                                Run & { inputs: Inputs }
                              >(`/runs/${r.id}`);
                              setAssessment(run.result);
                              setAssessedInputs(run.inputs);
                              setInputs(run.inputs);
                              setRunning(
                                run.status === "RUNNING" ? run.id : null,
                              );
                              setView("Overview");
                              setNotice(
                                "Loaded a stored run. Check its assessment time before acting.",
                              );
                            })
                          }
                        >
                          Open run
                          <ArrowRight size={15} />
                        </button>
                      </article>
                    ))
                  )}
                  {runMore && (
                    <button
                      className="button secondary mt-3"
                      disabled={busy}
                      onClick={() =>
                        void guarded(async () => {
                          const offset = runOffset + 20;
                          const page = await request<{ items: Run[] }>(
                            `/incidents/${selected.id}/runs?limit=20&offset=${offset}`,
                          );
                          setRuns((prev) => [...prev, ...page.items]);
                          setRunOffset(offset);
                          setRunMore(page.items.length === 20);
                        })
                      }
                    >
                      Load older runs
                    </button>
                  )}
                </section>
              )}
              {view === "Record history" && (
                <section className="panel">
                  <h2>Incident record history</h2>
                  <p className="subtitle mt-2">
                    Stored proposal, approval and execution records. This is not
                    an immutable event ledger.
                  </p>
                  {!records?.items.length ? (
                    <div className="history-start"><div><CheckCircle2 size={20}/><strong>Incident reported</strong><span>{date(selected.created_at)}</span></div><p>{selected.title}</p><p>{runs.length} planning run(s) loaded. No recovery proposal, approval or execution has been recorded for this incident.</p><button className="button secondary" onClick={() => setView("Workflow runs")}>View planning runs <ArrowRight size={16}/></button></div>
                  ) : (
                    records.items.map((r) => (
                      <article className="proposal-row" key={r.proposal.id}>
                        <div className="flex justify-between gap-3">
                          <h3>Proposal version {r.proposal.version}</h3>
                          <Badge value={r.proposal.current_status} />
                        </div>
                        <p className="subtitle">
                          {r.proposal.action_type.replaceAll("_", " ")} ·{" "}
                          {date(r.proposal.created_at)}
                        </p>
                        {r.decision && (
                          <p className="record-text">
                            <strong>{r.decision.decision}</strong> by{" "}
                            {r.decision.manager_subject}
                            <br />
                            {r.decision.reason}
                          </p>
                        )}
                        {r.resume_job && (
                          <p className="subtitle">
                            Resume job: {r.resume_job.current_status}
                          </p>
                        )}
                        {r.execution && (
                          <div className="info-note mt-3">
                            <CheckCircle2 size={20} />
                            <div>
                              <strong>Execution: {r.execution.status}</strong>
                              <p>
                                {r.execution.failure_reason ||
                                  r.execution.external_ref}
                              </p>
                              <p>
                                {r.execution.quantity} units ·{" "}
                                {r.execution.mode} · Physical receipt:{" "}
                                {r.execution.physical_receipt_recorded
                                  ? "recorded"
                                  : "not recorded"}
                              </p>
                            </div>
                          </div>
                        )}
                      </article>
                    ))
                  )}
                  {records?.next_before_version && (
                    <button
                      className="button secondary mt-3"
                      disabled={busy}
                      onClick={() =>
                        void guarded(async () => {
                          const page = await request<Records>(
                            `/incidents/${selected.id}/history?before_version=${records.next_before_version}`,
                          );
                          setRecords((prev) => ({
                            items: [...(prev?.items || []), ...page.items],
                            next_before_version: page.next_before_version,
                          }));
                        })
                      }
                    >
                      Load older records
                    </button>
                  )}
                </section>
              )}
            </>
          )}
          <footer className="page-footer">
            <span>
              <span className="status-dot" />
              Single-organization workspace · Mock ERP
            </span>
            <span>No physical receipt is recorded by mock execution.</span>
          </footer>
        </main>
      </div>
      {notice && (
        <div className="toast" role="status">
          <CheckCircle2 size={18} />
          {notice}
        </div>
      )}
      {newIncident && (
        <Modal
          title="Create an incident"
          close={() => {
            if (!busy) setNewIncident(false);
          }}
        >
          {errorView}
          <form onSubmit={create} className="planning-form">
            <label>
              Title
              <input
                required
                value={title}
                maxLength={255}
                onChange={(e) => {
                  setTitle(e.target.value);
                  creation.current = null;
                }}
                placeholder="Describe the disruption"
              />
            </label>
            <label>
              Description
              <textarea
                value={description}
                maxLength={10000}
                onChange={(e) => {
                  setDescription(e.target.value);
                  creation.current = null;
                }}
              />
            </label>
            <div className="form-grid">
              <label>
                Find product
                <input
                  value={productQuery}
                  onChange={(e) => setProductQuery(e.target.value)}
                />
              </label>
              <button
                className="button secondary"
                type="button"
                disabled={busy}
                onClick={() =>
                  void guarded(async () => {
                    const p = await request<Page<Product>>(
                      `/workspace/products?q=${encodeURIComponent(productQuery)}`,
                    );
                    setProducts(p.items);
                    setProductId("");
                    creation.current = null;
                  })
                }
              >
                Search products
              </button>
            </div>
            <label>
              Product
              <select
                required
                value={productId}
                onChange={(e) => {
                  setProductId(e.target.value);
                  creation.current = null;
                }}
              >
                <option value="">Select product</option>
                {products.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} · {p.sku}
                  </option>
                ))}
              </select>
            </label>
            <div className="form-grid">
              <label>
                Find plant
                <input
                  value={plantQuery}
                  onChange={(e) => setPlantQuery(e.target.value)}
                />
              </label>
              <button
                className="button secondary"
                type="button"
                disabled={busy}
                onClick={() =>
                  void guarded(async () => {
                    const l = await request<Page<Location>>(
                      `/workspace/locations?type=PLANT&q=${encodeURIComponent(plantQuery)}`,
                    );
                    setPlants(l.items);
                    setPlantId("");
                    creation.current = null;
                  })
                }
              >
                Search plants
              </button>
            </div>
            <label>
              Destination plant
              <select
                required
                value={plantId}
                onChange={(e) => {
                  setPlantId(e.target.value);
                  creation.current = null;
                }}
              >
                <option value="">Select plant</option>
                {plants.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} · {p.code}
                  </option>
                ))}
              </select>
            </label>
            <p className="tiny">
              Lists show the first 50 matches. Narrow the search to find
              additional records.
            </p>
            <button
              className="button primary w-full"
              disabled={busy || !productId || !plantId}
            >
              Create incident
            </button>
          </form>
        </Modal>
      )}
      {runDetail && <Modal title="Workflow run details" close={() => setRunDetail(null)}><Badge value={runDetail.status}/><p className="subtitle mt-3">Started {date(runDetail.created_at)}</p><div className="run-step-list">{runDetail.steps?.length ? runDetail.steps.map((step,index) => <div key={index}><span>{index+1}</span><strong>{step.name.replaceAll("_", " ")}</strong><Badge value={step.status}/></div>) : <p>No step details were returned for this run.</p>}</div><p>{runDetail.result?.explanation || runDetail.error_code || "No assessment result available."}</p></Modal>}
      {review && (
        <Modal
          title={`Review proposal · version ${review.version}`}
          close={() => {
            if (!busy) setReview(null);
          }}
        >
          {errorView}
          <Badge value={review.action_type} />
          <p className="subtitle mt-3">
            Valid until {date(review.expires_at)}. Approval revalidates the
            saved evidence.
          </p>
          <ProposalSummary proposal={review} destination={selected?.plant_name} />
          <label className="mt-4">
            Why are you approving or rejecting this plan?
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              maxLength={1000}
              required
            />
          </label>
          <div className="dialog-actions">
            <button
              className="button secondary"
              disabled={
                busy || !reason.trim() || Date.parse(review.expires_at) <= clock
              }
              onClick={() => void decide("REJECTED")}
            >
              Reject
            </button>
            <button
              className="button primary"
              disabled={
                busy || !reason.trim() || Date.parse(review.expires_at) <= clock
              }
              onClick={() => void decide("APPROVED")}
            >
              Approve proposal
            </button>
          </div>
        </Modal>
      )}
      {confirmExecution && (
        <Modal
          title="Execute approved mock recovery?"
          close={() => {
            if (!busy) setConfirmExecution(null);
          }}
        >
          {errorView}
          <div className="info-note">
            <TriangleAlert size={21} />
            <p>
              This records a mock order and reserves supply in the database. It
              does not deliver goods or record a physical receipt. Repeated
              execution of the same proposal is idempotent.
            </p>
          </div>
          <p className="subtitle mt-4">
            Proposal version {confirmExecution.version} ·{" "}
            {confirmExecution.action_type.replaceAll("_", " ")}
          </p>
          <div className="dialog-actions">
            <button
              className="button secondary"
              disabled={busy}
              onClick={() => setConfirmExecution(null)}
            >
              Cancel
            </button>
            <button
              className="button primary"
              disabled={
                busy || Date.parse(confirmExecution.expires_at) <= clock
              }
              onClick={() => void execute()}
            >
              Confirm mock execution
            </button>
          </div>
        </Modal>
      )}
      {execution && (
        <Modal title="Execution result" close={() => setExecution(null)}>
          <Badge value={execution.status} />
          <p className="subtitle mt-4">
            {execution.failure_reason ||
              "Mock order recorded. No physical receipt has been recorded."}
          </p>
          <div className="detail-stats">
            <div>
              Quantity<strong>{execution.result.quantity || "—"}</strong>
            </div>
            <div>
              Mode<strong>{execution.result.mode || "MOCK"}</strong>
            </div>
          </div>
          <p className="subtitle">
            Order reference: {execution.result.external_ref || "Not created"}
          </p>
          <button
            className="button primary mt-5"
            onClick={() => {
              setExecution(null);
              setView("Record history");
            }}
          >
            View incident history
            <ArrowRight size={16} />
          </button>
        </Modal>
      )}
    </div>
  );
}
