"use client";
import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import {
  Activity,
  ArrowDownLeft,
  ArrowRight,
  Bell,
  Box,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ClipboardList,
  Clock3,
  Database,
  Download,
  ExternalLink,
  History,
  House,
  Layers3,
  Link2,
  Loader2,
  LogOut,
  Menu,
  Package,
  Plus,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  ShoppingCart,
  Sparkles,
  TriangleAlert,
  Truck,
  UserCheck,
  Warehouse,
  X,
} from "lucide-react";
import { api, formatQty, type Actor, type Impact } from "@/lib/api";
import { demoImpact } from "@/lib/demo";

type Section =
  | "Overview"
  | "Incidents"
  | "Recovery proposals"
  | "Approvals"
  | "Workflow runs"
  | "Record history";
type Dialog =
  | "connection"
  | "incident"
  | "transfer"
  | "purchase"
  | "approval"
  | "new"
  | "notifications"
  | null;
const navigation = [
  { name: "Overview", icon: House },
  { name: "Incidents", icon: TriangleAlert },
  { name: "Recovery proposals", icon: ClipboardList },
  { name: "Approvals", icon: UserCheck },
  { name: "Workflow runs", icon: Activity },
  { name: "Record history", icon: History },
] as const;
const descriptions: Record<Section, string> = {
  Overview: "Monitor disruptions. Review recovery. Stay in control.",
  Incidents: "A clear view of the disruptions that need your attention.",
  "Recovery proposals": "Review the evidence behind each recovery option.",
  Approvals: "Human judgment. Every critical decision.",
  "Workflow runs": "Follow your assessments from evidence to recommendation.",
  "Record history": "Review stored decisions and execution records.",
};
function Badge({
  children,
  tone = "blue",
}: {
  children: ReactNode;
  tone?: "blue" | "amber" | "green" | "muted";
}) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
function Empty({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="empty-state">
      <Database size={30} />
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
function Modal({
  title,
  children,
  onClose,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const el = ref.current;
    el?.showModal();
    return () => el?.close();
  }, []);
  return (
    <dialog
      ref={ref}
      onCancel={onClose}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      aria-labelledby="dialog-title"
    >
      <header>
        <h2 id="dialog-title">{title}</h2>
        <button
          className="icon-btn"
          onClick={onClose}
          aria-label="Close dialog"
        >
          <X size={20} />
        </button>
      </header>
      <div className="dialog-body">{children}</div>
    </dialog>
  );
}
export default function Dashboard() {
  const [section, setSection] = useState<Section>("Overview");
  const [dialog, setDialog] = useState<Dialog>(null);
  const [mobile, setMobile] = useState(false);
  const [mode, setMode] = useState<"demo" | "live">("demo");
  const [token, setToken] = useState("");
  const [draftToken, setDraftToken] = useState("");
  const [actor, setActor] = useState<Actor | null>(null);
  const [impact, setImpact] = useState<Impact>(demoImpact);
  const [sku, setSku] = useState("FAN-MOTOR-45W");
  const [plant, setPlant] = useState("LK-HOM-PLANT");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [search, setSearch] = useState("");
  const [review, setReview] = useState<
    "Pending review" | "Approved" | "Rejected"
  >("Pending review");
  const [reason, setReason] = useState("");
  const [incidentId, setIncidentId] = useState(
    "081c88fc-1554-426b-bd0d-287b83362905",
  );
  const [history, setHistory] = useState<unknown>(null);
  const demo = mode === "demo";
  const assessed = impact.status === "ASSESSED";
  const total = impact.allocations.reduce(
    (a, x) => ({
      demand: a.demand + Number(x.remaining_demand),
      stock: a.stock + Number(x.stock_allocated_qty),
      inbound: a.inbound + Number(x.inbound_allocated_qty),
      shortage: a.shortage + Number(x.shortage_qty),
    }),
    { demand: 0, stock: 0, inbound: 0, shortage: 0 },
  );
  const matches =
    !search ||
    `${impact.plant_name} ${impact.sku} fan motor supply disruption ${impact.plant_code}`
      .toLowerCase()
      .includes(search.toLowerCase());
  useEffect(() => {
    if (!notice) return;
    const id = setTimeout(() => setNotice(""), 4500);
    return () => clearTimeout(id);
  }, [notice]);
  async function load(t = token, connecting = false) {
    setBusy(true);
    setError("");
    try {
      const authenticated = await api<Actor>("/auth/me", t);
      const data = await api<Impact>(
        `/impact?sku=${encodeURIComponent(sku)}&plant_code=${encodeURIComponent(plant)}`,
        t,
      );
      setActor(authenticated);
      setImpact(data);
      setMode("live");
      setToken(t);
      setHistory(null);
      setSearch("");
      if (connecting) {
        setDialog(null);
        setDraftToken("");
      }
      setNotice("Latest impact assessment loaded.");
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Unable to reach API. Check your connection.",
      );
    } finally {
      setBusy(false);
    }
  }
  function disconnect() {
    setToken("");
    setDraftToken("");
    setActor(null);
    setMode("demo");
    setImpact(demoImpact);
    setHistory(null);
    setError("");
    setNotice("Disconnected. Showing illustrative demo data.");
    setDialog(null);
  }
  function refresh() {
    if (demo)
      setNotice(
        "Demo snapshot refreshed. Connect the API for current evidence.",
      );
    else void load();
  }
  async function getHistory(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setHistory(null);
    try {
      setHistory(
        await api(
          `/incidents/${encodeURIComponent(incidentId)}/history?limit=20`,
          token,
        ),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "History unavailable.");
    } finally {
      setBusy(false);
    }
  }
  function exportSnapshot() {
    const blob = new Blob([JSON.stringify({ mode, impact }, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `opsflow-${mode}-assessment.json`;
    a.click();
    URL.revokeObjectURL(url);
  }
  const titles: Record<Exclude<Dialog, null>, string> = {
    connection: "Connect your backend",
    incident: "Incident overview",
    transfer: "Warehouse transfer",
    purchase: "Supplier purchase",
    approval: "Review recovery proposal",
    new: "Create an incident",
    notifications: "Workspace updates",
  };
  const summary = (
    <>
      <div className="card-heading">
        <div className="flex items-center gap-3 flex-wrap">
          <h2>{demo ? "Priority incident" : "Impact assessment"}</h2>
          <Badge
            tone={
              assessed && total.shortage > 0
                ? "amber"
                : assessed
                  ? "green"
                  : "muted"
            }
          >
            {assessed && total.shortage > 0 ? (
              <TriangleAlert size={13} />
            ) : (
              <Activity size={13} />
            )}{" "}
            {assessed
              ? total.shortage > 0
                ? "Action required"
                : "Covered"
              : impact.status.replaceAll("_", " ")}
          </Badge>
        </div>
        <Badge tone={demo ? "muted" : assessed ? "green" : "amber"}>
          {demo ? (
            "Demo snapshot"
          ) : assessed ? (
            <>
              <CheckCircle2 size={13} /> Evidence current
            </>
          ) : (
            "Review evidence"
          )}
        </Badge>
      </div>
      <h3 className="incident-title">
        {demo
          ? "Fan motor supply disruption"
          : `${impact.sku} supply assessment`}
      </h3>
      <p className="subtitle">
        {impact.plant_name}
        <span className="mx-2 text-slate-300">·</span>
        {impact.sku}
      </p>
      {assessed ? (
        <>
          <div className="coverage">
            <p>
              Remaining demand <strong>{formatQty(total.demand)} units</strong>
            </p>
            <div
              className="coverage-bar"
              role="img"
              aria-label={`Stock ${total.stock}, inbound ${total.inbound}, shortage ${total.shortage}`}
            >
              <span
                style={{
                  width: `${total.demand ? (total.stock / total.demand) * 100 : 0}%`,
                }}
              />
              <span
                style={{
                  width: `${total.demand ? (total.inbound / total.demand) * 100 : 0}%`,
                }}
              />
              <span
                style={{
                  width: `${total.demand ? (total.shortage / total.demand) * 100 : 0}%`,
                }}
              />
            </div>
            <div className="legend">
              {[
                { name: "Stock allocated", value: total.stock, color: "teal" },
                {
                  name: "On-time inbound",
                  value: total.inbound,
                  color: "blue",
                },
                { name: "Shortage", value: total.shortage, color: "orange" },
              ].map((x) => (
                <div key={x.name}>
                  <i className={x.color} />
                  <span>
                    {x.name}
                    <strong>{formatQty(x.value)} units</strong>
                  </span>
                </div>
              ))}
            </div>
          </div>
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
                {impact.allocations.map((x, i) => (
                  <tr key={x.demand_id}>
                    <td>{x.source_ref}</td>
                    <td>
                      {demo
                        ? `Demo, ${i ? "19:00" : "18:00"}`
                        : new Date(x.required_at).toLocaleString("en-GB", {
                            timeZone: "Asia/Colombo",
                            month: "short",
                            day: "numeric",
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                    </td>
                    <td>{formatQty(x.remaining_demand)}</td>
                    <td>
                      {formatQty(
                        Number(x.stock_allocated_qty) +
                          Number(x.inbound_allocated_qty),
                      )}
                    </td>
                    <td
                      className={Number(x.shortage_qty) > 0 ? "shortage" : ""}
                    >
                      {formatQty(x.shortage_qty)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <div className="issues">
          <h4>
            {impact.status === "NO_OPEN_DEMANDS"
              ? "No open demands"
              : "Assessment incomplete"}
          </h4>
          <p>
            {impact.status === "NO_OPEN_DEMANDS"
              ? "There are no active demands in this product and plant scope."
              : "Update the evidence before making a recovery decision. No definitive shortage is shown."}
          </p>
          {impact.issues.map((x, i) => (
            <div className="issue" key={i}>
              <TriangleAlert size={15} />
              <div>
                <strong>{x.code.replaceAll("_", " ")}</strong>
                <p>
                  {x.reference}: {x.message}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
      <div className="flex justify-between items-center mt-5 gap-3">
        <button className="text-button" onClick={() => setDialog("incident")}>
          View assessment <ArrowRight size={16} />
        </button>
        {!demo && (
          <span className="tiny">
            Assessed {new Date(impact.assessed_at).toLocaleTimeString()}
          </span>
        )}
      </div>
    </>
  );
  const options = (
    <section className="panel">
      <div className="card-heading">
        <h2>Recovery options</h2>
        <span className="tiny">
          Independent alternatives. Cost bases differ.
        </span>
      </div>
      {demo ? (
        <div className="option-grid">
          {[
            {
              type: "transfer" as const,
              title: "Warehouse transfer",
              sub: "Wattala Warehouse",
              Icon: Truck,
              time: "6 hours",
              cost: "Transport cost LKR 18,000",
            },
            {
              type: "purchase" as const,
              title: "Supplier purchase",
              sub: "Approved supplier offer",
              Icon: ShoppingCart,
              time: "7 hours",
              cost: "Order + freight LKR 600,000",
            },
          ].map((x) => (
            <button
              key={x.type}
              className="option-card"
              onClick={() => setDialog(x.type)}
            >
              <div className="flex items-center gap-3">
                <span className={`option-icon ${x.type}`}>
                  <x.Icon size={23} />
                </span>
                <span>
                  <strong>{x.title}</strong>
                  <small>{x.sub}</small>
                </span>
              </div>
              <p>
                <Box size={17} />
                280 units <span>·</span>
                {x.time}
              </p>
              <p>
                <Database size={17} />
                {x.cost}
              </p>
              <span className="option-link">
                View option <ArrowRight size={15} />
              </span>
            </button>
          ))}
        </div>
      ) : (
        <Empty title="Recovery options are not loaded">
          This dashboard currently connects to the impact API. Use backend
          Swagger to evaluate and create a proposal.
        </Empty>
      )}
    </section>
  );
  const approval = (
    <section className="panel">
      <div className="card-heading">
        <h2 className="flex items-center gap-2">
          <UserCheck size={22} />
          Approval required
        </h2>
      </div>
      {demo ? (
        <>
          <div className="approval-box">
            <Warehouse size={29} />
            <div>
              <strong>Warehouse transfer</strong>
              <p>280 units · Wattala → Homagama</p>
            </div>
            <Badge
              tone={
                review === "Pending review"
                  ? "amber"
                  : review === "Approved"
                    ? "green"
                    : "muted"
              }
            >
              {review}
            </Badge>
          </div>
          <button
            className="button primary w-full mt-3"
            onClick={() => setDialog("approval")}
          >
            {review === "Pending review"
              ? "Review proposal"
              : "View demo decision"}
          </button>
        </>
      ) : (
        <Empty title="Approval queue not connected">
          No pending-approval count is inferred from an impact assessment.
        </Empty>
      )}
    </section>
  );
  return (
    <div className="app-shell">
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      {mobile && (
        <button
          aria-label="Close navigation"
          className="nav-overlay"
          onClick={() => setMobile(false)}
        />
      )}
      <aside className={`sidebar ${mobile ? "open" : ""}`}>
        <a
          href="#"
          className="brand"
          onClick={(e) => {
            e.preventDefault();
            setSection("Overview");
          }}
        >
          <span className="brand-mark">
            <Layers3 size={31} />
          </span>
          <span>
            OpsFlow AI<small>Operations workspace</small>
          </span>
        </a>
        <div className="nav-caption">WORKSPACE</div>
        <nav aria-label="Main navigation">
          {navigation.map(({ name, icon: Icon }) => (
            <button
              key={name}
              className={section === name ? "active" : ""}
              aria-current={section === name ? "page" : undefined}
              onClick={() => {
                setSection(name);
                setSearch("");
                setMobile(false);
              }}
            >
              <Icon size={19} />
              <span>{name}</span>
              {name === "Approvals" && demo && review === "Pending review" && (
                <b>1</b>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="workspace">
            <Warehouse size={20} />
            <span>{demo ? "Demo workspace" : "Connected workspace"}</span>
            <ChevronRight size={16} />
          </div>
          <div className="mock-pill">
            <Database size={13} />
            Mock ERP
            <span />
          </div>
          <button
            className="user-profile"
            onClick={() => setDialog("connection")}
          >
            <span className="avatar">
              {demo ? "CM" : actor?.subject.slice(0, 2).toUpperCase()}
            </span>
            <span>
              <strong>{actor?.subject || "Chamii"}</strong>
              <small>
                {demo
                  ? "Demo · Procurement Manager"
                  : actor?.role.replaceAll("_", " ")}
              </small>
            </span>
            <Settings2 size={16} />
          </button>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="flex items-center gap-3">
            <button
              className="icon-btn mobile-menu"
              aria-label="Open navigation"
              onClick={() => setMobile(true)}
            >
              <Menu size={22} />
            </button>
            <Layers3 className="breadcrumb-icon" size={18} />
            <span className="breadcrumb">
              Workspace <span>/</span> <strong>{section}</strong>
            </span>
          </div>
          <div className="header-actions">
            <label className="search">
              <Search size={17} />
              <input
                aria-label="Filter the current assessment"
                placeholder="Search current assessment…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              <kbd>⌕</kbd>
            </label>
            <button
              className="icon-btn notification"
              aria-label="View notifications"
              onClick={() => setDialog("notifications")}
            >
              <Bell size={20} />
              {demo && review === "Pending review" && <i />}
            </button>
            <span className="header-divider" />
            <button
              className="avatar-button"
              aria-label="Connection settings"
              onClick={() => setDialog("connection")}
            >
              <span className="avatar small">
                {demo ? "CM" : actor?.subject.slice(0, 2).toUpperCase()}
              </span>
              <ChevronDown size={15} />
            </button>
          </div>
        </header>
        <main id="main">
          <div className="page-title">
            <div>
              <div className="flex items-center gap-3 flex-wrap">
                <h1>
                  {section === "Overview" ? "Operations overview" : section}
                </h1>
                <Badge tone={demo ? "blue" : "green"}>
                  {demo ? "DEMO DATA" : "LIVE IMPACT"}
                </Badge>
              </div>
              <p>{descriptions[section]}</p>
            </div>
            <div className="page-actions">
              <button
                className="button secondary"
                onClick={refresh}
                disabled={busy}
              >
                <RefreshCw size={16} className={busy ? "spin" : ""} />
                Refresh
              </button>
              <button
                className="button primary"
                onClick={() => setDialog(demo ? "new" : "connection")}
              >
                {demo ? <Plus size={18} /> : <Link2 size={17} />}{" "}
                {demo ? "New incident" : "Connection"}
              </button>
            </div>
          </div>
          {error && (
            <div className="error-banner" role="alert">
              <TriangleAlert size={18} />
              <span>
                {error}{" "}
                {mode === "live"
                  ? "The previous assessment remains visible; it has not been refreshed."
                  : ""}
              </span>
              <button
                className="icon-btn"
                aria-label="Dismiss error"
                onClick={() => setError("")}
              >
                <X size={17} />
              </button>
            </div>
          )}
          {section === "Overview" && (
            <div className="metrics">
              {[
                {
                  label: demo ? "Open incidents" : "Open demands",
                  value: demo
                    ? "1"
                    : String(
                        impact.allocations.length ||
                          (impact.status === "NO_OPEN_DEMANDS" ? 0 : "—"),
                      ),
                  Icon: TriangleAlert,
                  color: "rose",
                  foot: demo
                    ? "1 needs your attention"
                    : "This assessment only",
                },
                {
                  label: "Units at risk",
                  value: assessed ? formatQty(total.shortage) : "—",
                  Icon: Box,
                  color: "indigo",
                  foot: "Across assessed demands",
                },
                {
                  label: "Awaiting approval",
                  value: demo ? (review === "Pending review" ? "1" : "0") : "—",
                  Icon: UserCheck,
                  color: "amber",
                  foot: demo
                    ? "Manager review required"
                    : "Queue not connected",
                },
                {
                  label: "Active workflows",
                  value: demo ? "1" : "—",
                  Icon: Activity,
                  color: "indigo",
                  foot: demo
                    ? "Illustrative planning run"
                    : "Queue not connected",
                },
              ].map((x) => (
                <div className="metric" key={x.label}>
                  <span className={`metric-icon ${x.color}`}>
                    <x.Icon size={24} />
                  </span>
                  <div>
                    <span>{x.label}</span>
                    <strong>{x.value}</strong>
                    <small>{x.foot}</small>
                  </div>
                </div>
              ))}
            </div>
          )}
          {(section === "Overview" || section === "Incidents") &&
            (matches ? (
              <div className="dashboard-grid">
                <div className="left-column">
                  <section className="panel incident-panel">{summary}</section>
                  {options}
                </div>
                <div className="right-column">
                  <section className="panel ai-card">
                    <div className="card-heading">
                      <h2 className="flex gap-2 items-center">
                        <Sparkles size={23} />
                        AI brief
                      </h2>
                      <Badge>Advisory</Badge>
                    </div>
                    <p>
                      {demo
                        ? "On-time inbound covers 300 units. A 280-unit gap remains across two production demands. Review the recovery options below."
                        : "Live Gemini explanations are available through the backend planning endpoint. This view has loaded only the impact assessment."}
                    </p>
                    <div className="ai-footnote">
                      <ShieldCheck size={14} />
                      {demo
                        ? "Illustrative summary · demo data"
                        : "No AI explanation requested"}
                    </div>
                  </section>
                  {approval}
                  <section className="panel activity-panel">
                    <div className="card-heading">
                      <h2 className="flex items-center gap-2">
                        <Clock3 size={20} />
                        Recent activity
                      </h2>
                    </div>
                    {demo ? (
                      <ol className="timeline">
                        {[
                          {
                            title: "Assessment completed",
                            sub: "Incident data and supply position analyzed.",
                            time: "12 min ago",
                          },
                          {
                            title: "Recovery options evaluated",
                            sub: "2 independent options for 280 units.",
                            time: "9 min ago",
                          },
                          {
                            title:
                              review === "Pending review"
                                ? "Proposal awaiting approval"
                                : `Demo proposal ${review.toLowerCase()}`,
                            sub: "Warehouse transfer of 280 units.",
                            time: "6 min ago",
                          },
                        ].map((x, i) => (
                          <li key={i}>
                            <i />
                            <div>
                              <strong>{x.title}</strong>
                              <p>{x.sub}</p>
                            </div>
                            <time>{x.time}</time>
                          </li>
                        ))}
                      </ol>
                    ) : (
                      <p className="subtitle">
                        Activity is not inferred from the assessment. Open
                        Record history to read a known incident.
                      </p>
                    )}
                  </section>
                </div>
              </div>
            ) : (
              <section className="panel">
                <Empty title="No matching assessment">
                  Try the plant name or SKU, or clear your search.
                </Empty>
                <button
                  className="button secondary"
                  onClick={() => setSearch("")}
                >
                  Clear search
                </button>
              </section>
            ))}
          {section === "Recovery proposals" && (
            <div className="section-content">
              {options}
              <section className="panel">
                <h2>How recovery decisions work</h2>
                <p className="subtitle mt-3">
                  An assessment identifies the gap. A proposal records the plan
                  and evidence. A procurement manager reviews it before
                  execution revalidates the evidence.
                </p>
                <div className="process-steps">
                  {[
                    "Assess impact",
                    "Evaluate options",
                    "Create proposal",
                    "Manager approval",
                    "Revalidate & execute",
                  ].map((x, i) => (
                    <span key={x}>
                      <b>{i + 1}</b>
                      {x}
                    </span>
                  ))}
                </div>
              </section>
            </div>
          )}
          {section === "Approvals" && (
            <div className="section-content">
              {approval}
              <div className="info-note">
                <ShieldCheck size={19} />
                <p>
                  {demo
                    ? "This is a UI demonstration. Decisions here update this browser view only; no backend approval or order is created."
                    : "Live approval mutations are not wired in this first dashboard release. Use the authenticated backend approval API."}
                </p>
              </div>
            </div>
          )}
          {section === "Workflow runs" && (
            <section className="panel">
              {demo ? (
                <>
                  <div className="card-heading">
                    <h2>Demo planning run</h2>
                    <Badge tone="green">
                      <CheckCircle2 size={13} />
                      Assessment completed
                    </Badge>
                  </div>
                  <div className="process-steps">
                    {[
                      "Assess impact",
                      "Evaluate transfer",
                      "Evaluate purchase",
                      "Summarize findings",
                    ].map((x, i) => (
                      <span key={x}>
                        <b>
                          <Check size={14} />
                        </b>
                        {x}
                      </span>
                    ))}
                  </div>
                  <p className="subtitle">
                    Human approval is still required before mock execution. This
                    illustrative run is not a live queue record.
                  </p>
                </>
              ) : (
                <Empty title="Workflow queue not connected">
                  Use the backend run endpoints for persisted workflow state. A
                  successful impact request does not establish worker activity.
                </Empty>
              )}
            </section>
          )}
          {section === "Record history" && (
            <section className="panel">
              <div className="card-heading">
                <h2>Incident records</h2>
                <Badge tone="muted">Current stored records</Badge>
              </div>
              {demo ? (
                <>
                  <p className="subtitle">
                    Connect your API to retrieve the proposal, decision and
                    execution records of an incident.
                  </p>
                  <button
                    className="button primary mt-5"
                    onClick={() => setDialog("connection")}
                  >
                    <Link2 size={16} />
                    Connect API
                  </button>
                </>
              ) : (
                <>
                  <form onSubmit={getHistory} className="history-form">
                    <label>
                      Incident ID
                      <input
                        required
                        pattern="[0-9a-fA-F-]{36}"
                        value={incidentId}
                        onChange={(e) => setIncidentId(e.target.value)}
                      />
                    </label>
                    <button className="button primary" disabled={busy}>
                      {busy ? (
                        <Loader2 size={16} className="spin" />
                      ) : (
                        <History size={16} />
                      )}
                      Load records
                    </button>
                  </form>
                  {history !== null && (
                    <>
                      <p className="tiny mt-5">
                        First 20 versions. This is a current-record view, not an
                        immutable audit ledger.
                      </p>
                      <pre className="json-preview">
                        {JSON.stringify(history, null, 2)}
                      </pre>
                    </>
                  )}
                </>
              )}
            </section>
          )}
          <footer className="page-footer">
            <span>
              <span className="status-dot" />
              {demo
                ? "Illustrative workspace · no live actions"
                : "Connected impact view · mock ERP backend"}
            </span>
            <button onClick={() => setDialog("connection")}>
              {demo ? "Connect your backend" : "Manage connection"}
              <ArrowRight size={14} />
            </button>
          </footer>
        </main>
      </div>
      {notice && (
        <div className="toast" role="status">
          <CheckCircle2 size={19} />
          {notice}
        </div>
      )}
      {dialog && (
        <Modal
          title={titles[dialog]}
          onClose={() => {
            if (!busy) setDialog(null);
          }}
        >
          {dialog === "connection" ? (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void load(draftToken.trim(), true);
              }}
            >
              <p className="subtitle mb-5">
                Connect to your local FastAPI backend. Your token stays in
                memory and is cleared when this page reloads.
              </p>
              <label>
                Application bearer token
                <input
                  type="password"
                  autoComplete="off"
                  required
                  value={draftToken}
                  onChange={(e) => setDraftToken(e.target.value)}
                  placeholder="Paste the token only — no Bearer prefix"
                />
              </label>
              <div className="form-grid">
                <label>
                  Product SKU
                  <input
                    required
                    value={sku}
                    onChange={(e) => setSku(e.target.value)}
                  />
                </label>
                <label>
                  Plant code
                  <input
                    required
                    value={plant}
                    onChange={(e) => setPlant(e.target.value)}
                  />
                </label>
              </div>
              {error && (
                <p className="form-error" role="alert">
                  {error}
                </p>
              )}
              <div className="dialog-actions">
                {!demo && (
                  <button
                    className="button secondary"
                    type="button"
                    disabled={busy}
                    onClick={disconnect}
                  >
                    <LogOut size={16} />
                    Disconnect
                  </button>
                )}
                <button className="button primary" disabled={busy}>
                  {busy ? (
                    <Loader2 size={16} className="spin" />
                  ) : (
                    <Link2 size={16} />
                  )}
                  Connect & load impact
                </button>
              </div>
              <p className="tiny mt-4">
                Backend URL is configured with NEXT_PUBLIC_API_BASE_URL. Never
                put a token in an environment variable starting with
                NEXT_PUBLIC_.
              </p>
            </form>
          ) : dialog === "incident" ? (
            <>
              <Badge tone={demo ? "blue" : "green"}>
                {demo ? "DEMO ASSESSMENT" : "LIVE ASSESSMENT"}
              </Badge>
              <h3 className="mt-4">{impact.plant_name}</h3>
              <p className="subtitle">
                {impact.sku} · {impact.plant_code}
              </p>
              <div className="detail-stats">
                <div>
                  Remaining demand
                  <strong>{assessed ? formatQty(total.demand) : "—"}</strong>
                </div>
                <div>
                  Shortage
                  <strong>{assessed ? formatQty(total.shortage) : "—"}</strong>
                </div>
              </div>
              <h4>Assessment assumptions</h4>
              <ul className="assumptions">
                {impact.assumptions.map((x) => (
                  <li key={x}>{x}</li>
                ))}
              </ul>
              <button
                className="button secondary mt-5"
                onClick={exportSnapshot}
              >
                <Download size={16} />
                Export assessment JSON
              </button>
            </>
          ) : dialog === "transfer" || dialog === "purchase" ? (
            <>
              <Badge>DEMO OPTION</Badge>
              <h3 className="mt-4">
                {dialog === "transfer"
                  ? "Wattala → Homagama"
                  : "Approved supplier → Homagama"}
              </h3>
              <div className="detail-stats">
                <div>
                  Quantity<strong>280 units</strong>
                </div>
                <div>
                  Lead time
                  <strong>{dialog === "transfer" ? "6" : "7"} hours</strong>
                </div>
              </div>
              <p className="subtitle">
                {dialog === "transfer"
                  ? "Transport cost: LKR 18,000. This excludes the value of existing stock."
                  : "Purchase cost: 280 × LKR 2,100 + LKR 12,000 freight = LKR 600,000."}
              </p>
              <div className="info-note mt-5">
                <TriangleAlert size={19} />
                <p>
                  Independent alternatives with different cost bases.
                  Availability, arrival and evidence must be revalidated before
                  execution.
                </p>
              </div>
              {dialog === "transfer" && (
                <button
                  className="button primary mt-5"
                  onClick={() => setDialog("approval")}
                >
                  Review demo proposal
                  <ArrowRight size={16} />
                </button>
              )}
            </>
          ) : dialog === "approval" ? (
            <>
              <Badge tone="amber">DEMO ONLY · NO BACKEND WRITE</Badge>
              <h3 className="mt-4">Transfer 280 units from Wattala</h3>
              <p className="subtitle mt-2">
                Estimated lead time 6 hours · transport LKR 18,000
              </p>
              {review === "Pending review" ? (
                <>
                  <label className="mt-5">
                    Decision reason
                    <textarea
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                      maxLength={1000}
                      placeholder="Explain why this option is appropriate…"
                    />
                  </label>
                  <div className="dialog-actions">
                    <button
                      className="button secondary"
                      disabled={!reason.trim()}
                      onClick={() => {
                        setReview("Rejected");
                        setNotice(
                          "Demo proposal rejected. No backend changes.",
                        );
                      }}
                    >
                      Reject demo
                    </button>
                    <button
                      className="button primary"
                      disabled={!reason.trim()}
                      onClick={() => {
                        setReview("Approved");
                        setNotice(
                          "Demo proposal approved. No order was created.",
                        );
                      }}
                    >
                      <Check size={16} />
                      Approve demo
                    </button>
                  </div>
                </>
              ) : (
                <div className="info-note mt-5">
                  <CheckCircle2 size={22} />
                  <p>
                    <strong>{review} in this demo</strong>
                    <br />
                    {reason}
                    <br />
                    No backend decision, reservation or order was created.
                  </p>
                </div>
              )}
            </>
          ) : dialog === "new" ? (
            <>
              <p className="subtitle">
                Incident creation is available through the backend API. This
                dashboard release does not submit new incidents.
              </p>
              <div className="info-note mt-5">
                <Link2 size={20} />
                <p>
                  Open your local Swagger page, authorize, then use POST
                  /api/v1/incidents.
                </p>
              </div>
              <a
                className="button primary mt-5"
                href={`${(process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "")}/docs`}
                target="_blank"
                rel="noreferrer"
              >
                Open API docs
                <ExternalLink size={16} />
              </a>
            </>
          ) : (
            <>
              <p className="subtitle">
                {demo
                  ? "Demo workspace notifications"
                  : "No live notification feed is connected."}
              </p>
              {demo && (
                <div className="info-note mt-5">
                  <Bell size={20} />
                  <p>
                    {review === "Pending review"
                      ? "One demo warehouse-transfer proposal is waiting for manager review."
                      : `The demo warehouse-transfer proposal is ${review.toLowerCase()}.`}
                  </p>
                </div>
              )}
            </>
          )}
        </Modal>
      )}
    </div>
  );
}
