"""
Single entrypoint for deployment: runs the Flask website in a background
thread and the Discord bot in the main thread. One process, one host,
one 'start' command — this is what Railway/Render should run.
"""

import os
import threading
import logging

import db
from web import app

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("afterlife-main")


def run_web():
    from waitress import serve
    port = int(os.environ.get("PORT", 8080))
    log.info("Website listening on 0.0.0.0:%s", port)
    serve(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    db.init_db()

    web_thread = threading.Thread(target=run_web, daemon=True)
    web_thread.start()

    import bot  # imported here so DISCORD_BOT_TOKEN is only required at actual startup
    bot.bot.run(bot.TOKEN)
