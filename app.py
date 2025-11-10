# app.py
# -*- coding: utf-8 -*-

from flask import Flask, render_template, request, redirect, url_for, flash

app = Flask(__name__)
app.config['SECRET_KEY'] = "change-this-key"

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        # כאן אפשר להוסיף שליחה למייל / שמירה
        flash("הפנייה נשלחה בהצלחה! נחזור אליך בהקדם.", "success")
        return redirect(url_for("contact"))
    return render_template("contact.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        # דמו בסיסי: מייל מכללת צפת + סיסמה לא ריקה
        if email.endswith("@zefat.ac.il") and password:
            return redirect("https://students-placement-lecturer.onrender.com")
        else:
            flash("התחברות נכשלה. יש להזין מייל מכללת צפת וסיסמה.", "error")
            return redirect(url_for("login"))

    return render_template("login.html")


if __name__ == "__main__":
    # להרצה מקומית
    app.run(host="0.0.0.0", port=5000, debug=True)
