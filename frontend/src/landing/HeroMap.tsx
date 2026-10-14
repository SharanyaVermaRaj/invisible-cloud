import { useEffect, useMemo, useState } from "react";

// A scripted, self-playing version of the product's core moment:
// a sentence is typed, the access map previews the change, then applies it.

type Level = "on" | "read" | "off";
type People = "elena" | "john" | "mike" | "sarah";
type Doc = "tax" | "w2" | "payroll" | "globex";

const PEOPLE: { key: People; name: string; title: string }[] = [
  { key: "elena", name: "Elena", title: "Partner" },
  { key: "john", name: "John", title: "Accountant" },
  { key: "mike", name: "Mike", title: "Accountant" },
  { key: "sarah", name: "Sarah", title: "Accountant" },
];
const DOCS: { key: Doc; name: string }[] = [
  { key: "tax", name: "Acme tax return" },
  { key: "w2", name: "Acme W-2" },
  { key: "payroll", name: "Acme payroll" },
  { key: "globex", name: "Globex statement" },
];

type Grid = Record<People, Record<Doc, Level>>;
const START: Grid = {
  elena: { tax: "on", w2: "on", payroll: "on", globex: "on" },
  john: { tax: "on", w2: "off", payroll: "off", globex: "on" },
  mike: { tax: "off", w2: "on", payroll: "on", globex: "off" },
  sarah: { tax: "off", w2: "off", payroll: "off", globex: "off" },
};

interface Step {
  sentence: string;
  gain: [People, Doc][];
  loss: [People, Doc][];
  summary: string;
}
const SCRIPT: Step[] = [
  {
    sentence: "Mike is no longer handling Acme's payroll. Sarah will handle it.",
    gain: [["sarah", "w2"], ["sarah", "payroll"]],
    loss: [["mike", "w2"], ["mike", "payroll"]],
    summary: "Preview: Sarah gains 2 documents, Mike loses 2",
  },
  {
    sentence: "Sarah is now a partner.",
    gain: [["sarah", "tax"], ["sarah", "globex"]],
    loss: [],
    summary: "Preview: Sarah gains 2 documents",
  },
];

type Phase = "typing" | "preview" | "applied";

function apply(grid: Grid, step: Step): Grid {
  const next = structuredClone(grid);
  step.gain.forEach(([p, d]) => (next[p][d] = "on"));
  step.loss.forEach(([p, d]) => (next[p][d] = "off"));
  return next;
}

const reducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

export function useHeroScript() {
  const still = useMemo(reducedMotion, []);
  const [stepIdx, setStepIdx] = useState(0);
  const [chars, setChars] = useState(still ? SCRIPT[0].sentence.length : 0);
  const [phase, setPhase] = useState<Phase>(still ? "applied" : "typing");
  const [grid, setGrid] = useState<Grid>(still ? apply(START, SCRIPT[0]) : START);
  const step = SCRIPT[stepIdx];

  useEffect(() => {
    if (still) return;
    let t: number;
    if (phase === "typing") {
      if (chars < step.sentence.length) {
        t = window.setTimeout(() => setChars(c => c + 1), chars === 0 ? 700 : 34);
      } else {
        t = window.setTimeout(() => setPhase("preview"), 450);
      }
    } else if (phase === "preview") {
      t = window.setTimeout(() => { setGrid(g => apply(g, step)); setPhase("applied"); }, 2300);
    } else {
      t = window.setTimeout(() => {
        const next = (stepIdx + 1) % SCRIPT.length;
        if (next === 0) setGrid(START);
        setStepIdx(next);
        setChars(0);
        setPhase("typing");
      }, 3200);
    }
    return () => window.clearTimeout(t);
  }, [still, phase, chars, step, stepIdx]);

  return { step, phase, grid, typed: step.sentence.slice(0, chars), done: chars >= step.sentence.length };
}

export function HeroMap({ phase, grid, step }: { phase: Phase; grid: Grid; step: Step }) {
  const status =
    phase === "typing" ? "Waiting for a change" : phase === "preview" ? step.summary : "Applied. Every app now follows it.";
  const cellState = (p: People, d: Doc) => {
    if (phase === "preview") {
      if (step.gain.some(([gp, gd]) => gp === p && gd === d)) return "gain";
      if (step.loss.some(([lp, ld]) => lp === p && ld === d)) return "loss";
    }
    return grid[p][d];
  };
  return (
    <div className="map-card" aria-label="Animated example of the access map">
      <div className="map-head">
        <h2>Who can open what at Parkside Accounting</h2>
        <span className={`map-status${phase === "preview" ? " is-preview" : phase === "applied" ? " is-applied" : ""}`}
              aria-live="polite">{status}</span>
      </div>
      <table className="hmap">
        <thead>
          <tr>
            <th><span className="visually-hidden">Person</span></th>
            {DOCS.map(d => <th key={d.key} scope="col">{d.name}</th>)}
          </tr>
        </thead>
        <tbody>
          {PEOPLE.map(p => (
            <tr key={p.key}>
              <th scope="row">{p.name}<span>{p.key === "sarah" && phase === "applied" && step === SCRIPT[1] ? "Partner" : p.title}</span></th>
              {DOCS.map(d => {
                const s = cellState(p.key, d.key);
                return (
                  <td key={d.key}>
                    <div className={`cell ${s}`} aria-label={`${p.name}, ${d.name}: ${s === "on" ? "has access" : s === "gain" ? "will gain access" : s === "loss" ? "will lose access" : "no access"}`}>
                      {s === "gain" && <span className="mark">+</span>}
                      {s === "loss" && <span className="mark">{"−"}</span>}
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="map-legend">
        <span><i style={{ background: "var(--ink)" }} />Has access</span>
        <span><i style={{ background: "var(--gain)" }} />Will gain access</span>
        <span><i style={{ background: "var(--loss-soft)", boxShadow: "inset 0 0 0 2px var(--loss)" }} />Will lose access</span>
      </div>
    </div>
  );
}
