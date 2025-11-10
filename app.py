# app.py
# -*- coding: utf-8 -*-

import os
from functools import wraps
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
)

app = Flask(__name__)

# מפתח להצפנת session
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET", "devkey")

# סיסמה סודית למרצים - מגיעה מ-Render
LECTURER_SECRET = os.environ.get("LECTURER_SECRET")
if not LECTURER_SECRET:
    raise RuntimeError("LECTURER_SECRET is not set in environment")


# ---------- דף הבית ----------
@app.route("/")
def index():
    return render_template("index.html")


# ---------- יצירת קשר ----------
@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        # אפשר בעתיד לשמור / לשלוח מייל; כרגע רק הודעת אישור
        name = request.form.get("name")
        flash("הפנייה נשלחה בהצלחה. נחזור אליך בהקדם.", "success")
        return redirect(url_for("contact"))
    return render_template("contact.html")


# ---------- דקורטור: דרוש חיבור מרצה ----------
def lecturer_login_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if session.get("is_lecturer"):
            return view_func(*args, **kwargs)
        return redirect(url_for("lecturer_login"))
    return wrapper


# ---------- התחברות מרצים ----------
@app.route("/login", methods=["GET", "POST"])
def lecturer_login():
    error = None

    if request.method == "POST":
        password = request.form.get("password", "")

        if password == LECTURER_SECRET:
            session["is_lecturer"] = True
            return redirect(url_for("lecturers_area"))
        else:
            error = "סיסמה שגויה. אנא בדקו עם רואן."

    # שימי לב: כאן אנחנו טוענים את login.html כפי שקיים אצלך
    return render_template("login.html", error=error)


# ---------- יציאה ----------
@app.route("/logout")
def logout():
    session.clear()
    flash("התנתקת בהצלחה.", "info")
    return redirect(url_for("index"))


# ---------- אזור מרצים מוגן ----------
@app.route("/lecturers")
@lecturer_login_required
def lecturers_area():
    return render_template("lecturers.html")


# ---------- להרצה מקומית ----------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
