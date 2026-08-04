"""
Trial helper.

Run this on its own (no Discord bot needed) to plant a fake, valid token
in the database, then start just the website (`python web.py`) and open
the printed link. Lets you see and play with the terminal UI before the
bot is invited to any server.

Usage:
    python create_test_token.py
    python web.py
    # open the link it prints
"""

import db

if __name__ == "__main__":
    db.init_db()
    token = db.create_token(
        user_id=111111111111111111,
        guild_id=222222222222222222,
        username="test-user#0001",
        ttl_seconds=3600,  # 1 hour, generous for testing
    )
    print("\nTest token created. With `python web.py` running locally, open:\n")
    print(f"  http://localhost:8080/colour/{token}\n")
