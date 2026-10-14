import { useState } from "react";
import { api, ApiError, money } from "../api";
import { Avatar, timeAgo, useToast } from "../ui";
import { useApp } from "./context";

export function ApprovalsView() {
  const { state, refresh, name } = useApp();
  const toast = useToast();
  const [busy, setBusy] = useState<number | null>(null);
  const waiting = state.documents.filter(d => d.delivery?.status === "pending" && d.delivery.requested_by === state.me.key);

  const decide = async (id: number, decision: "approve" | "reject", docName: string) => {
    setBusy(id);
    try {
      await api.decide(id, decision);
      await refresh();
      toast({ text: decision === "approve" ? `Approved. ${docName} was sent to the client.` : `Declined. ${docName} wasn't sent.` });
    } catch (e) {
      toast({ text: e instanceof ApiError ? e.message : "Couldn't record the decision.", error: true });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div>
      <div className="page-head">
        <h2>Approvals</h2>
        <p>Documents that need sign-off before they go to a client, based on the firm's approval rules.</p>
      </div>

      {state.approvals.length === 0 ? (
        <div className="empty">
          <h3>Nothing needs your approval</h3>
          <p>
            {state.me.is_admin
              ? "When an accountant sends a tax return over the approval limit, it waits here for you. Try it: view the firm as John and send Acme's tax return."
              : "Requests that need your sign-off will show up here."}
          </p>
        </div>
      ) : (
        <div className="rows">
          {state.approvals.map(a => (
            <div className="row approval" key={a.id}>
              <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
                <Avatar person={a.requested_by} name={a.requested_by_name} />
                <div>
                  <b>{a.document_name}{a.amount != null && <>, <span className="num">{money(a.amount)}</span></>}</b>
                  <span className="sub">{a.requested_by_name} wants to send this to the client, {timeAgo(a.created_at)}. Rule: {a.reason}</span>
                </div>
              </div>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <a className="btn btn-sm" href={api.fileUrl(a.document)} target="_blank" rel="noreferrer">Open</a>
                <button className="btn btn-sm" disabled={busy === a.id} onClick={() => decide(a.id, "reject", a.document_name)}>Decline</button>
                <button className="btn btn-sm btn-primary" disabled={busy === a.id} onClick={() => decide(a.id, "approve", a.document_name)}>Approve and send</button>
              </div>
            </div>
          ))}
        </div>
      )}

      {waiting.length > 0 && (
        <section style={{ marginTop: 32 }}>
          <h3 style={{ fontSize: 17, margin: "0 0 10px" }}>Waiting on someone else</h3>
          <div className="rows">
            {waiting.map(d => (
              <div className="row approval" key={d.key}>
                <div><b>{d.name}</b><span className="sub">Waiting for a {name(d.approval?.approver_role ?? "partner").toLowerCase()} to approve.</span></div>
                <span className="badge hold">Awaiting approval</span>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
