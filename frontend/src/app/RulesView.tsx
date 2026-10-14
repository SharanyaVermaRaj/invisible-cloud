import { Link } from "react-router-dom";
import { useApp } from "./context";

const TYPE_LABEL: Record<string, string> = {
  access: "Access", restriction: "Restriction", approval: "Approval", exemption: "Exemption",
};

export function RulesView() {
  const { state } = useApp();
  return (
    <div>
      <div className="page-head">
        <h2>The firm's rules</h2>
        <p>
          Each rule is kept in the words it was given, next to exactly how the system reads it. Every document,
          approval and permission follows these.
          {state.me.is_admin && <> Add or change a rule by <Link to="/app">describing it</Link>.</>}
        </p>
      </div>
      <div className="rows">
        {state.rules.map(r => (
          <div className="row rule-row" key={r.key}>
            <div>
              <p className="said">{"“"}{r.text}{"”"}</p>
              <p className="reads"><b>How the system reads it:</b> {r.description}</p>
            </div>
            <div className="side-tags">
              <span className="badge">{TYPE_LABEL[r.type] ?? r.type}</span>
              {r.version > 1 && <span className="badge brand">Version {r.version}</span>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
