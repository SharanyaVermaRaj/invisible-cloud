# Putting Invisible Cloud on your own domain

This takes about 30 minutes. You'll end up with the site at something like
`https://invisiblecloud.app`, with a "Try the demo" button anyone can use.

**What you'll pay (check current prices before you start):**

| Item | Approximate cost |
| --- | --- |
| Domain name (.com or .app) | About $10–15 per year |
| Render web service, Starter plan | About $7 per month |
| Render Postgres, smallest paid plan | About $6 per month |
| Anthropic API usage | Pay as you go. A few dollars covers a lot of demo traffic |

Render's free tier works for trying things out, but free web services go to sleep after
15 minutes (the next visitor waits about a minute) and free databases are deleted after
30 days. For a link you send to YC, use the paid plans so the demo is always instant.

## 1. Put the code on GitHub

1. Create a free account at github.com if you don't have one.
2. Create a new **private** repository called `invisible-cloud`. Don't add a README.
3. In a terminal, inside the project folder:

   ```bash
   git remote add origin https://github.com/YOUR-USERNAME/invisible-cloud.git
   git branch -M main
   git push -u origin main
   ```

## 2. Get an Anthropic API key

1. Go to console.anthropic.com and create an account.
2. Add credit under Billing (start small; $10 is plenty for a demo).
3. Under API Keys, create a key and copy it. Keep it private: never put it in the code,
   a screenshot or a chat.
4. Optional but smart: set a monthly spend limit in the console.

The app also has its own guardrails, set by environment variables: 40 AI requests per visitor
per hour and 1,000 per day across all visitors. Lower them if you want.

## 3. Deploy on Render

1. Create an account at render.com and connect your GitHub account.
2. Click **New** and choose **Blueprint**, then pick your `invisible-cloud` repository.
   Render reads `render.yaml` and sets up the web server and the database together.
3. When asked for `ANTHROPIC_API_KEY`, paste your key.
4. Click **Apply**. The first build takes 3–5 minutes.
5. Open the `onrender.com` address Render gives you. You should see the landing page, and
   "Try the demo" should open your own sample firm.

**Check it works:** in the demo, click the first "Try saying" suggestion, then **Preview
change**. You should see Sarah gaining and Mike losing access. If you see a notice that the
AI isn't switched on, the API key is missing: add it under the service's **Environment** tab.

## 4. Connect your domain

1. Buy a domain from a registrar such as Cloudflare, Namecheap or Porkbun.
2. In Render, open the web service, go to **Settings**, then **Custom Domains**, and add your
   domain (for example `invisiblecloud.app` and `www.invisiblecloud.app`).
3. Render shows you the DNS records to create. Add them at your registrar exactly as shown.
4. Wait for Render to show the domain as verified (usually minutes, sometimes a few hours).
   Render sets up HTTPS automatically.

## 5. Before you send the link

- Open the site on your phone and on a laptop, in a private window.
- Go through the demo script below once, start to finish.
- Click **Reset demo** at the end so your own copy is fresh.

## A two-minute demo script (for the YC video, too)

1. **Landing page.** Point at the access map as the sentence types itself.
2. Click **Try the live demo**. Show the **Access map**: Mike can open Acme's payroll files,
   Sarah can't.
3. On **Ask**, say *"Mike is no longer handling Acme's payroll. Sarah will handle it."*
   Show the preview, then **Apply change**.
4. Back on the **Access map**, show that it changed. Switch to **Mike** (top right) and show
   the payroll files are gone from his documents. Click **Open** on a document he still has.
5. Switch back to **Elena**. Say *"Accountants can send tax returns up to $10,000 without
   approval."* Show the conflict and the two ways to resolve it, then click **Adjust your new
   rule** (it caps the new rule at $5,000, so the next step still needs approval).
6. Switch to **John**, send Acme's tax return. It goes to approval because it's over $5,000.
   Switch to **Elena** and approve it on **Approvals**.
7. Open **History** and undo the payroll change. Everything goes back.

## Updating the site later

Push to GitHub and Render redeploys automatically:

```bash
git add -A
git commit -m "Describe your change"
git push
```

## Environment variables

| Name | What it does |
| --- | --- |
| `DATABASE_URL` | Postgres connection string. Set automatically by the blueprint. |
| `SECRET_KEY` | Signs visitors' workspace cookies. Generated automatically. |
| `ANTHROPIC_API_KEY` | Turns on the plain-English layer. |
| `AI_MODEL` | Which Claude model translates sentences. Default `claude-sonnet-5-5`. |
| `COOKIE_SECURE` | `true` in production (HTTPS only cookies). |
| `AI_LIMIT_PER_WORKSPACE_PER_HOUR` | AI requests one visitor can make per hour. Default 40. |
| `AI_LIMIT_PER_DAY` | AI requests across all visitors per day. Default 1000. |
| `WORKSPACE_TTL_DAYS` | Demo firms older than this are deleted. Default 7. |
| `MAX_UPLOAD_MB` | Largest file a visitor can upload. Default 5. |

## Other hosts

The app is a standard Docker container that listens on `$PORT` and needs one Postgres
database, so it also runs on Railway, Fly.io, Google Cloud Run or any similar host. Set the
same environment variables there.
