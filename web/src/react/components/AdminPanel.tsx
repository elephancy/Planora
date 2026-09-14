import { useState } from "react";
import { ChartBar, Gauge, ShieldCheck, UsersThree } from "@phosphor-icons/react";
import type { Dict, Principal } from "../types";
import { AccessPanel } from "./AccessPanel";

function rows(value: unknown): Dict[] {
  return Array.isArray(value) ? (value as Dict[]) : [];
}

function asDict(value: unknown): Dict {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Dict) : {};
}

function asNumber(value: unknown): number | null {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function formatBytes(value: unknown): string {
  const bytes = asNumber(value);
  if (bytes === null) return "n/a";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let scaled = bytes;
  let index = 0;
  while (scaled >= 1024 && index < units.length - 1) {
    scaled /= 1024;
    index += 1;
  }
  return `${scaled >= 10 || index === 0 ? scaled.toFixed(0) : scaled.toFixed(1)} ${units[index]}`;
}

function formatPercent(value: unknown): string {
  const percent = asNumber(value);
  return percent === null ? "n/a" : `${percent.toFixed(percent >= 10 ? 0 : 1)}%`;
}

function formatDuration(seconds: unknown): string {
  const total = asNumber(seconds);
  if (total === null) return "n/a";
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

function UsageBar({ label, percent, detail }: { label: string; percent: unknown; detail: string }) {
  const value = Math.max(0, Math.min(100, asNumber(percent) ?? 0));
  const state = value >= 90 ? "danger" : value >= 75 ? "warn" : "ok";
  return (
    <div className="usage-row">
      <div className="usage-row-header"><span>{label}</span><strong>{formatPercent(percent)}</strong></div>
      <div className={`usage-track ${state}`} aria-label={`${label} ${formatPercent(percent)}`} role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={value}><span style={{ width: `${value}%` }} /></div>
      <small>{detail}</small>
    </div>
  );
}

type AdminTab = "people" | "system" | "audit";

export function AdminPanel({
  principal,
  accessSnapshot,
  auditEvents,
  system,
  systemStatus,
  analytics,
  onAccessChange,
  onRefresh,
  onEmailTest,
  onDownload,
}: {
  principal: Principal;
  accessSnapshot: Dict;
  auditEvents: Dict[];
  system: Dict;
  systemStatus: Dict;
  analytics: Dict;
  onAccessChange(change: Dict): Promise<void>;
  onRefresh(filters: Dict): Promise<void>;
  onEmailTest(email: string): Promise<void>;
  onDownload(path: string, filename: string): Promise<void>;
}) {
  const [activeTab, setActiveTab] = useState<AdminTab>("people");
  const [filters, setFilters] = useState({ days: "30", tenant_id: "", event_name: "", path: "", action: "", user_id: "" });
  const [email, setEmail] = useState("");
  if (!principal.is_global_admin) {
    return <section className="panel"><h2>Super admin</h2><p>This view is only available to global administrators.</p></section>;
  }

  const topPaths = rows(analytics.top_paths);
  const topEvents = rows(analytics.top_events);
  const byDay = rows(analytics.by_day);
  const statusApi = asDict(systemStatus.api);
  const disk = asDict(systemStatus.disk);
  const memory = asDict(systemStatus.memory);
  const containerMemory = asDict(memory.container);
  const hostMemory = asDict(memory.host);
  const jobs = asDict(systemStatus.jobs);
  const netdata = asDict(systemStatus.netdata);
  const netdataUrl = String(netdata.url || "");
  const database = asDict(system.database);
  const systemDatabase = asDict(systemStatus.database);

  return (
    <section className="admin-console">
      <header className="admin-page-header">
        <div>
          <span className="eyebrow"><ShieldCheck aria-hidden="true" weight="fill" /> Protected workspace</span>
          <h1>Super admin</h1>
          <p>Manage people across organizations, monitor the platform, and review sensitive activity.</p>
        </div>
        <span className="admin-identity"><strong>{principal.user_id.replace(/^email:/, "")}</strong><small>Global administrator</small></span>
      </header>

      <div className="admin-tabs" role="tablist" aria-label="Super admin sections">
        <button type="button" role="tab" aria-selected={activeTab === "people"} className={activeTab === "people" ? "active" : ""} onClick={() => setActiveTab("people")}><UsersThree aria-hidden="true" />People & access</button>
        <button type="button" role="tab" aria-selected={activeTab === "system"} className={activeTab === "system" ? "active" : ""} onClick={() => setActiveTab("system")}><Gauge aria-hidden="true" />System health</button>
        <button type="button" role="tab" aria-selected={activeTab === "audit"} className={activeTab === "audit" ? "active" : ""} onClick={() => setActiveTab("audit")}><ChartBar aria-hidden="true" />Audit & analytics</button>
      </div>

      <div className="admin-tab-content" role="tabpanel">
        {activeTab === "people" ? <AccessPanel principal={principal} snapshot={accessSnapshot} onChange={onAccessChange} embedded /> : null}

        {activeTab === "system" ? (
          <div className="admin-section-stack">
            <div className="admin-stat-grid">
              <article><span>API status</span><strong className={system.ok ? "status-online" : ""}>{system.ok ? "Online" : "Unknown"}</strong></article>
              <article><span>API uptime</span><strong>{formatDuration(statusApi.uptime_seconds)}</strong></article>
              <article><span>Environment</span><strong>{statusApi.production ? "Production" : "Development"}</strong></article>
              <article><span>Schema</span><strong>v{String(database.schema_version ?? "n/a")}</strong></article>
              <article><span>Database size</span><strong>{formatBytes(systemDatabase.size_bytes)}</strong></article>
              <article><span>Active jobs</span><strong>{String(jobs.active ?? 0)} / {String(jobs.active_limit_per_tenant ?? "n/a")}</strong></article>
            </div>

            <section className="admin-card">
              <div className="admin-card-heading"><div><h2>Runtime health</h2><p>Fast signals from the API container and its data volume.</p></div>{netdataUrl ? <a className="secondary-link-button" href={netdataUrl} target="_blank" rel="noreferrer">Open Netdata</a> : null}</div>
              <div className="status-grid">
                <UsageBar label="Data volume disk" percent={disk.used_percent} detail={`${formatBytes(disk.used_bytes)} used, ${formatBytes(disk.free_bytes)} free`} />
                <UsageBar label="API container memory" percent={containerMemory.used_percent} detail={`${formatBytes(containerMemory.used_bytes)} used of ${formatBytes(containerMemory.limit_bytes)}`} />
                <UsageBar label="Host memory" percent={hostMemory.used_percent} detail={`${formatBytes(hostMemory.used_bytes)} used, ${formatBytes(hostMemory.available_bytes)} available`} />
              </div>
              <div className="admin-path"><span>Database path</span><code title={String(database.path ?? "n/a")}>{String(database.path ?? "n/a")}</code></div>
            </section>

            <section className="admin-card compact-card">
              <div className="admin-card-heading"><div><h2>Email delivery test</h2><p>Send a real delivery check after configuring SPF, DKIM, and DMARC.</p></div></div>
              <div className="admin-inline-form"><label><span>Recipient</span><input type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="admin@example.edu" /></label><button type="button" disabled={!email.includes("@")} onClick={() => void onEmailTest(email)}>Send test email</button></div>
            </section>
          </div>
        ) : null}

        {activeTab === "audit" ? (
          <div className="admin-section-stack">
            <div className="admin-stat-grid audit-stats">
              <article><span>Audit records</span><strong>{auditEvents.length}</strong></article>
              <article><span>Analytics events</span><strong>{String(analytics.events ?? 0)}</strong></article>
              <article><span>Unique visitors</span><strong>{String(analytics.visitors ?? 0)}</strong></article>
            </div>

            <section className="admin-card">
              <div className="admin-card-heading"><div><h2>Filters & exports</h2><p>Narrow the activity window or download records for offline review.</p></div></div>
              <div className="admin-filter-grid">
                <label>Days<input value={filters.days} onChange={(event) => setFilters({ ...filters, days: event.target.value })} inputMode="numeric" /></label>
                <label>Organization<input value={filters.tenant_id} onChange={(event) => setFilters({ ...filters, tenant_id: event.target.value })} placeholder="All organizations" /></label>
                <label>Event<input value={filters.event_name} onChange={(event) => setFilters({ ...filters, event_name: event.target.value })} placeholder="page_view" /></label>
                <label>Path<input value={filters.path} onChange={(event) => setFilters({ ...filters, path: event.target.value })} placeholder="/workspace" /></label>
                <label>Audit action<input value={filters.action} onChange={(event) => setFilters({ ...filters, action: event.target.value })} placeholder="auth.login" /></label>
                <label>Audit user<input value={filters.user_id} onChange={(event) => setFilters({ ...filters, user_id: event.target.value })} placeholder="email:user@example.edu" /></label>
              </div>
              <div className="admin-filter-actions"><button type="button" onClick={() => void onRefresh(filters)}>Apply filters</button><button type="button" className="secondary-button" onClick={() => void onDownload(`/analytics/export.csv?${new URLSearchParams(filters).toString()}`, "planora-analytics.csv")}>Export analytics</button><button type="button" className="secondary-button" onClick={() => void onDownload(`/audit.csv?${new URLSearchParams(filters).toString()}`, "planora-audit.csv")}>Export audit log</button></div>
            </section>

            <div className="admin-report-grid">
              <section className="admin-card"><h2>Top pages</h2><div className="table-like compact"><div className="table-row header"><span>Path</span><span>Events</span><span>Visitors</span></div>{topPaths.length ? topPaths.map((row) => <div className="table-row" key={String(row.path)}><span>{String(row.path)}</span><span>{String(row.events)}</span><span>{String(row.visitors)}</span></div>) : <div className="empty-row">No page analytics yet.</div>}</div></section>
              <section className="admin-card"><h2>Top events</h2><div className="table-like compact"><div className="table-row header"><span>Event</span><span>Count</span><span>Window</span></div>{topEvents.length ? topEvents.map((row) => <div className="table-row" key={String(row.event_name)}><span>{String(row.event_name)}</span><span>{String(row.events)}</span><span>{String(analytics.days ?? 30)} days</span></div>) : <div className="empty-row">No event analytics yet.</div>}</div></section>
            </div>

            <section className="admin-card"><h2>Daily traffic</h2><div className="table-like compact"><div className="table-row header"><span>Day</span><span>Events</span><span>Visitors</span></div>{byDay.length ? byDay.map((row) => <div className="table-row" key={String(row.day)}><span>{String(row.day)}</span><span>{String(row.events)}</span><span>{String(row.visitors)}</span></div>) : <div className="empty-row">No daily analytics yet.</div>}</div></section>
            <section className="admin-card"><div className="admin-card-heading"><div><h2>Audit log</h2><p>Security-sensitive actions across all organizations.</p></div></div><div className="table-like"><div className="table-row header"><span>Action</span><span>Organization</span><span>User</span></div>{auditEvents.length ? auditEvents.map((event) => <div className="table-row" key={String(event.id)}><span>{String(event.action)}</span><span>{String(event.tenant_id)}</span><span>{String(event.user_id)}</span></div>) : <div className="empty-row">No audit events yet.</div>}</div></section>
          </div>
        ) : null}
      </div>
    </section>
  );
}
