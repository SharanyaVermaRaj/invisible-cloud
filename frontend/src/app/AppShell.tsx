import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, Navigate, NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { api, ApiError, AppState, getPersona, setPersona } from "../api";
import { Avatar, Icon, Logo, useToast } from "../ui";
import { AccessMapView } from "./AccessMapView";
import { ApprovalsView } from "./ApprovalsView";
import { AskView } from "./AskView";
import { Ctx, useApp } from "./context";
import { DocumentsView } from "./DocumentsView";
import { HistoryView } from "./HistoryView";
import { PeopleView } from "./PeopleView";
import { RulesView } from "./RulesView";

const TITLES: Record<string, string> = {
  "": "Tell the firm what changed", documents: "Documents", access: "Access map", people: "People",
  rules: "Rules", history: "History", approvals: "Approvals",
};

export function AppShell() {
  const [state, setState] = useState<AppState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const toast = useToast();
  const location = useLocation();
  const navigate = useNavigate();

  const load = useCallback(async (): Promise<AppState | null> => {
    try {
      const s = await api.state();
      setState(s);
      setError(null);
      if (getPersona() && getPersona() !== s.me.key) setPersona(s.me.key); // that person no longer exists
      return s;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong loading the demo.");
      return null;
    }
  }, []);
  const refresh = useCallback(async () => { await load(); }, [load]);

  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => { setMenuOpen(false); }, [location.pathname]);

  const name = useCallback((key: string | null | undefined) => (key && state?.names[key]) || key || "", [state]);
  const ctx = useMemo(() => (state ? { state, refresh, name } : null), [state, refresh, name]);

  const switchPersona = async (key: string) => {
    setPersona(key);
    const s = await load();
    if (s && !s.me.is_admin && ["/app", "/app/", "/app/access", "/app/history"].includes(location.pathname)) {
      navigate("/app/documents");
    }
  };

  const reset = async () => {
    if (!window.confirm("Start over with a fresh copy of the demo firm? Your changes will be cleared.")) return;
    try {
      await api.reset();
      setPersona(null);
      await refresh();
      navigate("/app");
      toast({ text: "Started a fresh copy of Parkside Accounting." });
    } catch (e) {
      toast({ text: e instanceof ApiError ? e.message : "Couldn't reset the demo.", error: true });
    }
  };

  if (error && !state) {
    return (
      <div className="boot">
        <div className="empty" style={{ maxWidth: 440 }}>
          <h3>The demo couldn't load</h3>
          <p>{error}</p>
          <button className="btn btn-primary" onClick={() => refresh()}>Try again</button>
        </div>
      </div>
    );
  }
  if (!ctx) return <div className="boot">Setting up your sample firm{"…"}</div>;

  const { me } = ctx.state;
  const section = location.pathname.replace(/^\/app\/?/, "").split("/")[0];

  return (
    <Ctx.Provider value={ctx}>
      <div className="app">
        <aside className={`side${menuOpen ? " open" : ""}`} aria-label="Sections">
          <Link to="/" className="wordmark"><Logo />Invisible Cloud</Link>
          <div className="firm">
            <strong>{ctx.state.workspace.name}</strong>
            <span><span className="badge brand">Demo</span>Sample firm</span>
          </div>
          <nav>
            {me.is_admin && <NavLink to="/app" end><Icon name="ask" />Ask</NavLink>}
            <NavLink to="/app/documents"><Icon name="docs" />Documents</NavLink>
            {me.is_admin && <NavLink to="/app/access"><Icon name="map" />Access map</NavLink>}
            <NavLink to="/app/people"><Icon name="people" />People</NavLink>
            <NavLink to="/app/rules"><Icon name="rules" />Rules</NavLink>
            {me.is_admin && <NavLink to="/app/history"><Icon name="history" />History</NavLink>}
            <NavLink to="/app/approvals">
              <Icon name="approvals" />Approvals
              {ctx.state.approvals.length > 0 && <span className="count">{ctx.state.approvals.length}</span>}
            </NavLink>
          </nav>
          <div className="spacer" />
          <button className="btn btn-ghost btn-sm" onClick={reset} style={{ justifyContent: "flex-start" }}>
            <Icon name="reset" className="" />Reset demo
          </button>
          <p className="foot">Demo data is fictional and private to your browser session.</p>
        </aside>

        <div className="main">
          <header className="topbar">
            <button className="btn btn-ghost btn-sm menu-toggle" aria-label="Open menu" onClick={() => setMenuOpen(o => !o)}>
              <Icon name="menu" className="" />
            </button>
            <h1>{TITLES[section] ?? ""}</h1>
            <div className="right">
              <PersonaSwitcher onSwitch={switchPersona} />
            </div>
          </header>
          <div className="content">
            {!me.is_admin && (
              <div className="notice">
                <Icon name="info" />
                <p>
                  You're viewing the firm as <b>{me.name}</b>{me.title ? `, ${me.title}` : ""}. You see only what the
                  firm's rules allow. Switch back to Elena (top right) to make changes.
                </p>
              </div>
            )}
            <Routes>
              <Route index element={me.is_admin ? <AskView /> : <Navigate to="/app/documents" replace />} />
              <Route path="documents" element={<DocumentsView />} />
              <Route path="access" element={me.is_admin ? <AccessMapView /> : <Navigate to="/app/documents" replace />} />
              <Route path="people" element={<PeopleView />} />
              <Route path="rules" element={<RulesView />} />
              <Route path="history" element={me.is_admin ? <HistoryView /> : <Navigate to="/app/documents" replace />} />
              <Route path="approvals" element={<ApprovalsView />} />
              <Route path="*" element={<Navigate to="/app" replace />} />
            </Routes>
          </div>
        </div>
      </div>
    </Ctx.Provider>
  );
}

function PersonaSwitcher({ onSwitch }: { onSwitch: (key: string) => void }) {
  const { state, name } = useApp();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", esc); };
  }, [open]);
  const roleName = (keys: string[]) => keys.map(k => name(k)).join(", ");
  return (
    <div className="persona" ref={ref}>
      <button className="persona-btn" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(o => !o)}>
        <Avatar person={state.me.key} name={state.me.name} />
        <span className="who"><small>Viewing as</small><b>{state.me.name}</b></span>
        <Icon name="chevron" className="" />
      </button>
      {open && (
        <div className="persona-menu" role="menu">
          <p>See the firm through someone else's eyes. Their view follows the firm's rules.</p>
          {state.people.map(p => (
            <button key={p.key} role="menuitem" aria-current={p.key === state.me.key}
                    onClick={() => { setOpen(false); onSwitch(p.key); }}>
              <Avatar person={p.key} name={p.name} small />
              <span>{p.name}<small>{p.title || roleName(p.roles)}</small></span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

