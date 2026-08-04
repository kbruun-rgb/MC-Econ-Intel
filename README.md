# Morning Consult Economic Intelligence

A password-protected client portal for MC econ dashboards and analysis
reports. Flask app, SQLite for accounts, content read live from:
- `G:\Shared drives\mc_econ\Econ Team\Econ Data Library` (dashboards)
- `C:\Users\kayla\Desktop\Kayla\Claude Helper Tools\Analyses` (reports)

Nothing from either location is copied — the app reads them at request time,
so updating a dashboard or publishing a new memo in those folders shows up
here automatically, no redeploy needed.

## Run it locally

```bash
venv\Scripts\activate
python run.py
```

Then open http://127.0.0.1:5000 — you'll be redirected to `/login`.

## Add a client account

```bash
venv\Scripts\activate
python create_user.py --email client@example.com --name "Client Name"
```
(Omit `--password` to be prompted instead of typing it on the command line.)
Re-running with an existing email updates that account's name/password
rather than creating a duplicate.

A demo account was created for initial testing:
`demo@client.test` / `MCDemo2026!` — **delete or change this before sharing
the site with anyone**, e.g.:
```bash
python create_user.py --email demo@client.test --name "Demo Client" --password "<new-password>"
```

## What's published to clients

- **Dashboards** (`/dashboards`): every `*.html` file found in each Econ Data
  Library theme folder, plus that folder's `interpretation_guide.md` as a
  "Methodology" section. Empty theme folders show as "Coming soon."
- **Analysis & Reports** (`/reports`): **opt-in only.** An Analyses folder
  only shows up here if you've explicitly published it — see below. This is
  deliberate: some analyses are bespoke work for a single client/brand (e.g.
  a one-off brief written about a specific company) and should never appear
  on the general site just because it has a memo file that matches a naming
  pattern.

### Publishing an analysis

```bash
venv\Scripts\activate
python publish_report.py 2026-06-10-memorial-day-spending
```
That's it — it'll appear on `/reports` on next page load, using the memo's
own headline as the title and a best-guess theme. To override either:
```bash
python publish_report.py 2026-06-03-staples-drs-leading-indicator --title "Office Supply Store Sales Leading Indicator" --theme "Consumer Spending"
```
To pull something back off the site:
```bash
python publish_report.py 2026-06-30-tapestry-genz --remove
```

**Rule of thumb for what to publish**: if the analysis is about a broad
economic trend, category, or region (e.g. consumer spending, a state's
sentiment, an index methodology), it's a good fit. If it's written about — or
would identify — a specific company/brand (bespoke client work), don't
publish it here.

Within a published folder, a written memo (`.docx`) is rendered as an inline
article (embedded images and all); a slide deck (`.pptx`) is converted to
PDF once (cached alongside the source) and offered as a download instead,
since a deck doesn't reflow into prose. Folders you haven't published, and
folders with no memo/brief file at all, are logged to the console when
`/reports` loads — check the terminal running `run.py` to see what's sitting
unpublished.

## Still to decide (see the plan for full context)

- **Hosting**: this only runs on localhost today. Nothing was deployed and
  no external accounts (Vercel/Supabase/etc.) were created — that's a
  decision for you to make, possibly with MC IT given this will hold
  proprietary data and client credentials.
- **Content tiering**: every client account currently sees the same content.
- Real Proxima Nova font files can be dropped in later (`app/static/`) —
  the official MC logo is already in place (`app/static/img/mc_logo.png`,
  pulled from morningconsult.com), just falling back to system fonts for now.

Full plan/context: `C:\Users\kayla\.claude\plans\calm-dancing-newt.md`
