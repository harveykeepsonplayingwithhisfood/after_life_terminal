# AFTERLIFE colour bot + terminal website

One process that runs both the Discord bot and the website. Someone clicks
a button in Discord → gets a private one-time link → picks a colour on a
cyberpunk terminal page → the bot applies it as a role automatically.

## How it fits together

```
Discord button click
        │
        ▼
  bot.py generates a random token, stores it in afterlife.db,
  DMs the user: yoursite.com/colour/<token>
        │
        ▼
  User opens the link → web.py checks the token is real,
  unused, and not expired → serves the terminal page
        │
        ▼
  User drags the hue slider (terminal recolours live) → hits
  "Lock in" → website writes the hex colour to afterlife.db
        │
        ▼
  bot.py's background loop (checks every 3s) sees the new
  colour, creates/updates a Discord role, assigns it, marks
  the token permanently used
```

The token embedded in the link **is** the "temporary password" — there's
nothing to separately type in. It's random, single-use, and expires after
10 minutes by default (`LINK_TTL_SECONDS` in `.env`).

## 1. Set up the Discord bot

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications) → **New Application**.
2. **Bot** tab → reset/copy the token → this is `DISCORD_BOT_TOKEN`.
3. Under **Privileged Gateway Intents**, turn on **Server Members Intent** (the bot needs this to assign roles reliably).
4. **OAuth2 → URL Generator**: scopes `bot` + `applications.commands`; permissions `Manage Roles`, `Send Messages`, `Embed Links`. Use the generated URL to invite it straight into **Afterlife**.
5. **Role position**: in Server Settings → Roles, drag the bot's own role **above** where the colour roles should sit. Discord only lets a bot manage roles positioned below its own highest role, and a member's name colour is decided by their *highest* coloured role — so the bot's role needs to sit above the colour roles, and the colour roles need to sit above anything else with a colour set that you don't want overriding it (e.g. a "Member" role).

## 2. Deploy it so it runs without your PC

**[Railway](https://railway.app)** (simplest, generous free tier to start):

1. Push this folder to a GitHub repo (private is fine).
2. Railway → New Project → Deploy from GitHub repo.
3. In the service's **Variables** tab, add everything from `.env.example` with real values. For `WEBSITE_BASE_URL`, use the `*.up.railway.app` domain Railway assigns you (Settings → Networking → Generate Domain) — you can attach a real custom domain any time from there too.
4. Railway auto-detects the start command from `main.py`, or set it explicitly: `python main.py`.
5. Deploy. Check the logs — you're live once you see `Logged in as <bot name>` and `Website listening on 0.0.0.0:...`.

Render.com works the same way (Web Service, same env vars, start command `python main.py`) if you'd rather use that.

**This is genuinely 24/7** — Railway keeps the process alive, restarts it if it crashes, and there's nothing running on your computer. Closing your laptop doesn't affect it.

## 3. Go live in Discord

In the channel you want the panel in, run the slash command:

```
/setup-colour-panel
```

(Needs "Manage Server" permission — it posts the embed + button using the
exact text you specified.) That's it — the button is live, real users can
click it right away.

## Previewing the terminal UI without waiting on Discord

If you ever want to see the site on its own — e.g. while Railway is still
deploying, or to sanity-check a design tweak — you can spin up just the
website locally:

```bash
pip install -r requirements.txt
python create_test_token.py     # prints a link
python web.py                   # starts just the website on :8080
```

Open the printed `http://localhost:8080/colour/<token>` link. This doesn't
touch Discord in any way (no bot running) — it's purely a way to look at
the page.

## Notes / things worth knowing

- **Database**: a single `afterlife.db` SQLite file, created automatically. On Railway this lives on the container's disk — fine for this workload, but if you ever redeploy in a way that wipes the filesystem, you'd lose the token history (not the roles themselves, those live on Discord).
- **One colour role per person**: picking a new colour edits your *existing* role rather than piling up new ones.
- **Privacy**: the site has no homepage/index and no links pointing at `/colour/<token>` from anywhere except the DM — it only makes sense to someone holding a real token, and every token is single-use and short-lived.
