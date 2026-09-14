import type { Principal, ViewKey } from "../types";
import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  CalendarBlank,
  CaretLeft,
  CaretRight,
  ChartLineUp,
  CloudCheck,
  Database,
  FolderOpen,
  List,
  Moon,
  Question,
  SignOut,
  SlidersHorizontal,
  ShieldStar,
  Sun,
  UserCircle,
  UsersThree,
  WarningDiamond,
  X,
} from "@phosphor-icons/react";
import type { Icon } from "@phosphor-icons/react";

type AuthView = {
  key: ViewKey;
  label: string;
  description: string;
  icon: Icon;
  adminOnly?: boolean;
  permission?: string;
};

const AUTH_VIEW_GROUPS: Array<{ label: string; items: AuthView[] }> = [
  {
    label: "Planning",
    items: [
      { key: "workspace", label: "Schedule", description: "Plan and repair", icon: CalendarBlank },
      { key: "operations", label: "Data", description: "Courses and resources", icon: Database },
      { key: "review", label: "Review", description: "Conflicts and quality", icon: WarningDiamond },
      { key: "projects", label: "Projects", description: "Drafts and releases", icon: FolderOpen },
      { key: "fairness", label: "Insights", description: "Fairness and workload", icon: ChartLineUp },
      { key: "settings", label: "Advanced", description: "Specialist controls", icon: SlidersHorizontal },
    ],
  },
  {
    label: "Management",
    items: [
      { key: "access", label: "People & access", description: "Roles, groups and invites", icon: UsersThree, permission: "access:manage" },
      { key: "parity", label: "Platform", description: "Feature coverage", icon: CloudCheck },
      { key: "account", label: "Account", description: "Profile and security", icon: UserCircle },
    ],
  },
  {
    label: "Administration",
    items: [
      { key: "admin", label: "Super admin", description: "People, system and audit", icon: ShieldStar, adminOnly: true },
    ],
  },
];

const AUTH_VIEWS = AUTH_VIEW_GROUPS.flatMap((group) => group.items);

const PUBLIC_VIEWS: Array<{ key: ViewKey; label: string }> = [
  { key: "home", label: "Home" },
  { key: "faq", label: "FAQ" },
  { key: "privacy", label: "Privacy" },
];

type Props = {
  principal: Principal;
  activeView: ViewKey;
  authenticated: boolean;
  theme: "light" | "dark";
  analyticsConsent: "pending" | "granted" | "denied";
  onViewChange(view: ViewKey): void;
  onSignOut(): void;
  onThemeToggle(): void;
  onTutorialOpen(): void;
  onAnalyticsConsentChange(consent: "pending" | "granted" | "denied"): void;
  children: ReactNode;
};

export function AppShell({
  principal,
  activeView,
  authenticated,
  theme,
  analyticsConsent,
  onViewChange,
  onSignOut,
  onThemeToggle,
  onTutorialOpen,
  onAnalyticsConsentChange,
  children,
}: Props) {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const workspaceNavRef = useRef<HTMLElement>(null);
  const canSeeView = (view: AuthView) =>
    (!view.adminOnly || principal.is_global_admin) &&
    (!view.permission || principal.permissions.includes(view.permission));
  const activeItem = AUTH_VIEWS.find((view) => view.key === activeView);
  const displayName = principal.user_id.replace(/^email:/, "").split("@")[0] || "Account";
  const roleLabel = principal.role.replaceAll("_", " ");

  useEffect(() => {
    setMobileNavOpen(false);
    workspaceNavRef.current?.querySelector<HTMLElement>("[aria-current='page']")?.scrollIntoView({ block: "nearest" });
  }, [activeView]);

  const changeView = (view: ViewKey) => {
    setMobileNavOpen(false);
    onViewChange(view);
  };

  return (
    <div className={`app-frame ${authenticated ? `authenticated-frame sidebar-${sidebarCollapsed ? "collapsed" : "expanded"}` : "public-frame"}`}>
      <header className="site-nav">
        <button type="button" className="brand-link" onClick={() => changeView(authenticated ? "workspace" : "home")} aria-label="Planora home">
          <img src="/app-icon.png" alt="" />
          <span className="brand-wordmark">
            <strong>Planora</strong>
            {authenticated ? <small>Academic scheduling</small> : null}
          </span>
        </button>
        {authenticated ? (
          <div className="nav-page-context" aria-live="polite">
            <span>{principal.tenant_id}</span>
            <strong>Academic planning / {activeItem?.label || "Planora"}</strong>
          </div>
        ) : (
          <nav className="public-nav-links" aria-label="Main navigation">
            {PUBLIC_VIEWS.map((item) => (
              <button
                key={item.key}
                type="button"
                className={activeView === item.key ? "active" : ""}
                onClick={() => changeView(item.key)}
              >
                {item.label}
              </button>
            ))}
          </nav>
        )}
        <div className="nav-actions">
          {authenticated ? <button type="button" className="quiet-button tutorial-trigger" onClick={onTutorialOpen}><Question aria-hidden="true" weight="bold" />How it works</button> : null}
          <button type="button" className="theme-toggle icon-button" onClick={onThemeToggle} aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}>
            {theme === "dark" ? <Sun aria-hidden="true" weight="bold" /> : <Moon aria-hidden="true" weight="bold" />}
          </button>
          {authenticated ? (
            <>
              <div className="header-profile" title={`${principal.user_id} · ${principal.tenant_id}`}>
                <span>{displayName.slice(0, 1).toUpperCase()}</span>
                <div>
                  <strong>{displayName}</strong>
                  <small>{roleLabel}</small>
                </div>
              </div>
              <button
                type="button"
                className={`mobile-nav-toggle icon-button ${mobileNavOpen ? "active" : ""}`}
                aria-label="Toggle workspace navigation"
                aria-expanded={mobileNavOpen}
                onClick={() => setMobileNavOpen((open) => !open)}
              >
                {mobileNavOpen ? <X aria-hidden="true" weight="bold" /> : <List aria-hidden="true" weight="bold" />}
              </button>
            </>
          ) : (
            <button type="button" className={activeView === "login" ? "active nav-auth-button" : "nav-auth-button"} onClick={() => changeView("login")}>Sign in</button>
          )}
        </div>
      </header>
      <div className="app-body">
        {authenticated ? (
          <>
            <button
              type="button"
              className={`nav-scrim ${mobileNavOpen ? "visible" : ""}`}
              aria-label="Close workspace navigation"
              onClick={() => setMobileNavOpen(false)}
            />
            <aside className={`workspace-sidebar ${mobileNavOpen ? "open" : ""}`}>
              <nav className="workspace-nav" aria-label="Workspace navigation" ref={workspaceNavRef}>
                {AUTH_VIEW_GROUPS.map((group) => {
                  const items = group.items.filter(canSeeView);
                  return items.length ? (
                    <div className="workspace-nav-group" key={group.label}>
                      <span className="workspace-nav-group-label">{group.label}</span>
                      {items.map((item) => (
                        <button
                          key={item.key}
                          type="button"
                          className={activeView === item.key ? "active" : ""}
                          aria-current={activeView === item.key ? "page" : undefined}
                          title={sidebarCollapsed ? item.label : undefined}
                          onClick={() => changeView(item.key)}
                        >
                          <item.icon className="workspace-nav-icon" aria-hidden="true" weight={activeView === item.key ? "fill" : "regular"} />
                          <span>
                            <strong>{item.label}</strong>
                            <small>{item.description}</small>
                          </span>
                        </button>
                      ))}
                    </div>
                  ) : null;
                })}
              </nav>
              <div className="sidebar-account">
                <button type="button" className="sidebar-profile" onClick={() => changeView("account")}>
                  <span className="account-avatar">{displayName.slice(0, 1).toUpperCase()}</span>
                  <span>
                    <strong>{displayName}</strong>
                    <small>{principal.tenant_id}</small>
                  </span>
                </button>
                <button type="button" className="sidebar-signout" onClick={onSignOut}><SignOut aria-hidden="true" />Sign out</button>
                <button
                  type="button"
                  className="sidebar-collapse"
                  aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
                  aria-expanded={!sidebarCollapsed}
                  onClick={() => setSidebarCollapsed((collapsed) => !collapsed)}
                >
                  {sidebarCollapsed ? <CaretRight aria-hidden="true" weight="bold" /> : <CaretLeft aria-hidden="true" weight="bold" />}
                  <span>{sidebarCollapsed ? "Expand" : "Collapse"}</span>
                </button>
              </div>
            </aside>
          </>
        ) : null}
        <main className={`page-content view-${activeView}`}>{children}</main>
      </div>
      <footer className="site-footer">
        <span>Planora academic scheduling</span>
        <button
          type="button"
          className="footer-link-button"
          onClick={() => onAnalyticsConsentChange(analyticsConsent === "granted" ? "denied" : "granted")}
        >
          Analytics: {analyticsConsent === "granted" ? "On" : "Off"}
        </button>
        <button type="button" className="footer-link-button" onClick={() => changeView("privacy")}>
          Privacy
        </button>
        <button type="button" className="footer-link-button" onClick={() => changeView("faq")}>
          FAQ
        </button>
        <span>© Mahmoud Elfeel</span>
      </footer>
    </div>
  );
}
