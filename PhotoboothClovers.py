import os
import json
import re
from datetime import datetime

import gspread
from oauth2client.service_account import ServiceAccountCredentials
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_socketio import SocketIO

# ---------------------------------------------------------
# Flask + SocketIO Setup
# ---------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev_secret")  # fallback
socketio = SocketIO(app)

# ---------------------------------------------------------
# Environment Variables
# ---------------------------------------------------------
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
GOOGLE_CREDS = os.environ.get("GOOGLE_CREDS")
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID")

if not ADMIN_PASSWORD:
    raise RuntimeError("ADMIN_PASSWORD must be set as an environment variable")
if not GOOGLE_CREDS:
    raise RuntimeError("GOOGLE_CREDS must be set as an environment variable")
if not SPREADSHEET_ID:
    raise RuntimeError("SPREADSHEET_ID must be set as an environment variable")

# ---------------------------------------------------------
# Google Sheets Setup
# ---------------------------------------------------------
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(GOOGLE_CREDS)
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

sheet = client.open_by_key(SPREADSHEET_ID).sheet1

# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------
def broadcast_queue():
    """Recalculate queue positions and broadcast live to all clients."""
    records = sheet.get_all_records()

    # Only active (Pending) orders
    active_orders = [o for o in records if o.get("Status", "").lower() != "done"]

    # Assign queue numbers dynamically
    for idx, order in enumerate(active_orders, start=1):
        order["QueueNumber"] = idx

    # Push update to all clients
    socketio.emit("queue_update", active_orders)
    return active_orders

# ---------------------------------------------------------
# Routes
# ---------------------------------------------------------
@app.route("/")
def form():
    return render_template("index.html", page="form")


@app.route("/submit", methods=["POST"])
def submit():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    copies = request.form.get("copies", "0").strip()
    amount = request.form.get("amount", "0").strip()
    timestamp = request.form.get("timestamp", "").strip()

    # sanitize inputs
    name = re.sub(r"[^a-zA-Z0-9\s]", "", name)
    email = re.sub(r"[^a-zA-Z0-9@._-]", "", email)

    # validate numbers
    try:
        copies = int(copies)
        amount = float(amount)
        if copies < 1 or amount < 0:
            raise ValueError
    except ValueError:
        flash("Invalid input: Copies must be ≥1 and Amount ≥0.", "error")
        return redirect(url_for("form"))

    # validate email domain if provided
    allowed_domains = ["gmail.com", "up.edu.ph"]
    if email:
        domain = email.split("@")[-1].lower()
        if domain not in allowed_domains:
            flash("Only gmail.com or up.edu.ph emails are allowed.", "error")
            return redirect(url_for("form"))

    # Generate ID
    records = sheet.get_all_records()
    new_id = len(records) + 1

    # fallback timestamp if missing
    if not timestamp:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Save to Google Sheets
    sheet.append_row([new_id, name, email, copies, amount, "Pending", timestamp])

    # Broadcast live queue
    broadcast_queue()

    return render_template("index.html", page="thanks", position=new_id)


@app.route("/queue")
def queue():
    orders = sheet.get_all_records()
    return render_template("index.html", page="queue", orders=orders)


@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == ADMIN_PASSWORD:
            session["is_admin"] = True
            return redirect(url_for("dashboard"))
        else:
            return render_template("index.html", page="login", error="Incorrect password.")

    return render_template("index.html", page="login")


@app.route("/dashboard")
def dashboard():
    if not session.get("is_admin"):
        return redirect(url_for("admin"))

    orders = sheet.get_all_records()
    return render_template("index.html", page="admin", orders=orders)


@app.route("/toggle/<int:order_id>", methods=["POST"])
def toggle(order_id):
    if not session.get("is_admin"):
        return redirect(url_for("admin"))

    data = sheet.get_all_records()
    for idx, row in enumerate(data, start=2):  # start=2 because of headers
        if row["ID"] == order_id:
            new_status = "Done" if row["Status"] == "Pending" else "Pending"
            sheet.update_cell(idx, 6, new_status)  # Status column is 6th
            # Broadcast queue update
            broadcast_queue()
            break

    return redirect(url_for("dashboard"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("admin"))


# ---------------------------------------------------------
# Run App (for local dev, Render uses gunicorn)
# ---------------------------------------------------------
if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
