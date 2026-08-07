import os
import time
from flask import Flask, render_template, request, jsonify

import db

app = Flask(__name__)


def _token_status(row):
    """Returns None if usable, otherwise a reason string for the invalid page."""
    if not row:
        return "no_token"
    if row["status"] == "applied" or row["status"] not in ("pending", "submitted"):
        return "used"
    if row["expires_at"] < int(time.time()):
        return "expired"
    return None


@app.route("/select/<token>")
def select_page(token):
    row = db.get_token(token)
    reason = _token_status(row)
    if reason:
        return render_template("invalid.html", reason=reason), 410
    stage = db.get_stage(row)
    if stage == "done":
        # already fully submitted, waiting on the bot to apply it, nothing left to do here
        return render_template("invalid.html", reason="used"), 410
    return render_template("select.html", token=token, username=row["username"], stage=stage)


@app.route("/api/verify", methods=["POST"])
def verify():
    data = request.get_json(silent=True) or {}
    token = data.get("token", "")
    password = data.get("password", "")

    result = db.verify_password(token, password)
    if result == "ok":
        return jsonify({"ok": True})
    if result == "wrong":
        return jsonify({"ok": False, "error": "incorrect password", "locked": False}), 401
    if result == "locked":
        return jsonify({"ok": False, "error": "too many attempts, this link is now dead", "locked": True}), 401
    return jsonify({"ok": False, "error": "this link has expired or was already used", "locked": True}), 410


@app.route("/api/submit-colour", methods=["POST"])
def submit_colour():
    data = request.get_json(silent=True) or {}
    token = data.get("token", "")
    payload = data.get("payload", "")

    if not db.submit_colour(token, payload):
        return jsonify({"ok": False, "error": "could not save that colour, the link may be out of order or dead"}), 400
    return jsonify({"ok": True})


@app.route("/api/submit-path", methods=["POST"])
def submit_path():
    data = request.get_json(silent=True) or {}
    token = data.get("token", "")
    payload = data.get("payload", "")

    if not db.submit_path(token, payload):
        return jsonify({"ok": False, "error": "could not save that path, the link may be out of order or dead"}), 400
    return jsonify({"ok": True})


@app.route("/")
def index():
    # not linked anywhere on the server, the site only makes sense arriving via a real token
    return render_template("invalid.html", reason="no_token"), 404


if __name__ == "__main__":
    db.init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=True)
