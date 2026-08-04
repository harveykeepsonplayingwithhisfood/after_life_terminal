import os
import re
import time
from flask import Flask, render_template, request, jsonify

import db

app = Flask(__name__)

HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _token_status(row):
    """Returns None if usable, otherwise a reason string for the invalid page."""
    if not row or row["status"] == "applied":
        return "used"
    if row["status"] not in ("pending",):
        return "used"
    if row["expires_at"] < int(time.time()):
        return "expired"
    return None


@app.route("/colour/<token>")
def colour_page(token):
    row = db.get_token(token)
    reason = _token_status(row)
    if reason:
        return render_template("invalid.html", reason=reason), 410

    return render_template("colour.html", token=token, username=row["username"], verified=bool(row["verified"]))


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


@app.route("/api/submit", methods=["POST"])
def submit():
    data = request.get_json(silent=True) or {}
    token = data.get("token", "")
    hex_colour = data.get("colour", "")

    if not HEX_RE.match(hex_colour):
        return jsonify({"ok": False, "error": "invalid colour format"}), 400

    row = db.get_token(token)
    if not row or row["status"] != "pending" or row["expires_at"] < int(time.time()):
        return jsonify({"ok": False, "error": "this link has expired or was already used"}), 410
    if not row["verified"]:
        return jsonify({"ok": False, "error": "password not verified"}), 403

    db.submit_colour(token, hex_colour)
    return jsonify({"ok": True})


@app.route("/")
def index():
    # not linked anywhere on the server, the site only makes sense arriving via a real token
    return render_template("invalid.html", reason="no_token"), 404


if __name__ == "__main__":
    db.init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=True)
