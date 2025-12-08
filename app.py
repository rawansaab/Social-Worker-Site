from flask import Flask, render_template, request, redirect, url_for, flash, session
from markupsafe import Markup  # <-- התיקון כאן
import os
from whitenoise import WhiteNoise
import smtplib
from email.message import EmailMessage
from itsdangerous import URLSafeTimedSerializer

app = Flask(__name__)
# ודא שמפתח זה מוגדר כמשתנה סביבה בסביבת הפרודקשן שלך
app.config['SECRET_KEY'] = os.getenv("FLASK_SECRET_KEY", "change-this-key-in-development")
# מחולל טוקנים לקישורי איפוס
serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])

def send_reset_email(to_email, reset_url):
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    from_email = os.getenv("FROM_EMAIL", smtp_user)

    msg = EmailMessage()
    msg["Subject"] = "איפוס סיסמה למערכת שיבוץ סטודנטים"
    msg["From"] = from_email
    msg["To"] = to_email
    msg.set_content(
        f"""שלום,\n\nהתבקש איפוס סיסמה למערכת.\n\nלקישור לאיפוס סיסמה לחצי כאן:\n{reset_url}\n\nאם לא את ביקשת – ניתן להתעלם מהודעה זו."""
    )

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)

@app.before_request
def maintenance_mode():
    # בודק אם אנחנו לא בנתיב של מרצה (כדי לא לנעול מרצים בחוץ)
    if not request.path.startswith('/lecturer') and not request.path.startswith('/login'):
        if os.getenv("MAINTENANCE_MODE", "0") == "1":
            html = """
            <html lang="he" dir="rtl">
            <head>
              <meta charset="utf-8">
              <title>האתר סגור</title>
              <style>
                body{
                  font-family:system-ui,-apple-system,Segoe UI,Heebo,Arial;
                  background:#f8fafc;
                  direction:rtl;
                  text-align:center;
                  margin:0;
                  padding-top:120px;
                  color:#111827;
                }
                .box{
                  display:inline-block;
                  padding:32px 40px;
                  border-radius:18px;
                  background:#ffffff;
                  box-shadow:0 10px 30px rgba(15,23,42,.08);
                  border:1px solid #e5e7eb;
                }
                h1{margin:0 0 12px;font-size:26px;}
                p{margin:0;color:#6b7280;}
              </style>
            </head>
            <body>
              <div class="box">
                <h1>⚙️ האתר סגור כרגע</h1>
                <p>הגישה לאתר מערכת חכמה לשיבוץ סטודנטים להתמחויות בעבודה סוציאלית הוגבלה זמנית.</p>
              </div>
            </body>
            </html>
            """
            return Markup(html), 503

# --- דפים ציבוריים ---

@app.route("/")
def index():
    # דף הבית הראשי הוא 'matching.html' כפי שמופיע בתמונות
    return render_template("matching.html")

@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        # לוגיקת שליחת אימייל (דמו)
        flash("הפנייה נשלחה בהצלחה! נחזור אליך בהקדם.", "success")
        return redirect(url_for("contact"))
    return render_template("contact.html")

# --- תהליך אימות מרצים ---

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        # כאן תוסיף לוגיקה לשמירת המשתמש במסד נתונים
        flash(f"הרשמה עבור {email} נקלטה (דמו).", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        # כאן תוסיף לוגיקה לבדיקת אימייל וסיסמה מול מסד נתונים
        
        # אם האימייל והסיסמה נכונים (בדמו, אנחנו מדלגים לבדיקה הבאה)
        if email and password:
            # שמור ב-session שהשלב הראשון עבר בהצלחה
            session['awaiting_secret_auth'] = email
            return redirect(url_for("verify_secret"))
        else:
            flash("נא למלא אימייל וסיסמה.", "error")
            
    return render_template("login.html")
# --- שכחתי סיסמה ---

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email")

        if not email:
            flash("נא להזין כתובת דוא\"ל.", "error")
            return redirect(url_for("forgot_password"))

        # כאן בד״כ בודקים שהאימייל קיים ב-DB
        # user = User.query.filter_by(email=email).first()
        # if not user: ...

        # מייצרים טוקן מבוסס אימייל
        token = serializer.dumps(email, salt="password-reset")
        reset_url = url_for("reset_password", token=token, _external=True)

        try:
            send_reset_email(email, reset_url)
            flash("נשלח קישור לאיפוס סיסמה לכתובת הדוא\"ל המוסדית (אם קיימת במערכת).", "success")
        except Exception as e:
            print("MAIL ERROR:", e)
            flash("אירעה שגיאה בשליחת המייל. נסי שוב מאוחר יותר.", "error")

        return redirect(url_for("forgot_password"))

    return render_template("forgot_password.html")
@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    try:
        email = serializer.loads(token, salt="password-reset", max_age=3600)  # שעה
    except Exception:
        flash("קישור האיפוס פג תוקף או לא תקין.", "error")
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        new_pass = request.form.get("password")
        confirm_pass = request.form.get("confirm_password")

        if new_pass != confirm_pass:
            flash("הסיסמאות אינן תואמות.", "error")
            return redirect(request.url)

        # כאן תשמרי את הסיסמה החדשה עבור המשתמש עם האימייל הזה ב-DB
        # user = User.query.filter_by(email=email).first()
        # user.password = hash_password(new_pass)
        # db.session.commit()

        flash("הסיסמה אופסה בהצלחה! אפשר להתחבר כעת.", "success")
        return redirect(url_for("login"))

    return render_template("reset_password.html")

@app.route("/verify-secret", methods=["GET", "POST"])
def verify_secret():
    # אם המשתמש לא עבר את שלב 1 (לוגין), החזר אותו לשם
    if 'awaiting_secret_auth' not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        secret = request.form.get("secret_password")
        # טען את הסיסמה הסודית ממשתני הסביבה
        LECTURER_SECRET = os.getenv("LECTURER_SECRET")

        if secret == LECTURER_SECRET:
            # האימות הושלם!
            session.pop('awaiting_secret_auth', None) # נקה את הסמן הזמני
            session['lecturer_email'] = session.get('awaiting_secret_auth', 'lecturer@zefat.ac.il') # שמור את המשתמש ב-session
            flash("התחברת בהצלחה!", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("סיסמת מרצים סודית שגויה.", "error")
            
    return render_template("verify_secret.html")

@app.route("/logout")
def logout():
    session.pop('lecturer_email', None)
    flash("יצאת בהצלחה מהמערכת.", "success")
    return redirect(url_for("index"))

# --- אזור מרצים מחוברים ---

# פונקציית עזר לבדיקת התחברות
def check_auth():
    if 'lecturer_email' not in session:
        flash("נא להתחבר למערכת המרצים תחילה.", "error")
        return redirect(url_for("login"))
    return None # מאושר

@app.route("/dashboard")
def dashboard():
    auth_redirect = check_auth()
    if auth_redirect: return auth_redirect
    
    # כאן תטען נתונים אמיתיים מה-DB
    stats = {
        "registered_students": 0,
        "registered_mentors": 0,
        "success_rate": 0,
        "placements_done": 0
    }
    return render_template("dashboard.html", stats=stats)

@app.route("/analytics", methods=["GET", "POST"])
def analytics():
    auth_redirect = check_auth()
    if auth_redirect: return auth_redirect

    if request.method == "POST":
        results_file = request.files.get('results_file')
        if not results_file:
            return render_template("analytics.html", error="לא נבחר קובץ.")
        
        # כאן תהיה הלוגיקה של ניתוח הקובץ (pandas, etc.)
        # ...
        
        # בדמו, נציג נתונים מזויפים
        tables = {
            "cols": {"site": "מקום הכשרה", "field": "תחום התמחות"},
            "by_site": [
                {"מקום הכשרה": "בית חולים א'", "מספר סטודנטים": 5},
                {"מקום הכשרה": "לשכת רווחה ב'", "מספר סטודנטים": 3}
            ],
            "by_field": [
                {"תחום התמחות": "ילד ונוער", "מספר סטודנטים": 4},
                {"תחום התמחות": "קשישים", "מספר סטודנטים": 4}
            ],
            "score_avg": [
                {"מקום הכשרה": "בית חולים א'", "ממוצע התאמה": "85.0%"},
                {"מקום הכשרה": "לשכת רווחה ב'", "ממוצע התאמה": "92.5%"}
            ]
        }
        charts = {
            "site_labels": ["בית חולים א'", "לשכת רווחה ב'"],
            "site_values": [5, 3],
            "field_labels": ["ילד ונוער", "קשישים"],
            "field_values": [4, 4],
            "avg_labels": ["בית חולים א'", "לשכת רווחה ב'"],
            "avg_values": [85.0, 92.5]
        }
        return render_template("analytics.html", tables=tables, charts=charts)

    return render_template("analytics.html")

@app.route("/placement-system")
def placement_system():
    auth_redirect = check_auth()
    if auth_redirect: return auth_redirect
    
    # קישור חיצוני למערכת השיבוץ
    return redirect("https://www.studentsplacement.org/")

# --- דפי דמו ישנים (אם צריך) ---
@app.route("/students-form")
def students_form():
    return "<h2>כאן יהיה שאלון סטודנטים (דף דמו זמני)</h2>"

@app.route("/mentors-form")
def mentors_form():
    return "<h2>כאן יהיה מיפוי מדריכים (דף דמו זמני)</h2>"

if __name__ == "__main__":
    app.run(debug=True)
