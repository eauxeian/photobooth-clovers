import os
import re
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_socketio import SocketIO
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json

# ---------------------------------------------------------
# Flask + SocketIO Setup
# ---------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev_secret")  # dev fallback
socketio = SocketIO(app)

# ---------------------------------------------------------
# Environment Variables
# ---------------------------------------------------------
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
if not ADMIN_PASSWORD:
    raise RuntimeError("ADMIN_PASSWORD must be set as an environment variable")

GOOGLE_CREDS = os.environ.get("GOOGLE_CREDS")
if not GOOGLE_CREDS:
    raise RuntimeError("GOOGLE_CREDS must be set as an environment variable")

# ---------------------------------------------------------
# Google Sheets Setup
# ---------------------------------------------------------
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(GOOGLE_CREDS)
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# ✅ Use Spreadsheet ID instead of name
SPREADSHEET_ID = "19j-OddWhztjAPP3y3RobEeU4nM9ejJlFy2ZoHGKPShM"
sheet = client.open_by_key(SPREADSHEET_ID).sheet1

# ---------------------------------------------------------
# Routes
# ---------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html", page="form")


@app.route("/submit", methods=["POST"])
def submit():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    copies = request.form.get("copies", "0").strip()
    amount = request.form.get("amount", "0").strip()

    # ✅ Sanitize
    name = re.sub(r"[^a-zA-Z0-9\s]", "", name)
    email = re.sub(r"[^a-zA-Z0-9@._-]", "", email)

    # ✅ Validate numbers
    try:
        copies = int(copies)
        amount = float(amount)
        if copies < 1 or amount < 0:
            raise ValueError
    except ValueError:
        flash("Invalid input: Copies must be ≥1 and Amount ≥0.", "error")
        return redirect(url_for("index"))

    # ✅ Save to Google Sheet
    sheet.append_row([name, email, copies, amount])
    socketio.emit("new_submission", {"name": name, "email": email, "copies": copies, "amount": amount})

    # queue position
    records = sheet.get_all_records()
    position = len(records)

    return render_template("index.html", page="thanks", position=position)


@app.route("/queue")
def queue():
    records = sheet.get_all_records()
    return render_template("index.html", page="queue", orders=records)


@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == ADMIN_PASSWORD:
            session["is_admin"] = True
            return redirect(url_for("dashboard"))
        else:
            return render_template("index.html", page="login", error="Incorrect admin password.")
    return render_template("index.html", page="login")


@app.route("/dashboard")
def dashboard():
    if not session.get("is_admin"):
        return redirect(url_for("admin"))

    records = sheet.get_all_records()
    return render_template("index.html", page="admin", orders=records)


@app.route("/logout")
def logout():
    session.pop("is_admin", None)
    return redirect(url_for("index"))

# ---------------------------------------------------------
# Run App
# ---------------------------------------------------------
if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
