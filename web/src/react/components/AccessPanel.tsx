import { useMemo, useState } from "react";
import { CheckCircle, MagnifyingGlass, ShieldCheck, UserCircle, UsersThree, WarningCircle } from "@phosphor-icons/react";
import type { Dict, Principal } from "../types";

type Props = {
  principal: Principal;
  snapshot: Dict;
  onChange(change: Dict): Promise<void>;
  embedded?: boolean;
};

const ROLES = ["student", "ta", "professor", "uni_admin", "admin"];

function userName(user: Dict): string {
  return String(user.display_name || user.email || user.user_id || "Unknown user");
}

function userEmail(user: Dict): string {
  return String(user.email || user.user_id || "").replace(/^email:/, "");
}

function userStatus(user: Dict): { label: string; tone: string } {
  if (Number(user.disabled || 0)) return { label: "Needs approval", tone: "warning" };
  if (!user.email_verified_at && String(user.provider || "email") === "email") return { label: "Email pending", tone: "neutral" };
  return { label: "Approved", tone: "success" };
}

function roleLabel(role: unknown): string {
  return String(role || "student").replaceAll("_", " ");
}

export function AccessPanel({ principal, snapshot, onChange, embedded = false }: Props) {
  const users = useMemo(() => (snapshot.users || []) as Dict[], [snapshot.users]);
  const groups = useMemo(() => (snapshot.groups || []) as Dict[], [snapshot.groups]);
  const memberships = (snapshot.memberships || []) as Dict[];
  const bindings = (snapshot.role_bindings || []) as Dict[];
  const invites = useMemo(() => (snapshot.invite_codes || []) as Dict[], [snapshot.invite_codes]);
  const accountTenants = useMemo(() => (snapshot.account_tenants || []) as Dict[], [snapshot.account_tenants]);
  const [groupName, setGroupName] = useState("");
  const [selectedUser, setSelectedUser] = useState("");
  const [selectedGroup, setSelectedGroup] = useState("");
  const [selectedRole, setSelectedRole] = useState("student");
  const [inviteCode, setInviteCode] = useState("");
  const [inviteLabel, setInviteLabel] = useState("");
  const [selectedInvite, setSelectedInvite] = useState("");
  const [staffId, setStaffId] = useState("");
  const [studentGroupId, setStudentGroupId] = useState("");
  const [scopeType, setScopeType] = useState("tenant");
  const [scopeId, setScopeId] = useState("*");
  const [search, setSearch] = useState("");
  const tenantIds = useMemo(
    () => Array.from(new Set([principal.tenant_id, ...users.map((row) => String(row.tenant_id || "")), ...groups.map((row) => String(row.tenant_id || "")), ...accountTenants.map((row) => String(row.tenant_id || ""))].filter(Boolean))).sort(),
    [accountTenants, groups, principal.tenant_id, users],
  );
  const [selectedTenant, setSelectedTenant] = useState(principal.tenant_id);
  const tenantId = principal.is_global_admin && tenantIds.includes(selectedTenant) ? selectedTenant : principal.tenant_id;
  const tenantUsers = useMemo(
    () => accountTenants
      .filter((account) => String(account.tenant_id) === tenantId)
      .map((account): Dict => ({
        ...(users.find((user) => String(user.user_id) === String(account.user_id)) || {}),
        ...account,
      })),
    [accountTenants, tenantId, users],
  );
  const filteredUsers = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return needle ? tenantUsers.filter((user) => `${userName(user)} ${userEmail(user)} ${String(user.role || "")}`.toLowerCase().includes(needle)) : tenantUsers;
  }, [search, tenantUsers]);
  const tenantGroups = useMemo(() => groups.filter((group) => String(group.tenant_id) === tenantId), [groups, tenantId]);
  const tenantInvites = useMemo(() => invites.filter((invite) => String(invite.tenant_id) === tenantId), [invites, tenantId]);
  const currentUser = tenantUsers.find((user) => String(user.user_id) === selectedUser);
  const disabledCount = tenantUsers.filter((user) => Number(user.disabled || 0)).length;
  const emailPendingCount = tenantUsers.filter((user) => !Number(user.disabled || 0) && !user.email_verified_at && String(user.provider || "email") === "email").length;
  const approvedCount = tenantUsers.length - disabledCount - emailPendingCount;

  const chooseUser = (user: Dict) => {
    setSelectedUser(String(user.user_id));
    setSelectedRole(String(user.role || "student"));
    setStaffId(String(user.staff_id ?? ""));
    setStudentGroupId(String(user.student_group_id ?? ""));
  };

  const roleOptions = ROLES.filter((role) => role !== "admin" || principal.is_global_admin);

  return (
    <div className={`access-console ${embedded ? "embedded" : "standalone"}`}>
      {!embedded ? (
        <header className="access-page-heading">
          <div>
            <span className="eyebrow">Organization management</span>
            <h2>People &amp; access</h2>
            <p>Approve accounts, assign responsibilities, and control who can work in each organization.</p>
          </div>
          {principal.is_global_admin ? (
            <label className="tenant-picker">
              Organization
              <select value={selectedTenant} onChange={(event) => {
                setSelectedTenant(event.target.value);
                setSelectedUser("");
                setSelectedGroup("");
                setSelectedInvite("");
              }}>
                {tenantIds.map((id) => <option key={id} value={id}>{id}</option>)}
              </select>
            </label>
          ) : null}
        </header>
      ) : principal.is_global_admin ? (
        <div className="access-toolbar">
          <label className="tenant-picker">
            Organization
            <select value={selectedTenant} onChange={(event) => {
              setSelectedTenant(event.target.value);
              setSelectedUser("");
              setSelectedGroup("");
              setSelectedInvite("");
            }}>
              {tenantIds.map((id) => <option key={id} value={id}>{id}</option>)}
            </select>
          </label>
          <span>Changes apply immediately to <strong>{tenantId}</strong>.</span>
        </div>
      ) : null}

      <div className="access-summary" aria-label="Access summary">
        <article><span className="summary-icon success"><CheckCircle weight="fill" /></span><div><strong>{approvedCount}</strong><span>Approved</span></div></article>
        <article><span className="summary-icon warning"><WarningCircle weight="fill" /></span><div><strong>{disabledCount}</strong><span>Needs approval</span></div></article>
        <article><span className="summary-icon neutral"><UserCircle weight="fill" /></span><div><strong>{emailPendingCount}</strong><span>Email pending</span></div></article>
        <article><span className="summary-icon accent"><UsersThree weight="fill" /></span><div><strong>{tenantGroups.length}</strong><span>Groups</span></div></article>
      </div>

      <div className="access-directory-layout">
        <section className="access-directory-card" aria-labelledby="people-directory-heading">
          <div className="access-section-heading">
            <div><h3 id="people-directory-heading">People</h3><p>{tenantUsers.length} accounts in this organization</p></div>
          </div>
          <label className="access-search">
            <MagnifyingGlass aria-hidden="true" />
            <span className="sr-only">Search people</span>
            <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search name, email, or role" />
          </label>
          <div className="people-list">
            {filteredUsers.length ? filteredUsers.map((user) => {
              const status = userStatus(user);
              const active = String(user.user_id) === selectedUser;
              return (
                <button type="button" className={`person-row ${active ? "selected" : ""}`} key={String(user.user_id)} onClick={() => chooseUser(user)}>
                  <span className="person-avatar">{userName(user).slice(0, 1).toUpperCase()}</span>
                  <span className="person-copy"><strong>{userName(user)}</strong><small>{userEmail(user)}</small></span>
                  <span className="person-meta"><span className={`status-pill ${status.tone}`}>{status.label}</span><small>{roleLabel(user.role)}</small></span>
                </button>
              );
            }) : <div className="access-empty">No people match this search.</div>}
          </div>
        </section>

        <section className="access-editor-card" aria-labelledby="access-editor-heading">
          {currentUser ? (
            <>
              <div className="selected-person-heading">
                <span className="person-avatar large">{userName(currentUser).slice(0, 1).toUpperCase()}</span>
                <div><span className="eyebrow">Edit access</span><h3 id="access-editor-heading">{userName(currentUser)}</h3><p>{userEmail(currentUser)}</p></div>
                <span className={`status-pill ${userStatus(currentUser).tone}`}>{userStatus(currentUser).label}</span>
              </div>

              {Number(currentUser.disabled || 0) ? (
                <div className="approval-callout">
                  <ShieldCheck aria-hidden="true" weight="fill" />
                  <div><strong>This person is waiting for access.</strong><span>Approve them to allow sign-in to {tenantId}.</span></div>
                  <button type="button" onClick={() => void onChange({ action: "set_disabled", user_id: selectedUser, disabled: false, tenant_id: tenantId })}>Approve access</button>
                </div>
              ) : null}

              <div className="access-form-grid">
                <label>Organization role<select value={selectedRole} onChange={(event) => setSelectedRole(event.target.value)}>{roleOptions.map((role) => <option key={role} value={role}>{roleLabel(role)}</option>)}</select></label>
                <button type="button" onClick={() => void onChange({ action: "set_role", user_id: selectedUser, role: selectedRole, tenant_id: tenantId })}>Save role</button>
                <label>Planora group<select value={selectedGroup} onChange={(event) => setSelectedGroup(event.target.value)}><option value="">Select group</option>{tenantGroups.map((group) => <option key={String(group.group_id)} value={String(group.group_id)}>{String(group.name)}</option>)}</select></label>
                <button type="button" className="secondary-button" disabled={!selectedGroup} onClick={() => void onChange({ action: "set_membership", user_id: selectedUser, group_id: selectedGroup, enabled: true, tenant_id: tenantId })}>Add to group</button>
                <label>Staff ID<input inputMode="numeric" value={staffId} onChange={(event) => setStaffId(event.target.value)} placeholder="Professor or TA ID" /></label>
                <label>Student group ID<input inputMode="numeric" value={studentGroupId} onChange={(event) => setStudentGroupId(event.target.value)} placeholder="Schedule group ID" /></label>
                <button type="button" className="secondary-button wide" onClick={() => void onChange({ action: "link_schedule_identity", user_id: selectedUser, staff_id: staffId, student_group_id: studentGroupId, tenant_id: tenantId })}>Save schedule identity</button>
              </div>
              <div className="access-danger-zone">
                <div><strong>Account controls</strong><span>Pausing access preserves schedules, membership records, and audit history.</span></div>
                <button type="button" className="secondary-button" disabled={selectedUser === principal.user_id || Number(currentUser.disabled || 0) === 1} onClick={() => {
                  if (window.confirm("Pause this account? The user will lose access, but audit history and existing records stay intact.")) {
                    void onChange({ action: "set_disabled", user_id: selectedUser, disabled: true, tenant_id: tenantId });
                  }
                }}>Pause access</button>
                {principal.is_global_admin ? <button type="button" className="danger-button" disabled={selectedUser === principal.user_id} onClick={() => {
                  if (window.confirm(`Permanently delete ${userName(currentUser)}? Login sessions, memberships, tenant links, and authentication tokens will be removed.`)) {
                    void onChange({ action: "delete_user", user_id: selectedUser, tenant_id: tenantId }).then(() => setSelectedUser(""));
                  }
                }}>Delete account</button> : null}
              </div>
            </>
          ) : (
            <div className="access-editor-empty">
              <span><UserCircle aria-hidden="true" weight="duotone" /></span>
              <h3 id="access-editor-heading">Select a person</h3>
              <p>Choose someone from the directory to approve their account, change their role, or connect their schedule identity.</p>
            </div>
          )}
        </section>
      </div>

      <div className="access-management-grid">
        <section className="access-tool-card">
          <div className="access-section-heading"><div><h3>Groups</h3><p>Organize people for teaching and scheduling.</p></div></div>
          <div className="compact-form-row"><label><span>Group name</span><input value={groupName} onChange={(event) => setGroupName(event.target.value)} placeholder="Computer Science staff" /></label><button type="button" disabled={!groupName.trim()} onClick={() => void onChange({ action: "create_group", name: groupName.trim(), tenant_id: tenantId }).then(() => setGroupName(""))}>Create group</button></div>
          <div className="mini-list">{tenantGroups.length ? tenantGroups.map((group) => <span key={String(group.group_id)}><UsersThree aria-hidden="true" /><strong>{String(group.name)}</strong></span>) : <p>No groups have been created yet.</p>}</div>
        </section>

        <section className="access-tool-card">
          <div className="access-section-heading"><div><h3>Scoped group role</h3><p>Grant a group responsibility for a tenant or academic scope.</p></div></div>
          <div className="compact-form-grid">
            <label>Group<select value={selectedGroup} onChange={(event) => setSelectedGroup(event.target.value)}><option value="">Select group</option>{tenantGroups.map((group) => <option key={String(group.group_id)} value={String(group.group_id)}>{String(group.name)}</option>)}</select></label>
            <label>Role<select value={selectedRole} onChange={(event) => setSelectedRole(event.target.value)}>{roleOptions.map((role) => <option key={role} value={role}>{roleLabel(role)}</option>)}</select></label>
            <label>Scope<select value={scopeType} onChange={(event) => setScopeType(event.target.value)}><option value="tenant">Entire tenant</option><option value="department">Department</option><option value="program">Program</option><option value="course">Course</option><option value="group">Student group</option></select></label>
            <label>Scope ID<input value={scopeId} onChange={(event) => setScopeId(event.target.value)} disabled={scopeType === "tenant"} /></label>
            <button type="button" className="wide" disabled={!selectedGroup} onClick={() => void onChange({ action: "bind_role", principal_type: "group", principal_id: selectedGroup, role: selectedRole, scope_type: scopeType, scope_id: scopeType === "tenant" ? "*" : scopeId, tenant_id: tenantId })}>Save group role</button>
          </div>
        </section>

        <section className="access-tool-card wide-card">
          <div className="access-section-heading"><div><h3>Invitations</h3><p>Create, rotate, and revoke group invitation codes. Existing members are not affected when a code changes.</p></div></div>
          <div className="compact-form-grid invite-form">
            <label>Group<select value={selectedGroup} onChange={(event) => setSelectedGroup(event.target.value)}><option value="">Select group</option>{tenantGroups.map((group) => <option key={String(group.group_id)} value={String(group.group_id)}>{String(group.name)}</option>)}</select></label>
            <label>Invite role<select value={selectedRole} onChange={(event) => setSelectedRole(event.target.value)}>{ROLES.filter((role) => role !== "admin" && (role !== "uni_admin" || principal.is_global_admin || principal.role === "uni_admin")).map((role) => <option key={role} value={role}>{roleLabel(role)}</option>)}</select></label>
            <label>Label<input value={inviteLabel} onChange={(event) => setInviteLabel(event.target.value)} placeholder="Fall 2026 CS students" /></label>
            <label>Custom code<input value={inviteCode} onChange={(event) => setInviteCode(event.target.value)} placeholder="Leave blank for random" autoComplete="off" /></label>
            <button type="button" disabled={!selectedGroup} onClick={() => void onChange({ action: "create_invite", group_id: selectedGroup, role: selectedRole, label: inviteLabel, code: inviteCode, tenant_id: tenantId })}>Create invitation</button>
            <label>Existing invitation<select value={selectedInvite} onChange={(event) => setSelectedInvite(event.target.value)}><option value="">Select invitation</option>{tenantInvites.map((invite) => <option key={String(invite.invite_id)} value={String(invite.invite_id)}>{String(invite.label || invite.invite_id)} · {roleLabel(invite.role)}</option>)}</select></label>
            <button type="button" className="secondary-button" disabled={!selectedInvite} onClick={() => void onChange({ action: "rotate_invite", invite_id: selectedInvite, code: inviteCode, label: inviteLabel || undefined, tenant_id: tenantId })}>Rotate code</button>
            <button type="button" className="secondary-button" disabled={!selectedInvite} onClick={() => void onChange({ action: "set_invite_disabled", invite_id: selectedInvite, disabled: true, tenant_id: tenantId })}>Disable invitation</button>
          </div>
          {snapshot.new_invite_code ? <div className="inline-note">New invitation code: <strong>{String(snapshot.new_invite_code)}</strong></div> : null}
        </section>
      </div>

      <p className="access-footnote">{memberships.filter((row) => String(row.tenant_id) === tenantId).length} memberships · {bindings.filter((row) => String(row.tenant_id) === tenantId).length} scoped roles · {tenantInvites.length} invitation codes</p>
    </div>
  );
}
