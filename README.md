# AFTERLIFE colour and path bot

One process, one button, one link. Someone clicks it and gets a DM with a
single private link and password. The site walks them through picking
their colour, then their path (Nomad, Streetkid, or Corpo), on the same
page, in that order. The whole thing is one shot, once it's done that
member can't run it again. Both results apply as Discord roles
automatically, live, with no manual step.

The path step is an original design (its own icons, its own copy), not a
copy of any game's actual artwork, it just borrows the general idea of
"three origins to pick from" as a layout.

## How it fits together

```
Discord button click
        │
        ▼
  bot.py checks this member hasn't completed the flow before.
  If they haven't, it generates one token and one 8 character
  password, stores them in afterlife.db, and DMs both as:
  yoursite.com/select/<token>
        │
        ▼
  User opens the link. web.py checks the token is real, unused,
  and not expired, works out which stage they're on (password,
  colour, or path), and serves that stage. Reloading the page
  mid-flow resumes wherever they left off instead of restarting.
        │
        ▼
  User types the password in. web.py checks it against the
  stored hash (5 wrong guesses permanently kills the link)
        │
        ▼
  Step 1: the hue slider unlocks, they pick a colour, "lock in"
  saves it and the page moves straight into step 2 without a
  reload
        │
        ▼
  Step 2: three path cards unlock, picking one recolours the
  whole page to match it, "confirm" saves it and marks the
  token ready
        │
        ▼
  bot.py's background loop (checks every 3s) sees the completed
  submission and applies both roles:
    colour -> a role named after the hex code, that member's
              own colour
    path   -> a shared "Nomad" / "Streetkid" / "Corpo" role,
              white, reused across everyone who picks that path
  The token is marked permanently used.
```

## 1. Set up the Discord bot

1. [Discord Developer Portal](https://discord.com/developers/applications), New Application.
2. Bot tab, copy the token, this is `DISCORD_BOT_TOKEN`.
3. Under Privileged Gateway Intents, turn on Server Members Intent (needed to assign roles reliably).
4. OAuth2 URL Generator: scopes `bot` and `applications.commands`; permissions `Manage Roles`, `Send Messages`, `Embed Links`. Invite it into Afterlife.
5. Role position: drag the bot's own role above where both the colour roles and the three path roles should sit, a bot can only manage roles below its own highest role, and a member's displayed colour is decided by their highest coloured role.

## 2. Deploy it so it runs without your PC

[Railway](https://railway.app):

1. Push this folder to a GitHub repo.
2. Railway, New Project, Deploy from GitHub repo.
3. Variables tab: add everything from `.env.example`. `WEBSITE_BASE_URL` must include the scheme, `https://your-app.up.railway.app`, not just the bare domain, the bot checks this on startup and refuses to run without it.
4. Start command: `python main.py`.
5. Deploy, check the logs for `Logged in as <bot name>` and `Website listening on 0.0.0.0:...`.

## 3. Go live in Discord

```
/setup-panel
```

Needs "Manage Server" permission. Posts one embed with one button. Clicking it is what sends the link.

## Previewing the flow without waiting on Discord

```bash
pip install -r requirements.txt
python create_test_token.py
python web.py
```

Open the printed link and type in the password it printed. You can walk the whole colour then path sequence right there, nothing touches Discord.

## Notes

- **One shot, once, for the whole flow**: `db.has_completed()` checks whether this member has ever finished both steps. Letting a link expire or fail before finishing doesn't count against them, they can still request a new one.
- **Path roles are shared**: unlike colour (one role per person), the three path roles are created once each and reused for everyone who picks that path.
- **Order is enforced server side**: the website can't be tricked into submitting a path before a colour, `db.submit_path()` checks that the colour is already set first.
- **Passwords are real**: 8 characters, secrets-generated, hashed in the database, checked server side, 5 wrong guesses kills the link.
- **Database**: a single `afterlife.db` SQLite file, created automatically.
- **Privacy**: `/select/<token>` is not linked anywhere except in the DM.
