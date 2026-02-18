import os
import json
import re
import time
from datetime import datetime

import gspread
from oauth2client.service_account import ServiceAccountCredentials
from flask import Flask, render_template, request, redirect, url_for, flash, session
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


# ===============================
# HELPERS
# ===============================

CACHE = {"data": None, "time": 0}


def valid_email(email):
    if not email:
        return True
    return bool(
        re.fullmatch(r"[A-Za-z0-9._%+-]+@(gmail\.com|up\.edu\.ph)", email)
    )


def valid_facebook(link):
    if not link:
        return True
    return bool(
        re.fullmatch(r"https?://(www\.)?facebook\.com/.+", link, re.IGNORECASE)
    )


def valid_order_type(order_type):
    return order_type in ["Stickers", "Charm Bracelet", "Photo Booth"]


def get_records():
    global CACHE

    headers = [
        "ID", "Name", "Email", "Facebook", "Order Type", "Quantity",
        "Amount Paid", "Status", "Printed", "Claimed", "Timestamp", "Hidden", "Liked Page"
    ]

    now = time.time()

    # 2-second cache
    if CACHE["data"] and now - CACHE["time"] < 2:
        return CACHE["data"]

    records = sheet.get_all_records(expected_headers=headers)

    for r in records:
        r["ID"] = int(r["ID"])
        r["Status"] = str(r["Status"]).strip()
        r["Printed"] = str(r["Printed"]).strip()
        r["Claimed"] = str(r["Claimed"]).strip()
        r["Hidden"] = str(r.get("Hidden", "No")).strip()

    CACHE = {"data": records, "time": now}
    return records


def broadcast_queue():
    records = get_records()

    visible = [r for r in records if r.get("Hidden", "No") != "Yes"]

    pending = [
        r for r in visible
        if r["Status"].lower() == "pending"
    ]

    # Sort by timestamp
    pending.sort(key=lambda r: r["Timestamp"])

    for i, r in enumerate(pending, start=1):
        r["QueueNumber"] = i

    socketio.emit("queue_update", {
        "all": visible,
        "pending": pending
    })


@socketio.on("connect")
def on_connect():
    broadcast_queue()


# ===============================
# ROUTES
# ===============================

@app.route("/")
def form():
    return render_template("index.html", page="form")


@app.route("/submit", methods=["POST"])
def submit():
    name = re.sub(r"[^a-zA-Z0-9\s]", "", request.form.get("name", "").strip())

    email = request.form.get("email", "").strip().lower()
    facebook = request.form.get("facebook", "").strip()
    order_types = request.form.getlist("order_type[]")
    quantities = request.form.getlist("quantity[]")
    amount = float(request.form.get("amount", 0))

    timestamp = request.form.get("timestamp") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    liked_page = "Yes" if request.form.get("liked_page") else "No"

    if liked_page == "No":
        flash("You must like the Sneak Attack Facebook page first.", "error")
        return redirect(url_for("form"))

    if not valid_email(email):
        flash("Invalid email domain", "error")
        return redirect(url_for("form"))

    if not valid_facebook(facebook):
        flash("Invalid Facebook link", "error")
        return redirect(url_for("form"))

    for ot in order_types:
        if not valid_order_type(ot):
            flash("Invalid order type", "error")
            return redirect(url_for("form"))

    group_id = int(datetime.now().timestamp() * 1000)

    if not order_types or not quantities:
        flash("Please add at least one item.", "error")
        return redirect(url_for("form"))

    for order_type, qty in zip(order_types, quantities):
        sheet.append_row([
            group_id,
            name,
            email,
            facebook,
            order_type,
            int(qty),
            amount,
            "Pending",
            "No",
            "No",
            timestamp,
            "No",
            liked_page
        ])

    broadcast_queue()
    return redirect(url_for("thanks", position=group_id))


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
                sheet.update_cell(i, 8, "Done")
                sheet.update_cell(i, 9, "Yes")
            else:
                sheet.update_cell(i, 8, "Pending")
                sheet.update_cell(i, 9, "No")
                sheet.update_cell(i, 10, "No")
            break

    broadcast_queue()
    return redirect(url_for("dashboard"))


@app.route("/toggle_printed/<int:order_id>", methods=["POST"])
def toggle_printed(order_id):
    if not session.get("is_admin"):
        return redirect(url_for("admin"))

    for i, r in enumerate(get_records(), start=2):
        if r["ID"] == order_id:
            sheet.update_cell(i, 9, "No" if r["Printed"] == "Yes" else "Yes")
            break

    broadcast_queue()
    return redirect(url_for("dashboard"))


@app.route("/toggle_claimed/<int:order_id>", methods=["POST"])
def toggle_claimed(order_id):
    if not session.get("is_admin"):
        return redirect(url_for("admin"))

    for i, r in enumerate(get_records(), start=2):
        if r["ID"] == order_id:
            sheet.update_cell(i, 10, "No" if r["Claimed"] == "Yes" else "Yes")
            break

    broadcast_queue()
    return redirect(url_for("dashboard"))


@app.route("/clear/<int:order_id>", methods=["POST"])
def clear_order(order_id):
    if not session.get("is_admin"):
        return redirect(url_for("admin"))

    for i, r in enumerate(get_records(), start=2):
        if r["ID"] == order_id:
            sheet.update_cell(i, 12, "Yes")
            break

    broadcast_queue()
    return redirect(url_for("dashboard"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("admin"))


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
