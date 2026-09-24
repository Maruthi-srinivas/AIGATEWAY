import { NavLink, Outlet, useLocation } from "react-router-dom";

import { logout } from "../api/client";
import { useSession } from "../api/session";
import { LayerToggle } from "../components/LayerToggle";

const explainLinks = [
  { to: "/", label: "Map", end: true },
  { to: "/flow", label: "Chat path", end: false },
  { to: "/failures", label: "Failures", end: false },
];

const tryLinks = [
  { to: "/try", label: "Chat", end: true },
  { to: "/try/conversations", label: "Conversations", end: false },
  { to: "/try/documents", label: "Documents", end: false },
  { to: "/try/policy", label: "Policy", end: false },
  { to: "/try/audit", label: "Audit", end: false },
  { to: "/try/ready", label: "Ready", end: false },
];

export function Shell() {
  const location = useLocation();
  const session = useSession();
  const explain = !location.pathname.startsWith("/try");
  const links = explain ? explainLinks : tryLinks;
  return (
    <div className={explain ? "shell shell-docs" : "shell shell-console"}>
      <div className="nav-dock">
      <header className="topbar">
        <div className="brand">
          <strong>AI Gateway</strong>
          <span>Version 8 console</span>
        </div>
        <nav>
          <NavLink to="/" end>
            Explain
          </NavLink>
          <NavLink to="/try">Try</NavLink>
        </nav>
        <div className="top-actions">
          {explain ? <LayerToggle /> : null}
          {session.me ? (
            <button type="button" className="ghost-button" onClick={() => void logout()}>
              Sign out {session.me.email ?? session.me.role}
            </button>
          ) : null}
        </div>
      </header>
      <div className="subnav">
        {links.map((link) => (
          <NavLink key={link.to} to={link.to} end={link.end}>
            {link.label}
          </NavLink>
        ))}
      </div>
      </div>
      <main>
        <Outlet />
      </main>
    </div>
  );
}
