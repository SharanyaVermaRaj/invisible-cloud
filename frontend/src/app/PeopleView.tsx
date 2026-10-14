import { Link } from "react-router-dom";
import { Avatar } from "../ui";
import { useApp } from "./context";

export function PeopleView() {
  const { state, name } = useApp();
  return (
    <div>
      <div className="page-head">
        <h2>People</h2>
        <p>
          Who works at the firm, their role, and what they're responsible for.
          {state.me.is_admin && <> To change any of this, <Link to="/app">tell the firm what changed</Link>.</>}
        </p>
      </div>
      <div className="rows">
        {state.people.map(p => (
          <div className="row person-row" key={p.key}>
            <div className="who">
              <Avatar person={p.key} name={p.name} />
              <div><b>{p.name}</b><span>{p.title}</span></div>
            </div>
            <div className="tags">
              {p.roles.map(r => <span key={r} className={`badge${r === "partner" ? " brand" : ""}`}>{name(r)}</span>)}
            </div>
            <div className="tags">
              {p.assignments.map(a => <span key={a} className="badge">{name(a)}</span>)}
              {p.contact_for.map(c => <span key={c} className="badge">Contact for {name(c)}</span>)}
              {p.assignments.length === 0 && p.contact_for.length === 0 && (
                <span style={{ color: "var(--ink-3)", fontSize: 13 }}>{p.roles.includes("partner") ? "Oversees every client" : "No assignments"}</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
