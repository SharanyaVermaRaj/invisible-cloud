import { Link } from "react-router-dom";
import { Icon, Logo } from "../ui";
import { HeroMap, useHeroScript } from "./HeroMap";

export function Landing() {
  const hero = useHeroScript();
  return (
    <div>
      <div className="l-wrap">
        <header className="l-nav">
          <Link to="/" className="wordmark"><Logo />Invisible Cloud</Link>
          <nav aria-label="Main">
            <a className="plain" href="#how">How it works</a>
            <a className="plain" href="#safety">Safety</a>
            <Link to="/app" className="btn btn-primary">Try the demo</Link>
          </nav>
        </header>

        <section className="hero">
          <div>
            <p className="hero-quote said" aria-label={hero.step.sentence}>
              <span aria-hidden="true">{"“"}{hero.typed}{hero.done ? "”" : ""}</span>
              {!hero.done && <span className="caret" aria-hidden="true" />}
            </p>
            <p className="hero-lede">
              Your firm already knows its rules: who handles which client, who sees which file, who signs off.{" "}
              <strong>Invisible Cloud runs on those rules.</strong> Say what changed, see exactly who gains and
              loses access, and confirm.
            </p>
            <div className="hero-cta">
              <Link to="/app" className="btn btn-brand btn-lg">Try the live demo</Link>
              <small>No sign-up. You get your own sample accounting firm.</small>
            </div>
          </div>
          <HeroMap phase={hero.phase} grid={hero.grid} step={hero.step} />
        </section>
      </div>

      <section className="l-section">
        <div className="l-wrap split">
          <div>
            <h2>One change at your firm means six updates in your software.</h2>
            <p className="lead">
              When someone takes over a client, someone else has to remember every folder, portal and login that
              needs changing. Miss one, and the wrong person can still open a client's tax return.
            </p>
          </div>
          <div className="fanout">
            <p className="said-box said">{"“"}Sarah is taking over Acme's payroll.{"”"}</p>
            <svg viewBox="0 0 56 260" aria-hidden="true">
              {[22, 66, 110, 152, 196, 238].map(y => (
                <path key={y} d={`M2 130 C 30 130, 26 ${y}, 54 ${y}`} fill="none" stroke="#bdc6bf" strokeWidth="1.5" />
              ))}
            </svg>
            <ul>
              <li><span><b>Shared drive</b> Add Sarah to the Acme payroll folder</span></li>
              <li><span><b>Shared drive</b> Remove Mike from it</span><em>Forgotten</em></li>
              <li><span><b>Client portal</b> Change Acme's payroll contact</span></li>
              <li><span><b>Payroll system</b> Change the preparer</span></li>
              <li><span><b>Accounting software</b> Update user permissions</span></li>
              <li><span><b>Email</b> Reroute Acme payroll requests</span></li>
            </ul>
          </div>
        </div>
      </section>

      <section className="l-section" id="how">
        <div className="l-wrap">
          <h2>Describe the change. Check it. Confirm it.</h2>
          <p className="lead">
            Your files, permissions and approvals live in one place that understands how your firm works. You
            manage all of it by saying what changed.
          </p>
          <ol className="steps">
            <li>
              <span className="n">1</span>
              <h3>Say what changed</h3>
              <p>Type it the way you'd tell a colleague: new hires, reassignments, promotions, people leaving, new rules.</p>
            </li>
            <li>
              <span className="n">2</span>
              <h3>See exactly what happens</h3>
              <p>Before anything changes, you see every person who gains or loses access to every document.</p>
            </li>
            <li>
              <span className="n">3</span>
              <h3>Confirm, or undo later</h3>
              <p>Every change is recorded. Undo any of them in one click, like version history for your whole firm.</p>
            </li>
          </ol>
        </div>
      </section>

      <section className="l-section" id="safety">
        <div className="l-wrap split">
          <div>
            <h2>The AI suggests. Your rules decide.</h2>
            <p className="lead">
              The AI never touches your data. It can only propose changes from a short list of actions we've built
              and tested, and every proposal is checked before you see it.
            </p>
            <ul className="checks">
              <li><b>No generated code.</b> The AI picks from fixed, tested actions. It can't invent new ones.</li>
              <li><b>Checked before you see it.</b> Unknown people, impossible assignments and typos are caught automatically.</li>
              <li><b>Nothing happens without you.</b> Every change waits for your confirmation.</li>
            </ul>
          </div>
          <div className="translate">
            <p className="said">{"“"}Priya joined as an accountant. She'll help John with Globex's books.{"”"}</p>
            <ol>
              <li><span>Add person</span><span>Priya Nair</span></li>
              <li><span>Give role</span><span>Priya Nair becomes Accountant</span></li>
              <li><span>Assign work</span><span>Priya Nair on Globex {"–"} Bookkeeping</span></li>
            </ol>
            <p className="refused">Asked to {"“"}delete the database{"”"}? <b>That action doesn't exist.</b></p>
          </div>
        </div>
      </section>

      <section className="l-section">
        <div className="l-wrap split">
          <div className="conflict-demo">
            <p className="said">{"“"}Accountants can send tax returns up to $10,000 without approval.{"”"}</p>
            <div className="conflict">
              <h4><Icon name="warn" />This clashes with an existing rule</h4>
              <p>Your firm requires partner approval for tax returns over $5,000. This rule would skip it between $5,000 and $10,000.</p>
              <div className="options">
                <div className="option"><h5>Keep the existing rule</h5><ul><li>Accountants can send tax returns up to $5,000 without approval.</li></ul></div>
                <div className="option"><h5>Apply your new rule</h5><ul><li>Tax returns over $10,000 need partner approval.</li></ul></div>
              </div>
            </div>
          </div>
          <div>
            <h2>It notices when rules disagree.</h2>
            <p className="lead">
              A new rule can quietly undo an old one. Instead of guessing, Invisible Cloud shows you the clash and
              the clean ways to resolve it, then lets you choose.
            </p>
          </div>
        </div>
      </section>

      <section className="final-cta">
        <div className="l-wrap">
          <h2>See a sample firm follow your words.</h2>
          <div className="hero-cta">
            <Link to="/app" className="btn btn-brand btn-lg">Try the live demo</Link>
            <small>Takes two minutes. Nothing to install.</small>
          </div>
        </div>
      </section>

      <div className="l-wrap">
        <footer className="l-foot">
          <span>Invisible Cloud is an early prototype. The demo firm, people and documents are fictional.</span>
          <span>{"©"} {new Date().getFullYear()} Invisible Cloud</span>
        </footer>
      </div>
    </div>
  );
}
