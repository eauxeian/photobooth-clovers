import os
import json
import re
from datetime import datetime

import gspread
from oauth2client.service_account import ServiceAccountCredentials
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_socketio import SocketIO

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev_secret")
socketio = SocketIO(app, cors_allowed_origins="*")

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
GOOGLE_CREDS = os.environ.get("GOOGLE_CREDS")
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID")

if not ADMIN_PASSWORD or not GOOGLE_CREDS or not SPREADSHEET_ID:
    raise RuntimeError("Missing environment variables")

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]
creds = ServiceAccountCredentials.from_json_keyfile_dict(
    json.loads(GOOGLE_CREDS), scope
)
client = gspread.authorize(creds)
sheet = client.open_by_key(SPREADSHEET_ID).sheet1

# 🔒 Cleared IDs live ONLY in memory (not Sheets)
CLEARED_IDS = set()

def valid_email(email):
    if not email:
        return True
    return bool(re.match(r"^[^@]+@(gmail\.com|up\.edu\.ph)$", email, re.IGNORECASE))

def get_records():
    headers = [
        "ID", "Name", "Email", "Copies", "Amount Paid",
        "Status", "Printed", "Claimed", "Timestamp"
    ]
    return sheet.get_all_records(expected_headers=headers)

def broadcast_queue():
    records = get_records()

    visible = [r for r in records if r["ID"] not in CLEARED_IDS]

    pending = [r for r in visible if r["Status"] == "Pending"]
    for i, r in enumerate(pending, start=1):
        r["QueueNumber"] = i

    socketio.emit("queue_update", {
        "all": visible,
        "pending": pending
    })

@socketio.on("connect")
def on_connect():
    broadcast_queue()

@app.route("/")
def form():
    return render_template("index.html", page="form")

@app.route("/submit", methods=["POST"])
def submit():
    name = re.sub(r"[^a-zA-Z0-9\s]", "", request.form.get("name", "").strip())
    email = re.sub(r"[^a-zA-Z0-9@._-]", "", request.form.get("email", "").strip().lower())
    copies = int(request.form.get("copies", 1))
    amount = float(request.form.get("amount", 0))
    timestamp = request.form.get("timestamp") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not valid_email(email):
        flash("Invalid email domain", "error")
        return redirect(url_for("form"))

    records = get_records()
    new_id = len(records) + 1

    sheet.append_row([
        new_id, name, email, copies, amount,
        "Pending", "No", "No", timestamp
    ])

    broadcast_queue()
    return redirect(url_for("thanks", position=new_id))

@app.route("/thanks/<int:position>")
def thanks(position):
    return render_template("index.html", page="thanks", position=position)

@app.route("/queue")
def queue():
    return render_template("index.html", page="queue")

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["is_admin"] = True
            return redirect(url_for("dashboard"))
        return render_template("index.html", page="login", error="Wrong password")
    return render_template("index.html", page="login")

@app.route("/dashboard")
def dashboard():
    if not session.get("is_admin"):
        return redirect(url_for("admin"))
    return render_template("index.html", page="admin")

@app.route("/toggle/<int:order_id>", methods=["POST"])
def toggle_status(order_id):
    if not session.get("is_admin"):
        return redirect(url_for("admin"))

    for i, r in enumerate(get_records(), start=2):
        if r["ID"] == order_id:
            if r["Status"] == "Pending":
                sheet.update_cell(i, 6, "Done")
                sheet.update_cell(i, 7, "Yes")
            else:
                sheet.update_cell(i, 6, "Pending")
                sheet.update_cell(i, 7, "No")
                sheet.update_cell(i, 8, "No")
            break

    broadcast_queue()
    return redirect(url_for("dashboard"))

@app.route("/toggle_printed/<int:order_id>", methods=["POST"])
def toggle_printed(order_id):
    if not session.get("is_admin"):
        return redirect(url_for("admin"))

    for i, r in enumerate(get_records(), start=2):
        if r["ID"] == order_id:
            sheet.update_cell(i, 7, "No" if r["Printed"] == "Yes" else "Yes")
            break

    broadcast_queue()
    return redirect(url_for("dashboard"))

@app.route("/toggle_claimed/<int:order_id>", methods=["POST"])
def toggle_claimed(order_id):
    if not session.get("is_admin"):
        return redirect(url_for("admin"))

    for i, r in enumerate(get_records(), start=2):
        if r["ID"] == order_id:
            sheet.update_cell(i, 8, "No" if r["Claimed"] == "Yes" else "Yes")
            break

    broadcast_queue()
    return redirect(url_for("dashboard"))

# 🧹 Clear (UI only, NOT Sheets)
@app.route("/clear/<int:order_id>", methods=["POST"])
def clear_order(order_id):
    if not session.get("is_admin"):
        return redirect(url_for("admin"))

    CLEARED_IDS.add(order_id)
    broadcast_queue()
    return redirect(url_for("dashboard"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("admin"))

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
