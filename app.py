from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from markupsafe import Markup
import os
import json
import smtplib
from email.message import EmailMessage
from itsdangerous import URLSafeTimedSerializer
import pandas as pd

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "change-this-key-in-development")

serializer = URLSafeTimedSerializer(app.config["SECRET_KEY"])

DATA_DIR = "data"
STATS_FILE = os.path.join(DATA_DIR, "dashboard_stats.json")


# ======================================================
# עזר כללי
# ======================================================

def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def safe_text(value):
    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass

    return str(value).strip()


def normalize_column_name(value):
    return str(value).strip().replace("\n", " ").replace("\r", " ")


def find_col(df, options):
    clean_map = {}

    for col in df.columns:
        clean_map[normalize_column_name(col)] = col

    for opt in options:
        opt_clean = normalize_column_name(opt)

        if opt_clean in clean_map:
            return clean_map[opt_clean]

    return None


def default_dashboard_stats():
    return {
        "registered_students": 0,
        "registered_mentors": 0,
        "registered_sites": 0,
        "success_rate": "0%",
        "placements_done": 0,
        "avg_score": "0%",
        "last_update": "טרם הועלה קובץ ניתוח"
    }


def load_dashboard_stats():
    ensure_data_dir()

    if not os.path.exists(STATS_FILE):
        return default_dashboard_stats()

    try:
        with open(STATS_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)

        stats = default_dashboard_stats()
        stats.update(saved)
        return stats

    except Exception:
        return default_dashboard_stats()


def save_dashboard_stats(stats):
    ensure_data_dir()

    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)


def read_uploaded_dataframe(uploaded_file):
    filename = (uploaded_file.filename or "").lower()

    if filename.endswith((".xlsx", ".xls")):
        try:
            return pd.read_excel(uploaded_file)
        except ImportError:
            raise RuntimeError("חסרה ספריית openpyxl. הריצי בטרמינל: pip install openpyxl")

    try:
        return pd.read_csv(uploaded_file, encoding="utf-8-sig")
    except UnicodeDecodeError:
        uploaded_file.stream.seek(0)
        return pd.read_csv(uploaded_file, encoding="cp1255")


def normalize_analytics_columns(df):
    df = df.copy()
    df.columns = [normalize_column_name(c) for c in df.columns]

    site_col = find_col(df, [
        "שם מקום ההתמחות",
        "שם מקום הכשרה",
        "שם מקום ההכשרה",
        "מקום התמחות",
        "מקום הכשרה",
        "מוסד / שירות הכשרה",
        "מוסד",
        "שם מוסד ההתמחות",
        "שם המוסד",
        "מוסד ההכשרה"
    ])

    field_col = find_col(df, [
        "תחום התמחות",
        "תחום ההתמחות",
        "תחום ההתמחות במוסד",
        "תחום",
        "תחום מועדף"
    ])

    score_col = find_col(df, [
        "אחוז התאמה",
        "ציון התאמה",
        "ציון סופי",
        "התאמה",
        "score"
    ])

    mentor_col = find_col(df, [
        "שם המדריך/ה",
        "שם המדריך",
        "מדריך/ה",
        "מדריך",
        "שם מנחה"
    ])

    student_id_col = find_col(df, [
        "תעודת זהות",
        "ת\"ז הסטודנט",
        "תז הסטודנט",
        "מספר תעודת זהות",
        "ת\"ז",
        "תז"
    ])

    student_name_col = find_col(df, [
        "שם הסטודנט/ית",
        "שם סטודנט",
        "שם הסטודנט",
        "סטודנט/ית"
    ])

    first_name_col = find_col(df, ["שם פרטי"])
    last_name_col = find_col(df, ["שם משפחה"])

    manual_col = find_col(df, [
        "עודכן ידנית?",
        "התערבות ידנית",
        "עדכון ידני",
        "שינוי ידני",
        "עודכן ידנית"
    ])

    city_col = find_col(df, [
        "עיר המוסד",
        "עיר מקום ההתמחות",
        "עיר"
    ])

    rename_map = {}

    if site_col:
        rename_map[site_col] = "שם מקום ההתמחות"
    if field_col:
        rename_map[field_col] = "תחום התמחות"
    if score_col:
        rename_map[score_col] = "אחוז התאמה"
    if mentor_col:
        rename_map[mentor_col] = "שם המדריך/ה"
    if student_id_col:
        rename_map[student_id_col] = "תעודת זהות"
    if student_name_col:
        rename_map[student_name_col] = "שם הסטודנט/ית"
    if manual_col:
        rename_map[manual_col] = "עודכן ידנית?"
    if city_col:
        rename_map[city_col] = "עיר המוסד"

    df = df.rename(columns=rename_map)

    if "שם הסטודנט/ית" not in df.columns and first_name_col and last_name_col:
        df["שם הסטודנט/ית"] = (
            df[first_name_col].apply(safe_text) + " " + df[last_name_col].apply(safe_text)
        ).str.strip()

    for col in [
        "שם מקום ההתמחות",
        "תחום התמחות",
        "שם המדריך/ה",
        "שם הסטודנט/ית",
        "תעודת זהות",
        "עודכן ידנית?",
        "עיר המוסד"
    ]:
        if col in df.columns:
            df[col] = df[col].apply(safe_text)

    if "אחוז התאמה" in df.columns:
        df["אחוז התאמה"] = (
            df["אחוז התאמה"]
            .astype(str)
            .str.replace("%", "", regex=False)
            .str.strip()
        )
        df["אחוז התאמה"] = pd.to_numeric(df["אחוז התאמה"], errors="coerce")

    return df


def build_analytics_payload(df):
    df = normalize_analytics_columns(df)

    required_cols = ["שם מקום ההתמחות", "תחום התמחות"]
    missing = [c for c in required_cols if c not in df.columns]

    if missing:
        available_cols = ", ".join([str(c) for c in df.columns])
        raise ValueError(
            "הקובץ לא מכיל את העמודות הדרושות: "
            + ", ".join(missing)
            + ". העמודות שנמצאו בקובץ הן: "
            + available_cols
        )

    df = df.copy()

    df["שם מקום ההתמחות"] = df["שם מקום ההתמחות"].replace("", "לא צוין")
    df["תחום התמחות"] = df["תחום התמחות"].replace("", "לא צוין")

    total_rows = len(df)

    valid_placements = df[
        (df["שם מקום ההתמחות"] != "לא שובץ") &
        (df["שם מקום ההתמחות"] != "לא צוין")
    ].copy()

    if "תעודת זהות" in df.columns:
        total_students = int(df["תעודת זהות"].replace("", pd.NA).dropna().nunique())
        if total_students == 0:
            total_students = total_rows
    else:
        total_students = total_rows

    placements_done = int(len(valid_placements))
    success_rate_num = round((placements_done / total_rows) * 100, 1) if total_rows else 0

    registered_sites = int(valid_placements["שם מקום ההתמחות"].nunique()) if not valid_placements.empty else 0

    if "שם המדריך/ה" in df.columns:
        registered_mentors = int(df["שם המדריך/ה"].replace("", pd.NA).dropna().nunique())
    else:
        registered_mentors = 0

    has_score = "אחוז התאמה" in df.columns and df["אחוז התאמה"].notna().any()

    if has_score:
        score_df = df.dropna(subset=["אחוז התאמה"]).copy()
    else:
        score_df = pd.DataFrame()

    if has_score and not score_df.empty:
        avg_score_num = round(score_df["אחוז התאמה"].mean(), 1)
        low_score_count = int((score_df["אחוז התאמה"] < 60).sum())
        high_score_count = int((score_df["אחוז התאמה"] >= 85).sum())
    else:
        avg_score_num = 0
        low_score_count = 0
        high_score_count = 0

    if "עודכן ידנית?" in df.columns:
        manual_values = df["עודכן ידנית?"].astype(str).str.lower().str.strip()
        manual_count = int(manual_values.isin(["כן", "yes", "true", "1", "עודכן"]).sum())
    else:
        manual_count = 0

    auto_count = max(total_rows - manual_count, 0)

    by_site = (
        valid_placements
        .groupby("שם מקום ההתמחות")
        .size()
        .reset_index(name="מספר סטודנטים")
        .sort_values("מספר סטודנטים", ascending=False)
    )

    by_field = (
        df
        .groupby("תחום התמחות")
        .size()
        .reset_index(name="מספר סטודנטים")
        .sort_values("מספר סטודנטים", ascending=False)
    )

    if "שם המדריך/ה" in df.columns:
        by_mentor = (
            df[df["שם המדריך/ה"] != ""]
            .groupby("שם המדריך/ה")
            .size()
            .reset_index(name="מספר סטודנטים")
            .sort_values("מספר סטודנטים", ascending=False)
        )
    else:
        by_mentor = pd.DataFrame(columns=["שם המדריך/ה", "מספר סטודנטים"])

    if has_score and not score_df.empty:
        score_avg = (
            score_df
            .groupby("שם מקום ההתמחות")["אחוז התאמה"]
            .mean()
            .round(1)
            .reset_index(name="ממוצע התאמה")
            .sort_values("ממוצע התאמה", ascending=False)
        )

        score_avg_table = score_avg.copy()
        score_avg_table["ממוצע התאמה"] = score_avg_table["ממוצע התאמה"].astype(str) + "%"

        bins = [-1, 59, 74, 84, 100]
        labels = ["0–59", "60–74", "75–84", "85–100"]
        score_categories = pd.cut(score_df["אחוז התאמה"], bins=bins, labels=labels)
        score_dist = score_categories.value_counts().reindex(labels, fill_value=0)

        low_cols = []
        for col in ["שם הסטודנט/ית", "שם מקום ההתמחות", "תחום התמחות", "אחוז התאמה"]:
            if col in score_df.columns:
                low_cols.append(col)

        low_students = (
            score_df[score_df["אחוז התאמה"] < 60][low_cols]
            .sort_values("אחוז התאמה", ascending=True)
            .head(10)
        )
    else:
        score_avg = pd.DataFrame(columns=["שם מקום ההתמחות", "ממוצע התאמה"])
        score_avg_table = pd.DataFrame(columns=["שם מקום ההתמחות", "ממוצע התאמה"])
        score_dist = pd.Series([], dtype=int)
        low_students = pd.DataFrame()

    most_popular_site = by_site.iloc[0]["שם מקום ההתמחות"] if not by_site.empty else "אין נתונים"
    most_popular_field = by_field.iloc[0]["תחום התמחות"] if not by_field.empty else "אין נתונים"

    if has_score and not score_avg.empty:
        best_avg_text = (
            str(score_avg.iloc[0]["שם מקום ההתמחות"])
            + " ("
            + str(score_avg.iloc[0]["ממוצע התאמה"])
            + "%)"
        )
    else:
        best_avg_text = "אין עמודת אחוז התאמה"

    summary = {
        "total_students": total_students,
        "placements_done": placements_done,
        "registered_sites": registered_sites,
        "registered_mentors": registered_mentors,
        "success_rate": f"{success_rate_num}%",
        "avg_score": f"{avg_score_num}%",
        "manual_count": manual_count,
        "auto_count": auto_count,
        "low_score_count": low_score_count,
        "high_score_count": high_score_count,
        "most_popular_site": most_popular_site,
        "most_popular_field": most_popular_field,
        "best_avg_text": best_avg_text
    }

    tables = {
        "by_site": by_site.to_dict(orient="records"),
        "by_field": by_field.to_dict(orient="records"),
        "by_mentor": by_mentor.to_dict(orient="records"),
        "score_avg": score_avg_table.to_dict(orient="records"),
        "low_students": low_students.to_dict(orient="records") if not low_students.empty else []
    }

    charts = {
        "site_labels": by_site["שם מקום ההתמחות"].tolist(),
        "site_values": by_site["מספר סטודנטים"].astype(int).tolist(),

        "field_labels": by_field["תחום התמחות"].tolist(),
        "field_values": by_field["מספר סטודנטים"].astype(int).tolist(),

        "mentor_labels": by_mentor["שם המדריך/ה"].tolist()[:10] if not by_mentor.empty else [],
        "mentor_values": by_mentor["מספר סטודנטים"].astype(int).tolist()[:10] if not by_mentor.empty else [],

        "avg_labels": score_avg["שם מקום ההתמחות"].tolist() if not score_avg.empty else [],
        "avg_values": score_avg["ממוצע התאמה"].astype(float).tolist() if not score_avg.empty else [],

        "score_labels": list(score_dist.index.astype(str)) if len(score_dist) else [],
        "score_values": [int(v) for v in score_dist.tolist()] if len(score_dist) else [],

        "manual_labels": ["שיבוץ אוטומטי", "עודכן ידנית"],
        "manual_values": [auto_count, manual_count]
    }

    dashboard_stats = {
        "registered_students": total_students,
        "registered_mentors": registered_mentors,
        "registered_sites": registered_sites,
        "success_rate": f"{success_rate_num}%",
        "placements_done": placements_done,
        "avg_score": f"{avg_score_num}%",
        "last_update": pd.Timestamp.now().strftime("%d/%m/%Y %H:%M")
    }

    save_dashboard_stats(dashboard_stats)

    return summary, tables, charts


# ======================================================
# מייל איפוס סיסמה
# ======================================================

def send_reset_email(to_email, reset_url):
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    from_email = os.getenv("FROM_EMAIL", smtp_user)

    if not smtp_host or not smtp_user or not smtp_pass:
        raise RuntimeError("SMTP settings are missing.")

    msg = EmailMessage()
    msg["Subject"] = "איפוס סיסמה למערכת שיבוץ סטודנטים"
    msg["From"] = from_email
    msg["To"] = to_email
    msg.set_content(
        f"""שלום,

התבקש איפוס סיסמה למערכת.

קישור לאיפוס סיסמה:
{reset_url}

אם לא את ביקשת – ניתן להתעלם מהודעה זו.
"""
    )

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)


# ======================================================
# מצב תחזוקה
# ======================================================

@app.before_request
def maintenance_mode():
    allowed_paths = ["/login", "/verify-secret", "/static"]

    if any(request.path.startswith(path) for path in allowed_paths):
        return None

    if os.getenv("MAINTENANCE_MODE", "0") == "1":
        html = """
        <html lang="he" dir="rtl">
        <head>
          <meta charset="utf-8">
          <title>האתר סגור</title>
          <style>
            body{
              font-family:Heebo,system-ui,-apple-system,Segoe UI,Arial;
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
            <p>הגישה לאתר מערכת השיבוץ הוגבלה זמנית.</p>
          </div>
        </body>
        </html>
        """
        return Markup(html), 503

    return None


# ======================================================
# דפים ציבוריים
# ======================================================

@app.route("/")
def index():
    return render_template("matching.html")


@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        flash("הפנייה נשלחה בהצלחה! נחזור אליך בהקדם.", "success")
        return redirect(url_for("contact"))

    return render_template("contact.html")


# ======================================================
# צ'אט
# ======================================================

CHAT_KNOWLEDGE = [
    {
        "keywords": ["שיבוץ", "תהליך", "איך עובד", "איך זה עובד", "התאמה"],
        "answer": """תהליך השיבוץ עובד בשלושה שלבים:
1. הסטודנטים ממלאים שאלון עם פרטים, תחום מועדף ובקשות מיוחדות.
2. המדריכים/מקומות ההתמחות ממלאים מיפוי עם תחום, עיר, קיבולת ופרטי מדריך.
3. המערכת מחשבת התאמה ומפיקה קובץ תוצאות מסודר."""
    },
    {
        "keywords": ["שאלון סטודנט", "סטודנטים", "מילוי שאלון", "student"],
        "answer": """שאלון הסטודנט מיועד לאיסוף נתוני הסטודנטים: פרטים אישיים, עיר מגורים, תחום מועדף ובקשות מיוחדות.
אפשר להיכנס אליו דרך הכפתור 'שאלון סטודנט' בדף הבית."""
    },
    {
        "keywords": ["מדריך", "מדריכים", "מיפוי", "מקום התמחות", "mentor"],
        "answer": """מיפוי המדריכים נועד לאיסוף נתונים ממקומות ההתמחות: שם מקום ההכשרה, תחום התמחות, עיר, קיבולת, שם מדריך/ה ופרטי קשר."""
    },
    {
        "keywords": ["ניתוח", "סטטיסטיקה", "גרף", "גרפים", "דוח"],
        "answer": """בדף הניתוחים הסטטיסטיים אפשר להעלות קובץ תוצאות שיבוץ ולקבל סיכום נתונים, גרפים, ממוצע התאמה, התפלגות תחומים ומקומות לבדיקה."""
    },
    {
        "keywords": ["כמה סטודנטים", "כמה מדריכים", "נתונים", "מספרים", "סטטוס"],
        "answer": "DYNAMIC_STATS"
    }
]


def build_dynamic_stats_answer():
    stats = load_dashboard_stats()

    return f"""לפי הקובץ האחרון שנותח:
סטודנטים: {stats.get("registered_students", 0)}
מדריכים: {stats.get("registered_mentors", 0)}
מקומות התמחות: {stats.get("registered_sites", 0)}
שיבוצים שבוצעו: {stats.get("placements_done", 0)}
אחוז הצלחה: {stats.get("success_rate", "0%")}
ממוצע התאמה: {stats.get("avg_score", "0%")}
עדכון אחרון: {stats.get("last_update", "טרם הועלה קובץ ניתוח")}"""


@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(silent=True) or {}
    message = safe_text(data.get("message", "")).lower()

    if not message:
        return jsonify({"answer": "כתבי שאלה קצרה על השיבוץ, השאלונים או דף הניתוחים."})

    best_item = None
    best_score = 0

    for item in CHAT_KNOWLEDGE:
        score = 0

        for keyword in item["keywords"]:
            if keyword.lower() in message:
                score += 1

        if score > best_score:
            best_score = score
            best_item = item

    if best_item:
        if best_item["answer"] == "DYNAMIC_STATS":
            return jsonify({"answer": build_dynamic_stats_answer()})

        return jsonify({"answer": best_item["answer"]})

    return jsonify({
        "answer": """אני יכולה לעזור בשאלות על:
• תהליך השיבוץ
• שאלון סטודנטים
• מיפוי מדריכים
• ניתוחים סטטיסטיים
• נתונים מהקובץ האחרון

נסי למשל: איך עובד השיבוץ?"""
    })


# ======================================================
# הרשמה / כניסה
# ======================================================

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = safe_text(request.form.get("email"))
        password = safe_text(request.form.get("password"))
        password_confirm = safe_text(request.form.get("password_confirm"))

        if not email or not password or not password_confirm:
            flash("נא למלא את כל השדות.", "error")
            return redirect(url_for("register"))

        if password != password_confirm:
            flash("הסיסמאות אינן תואמות.", "error")
            return redirect(url_for("register"))

        flash(f"הרשמה עבור {email} נקלטה בהצלחה.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = safe_text(request.form.get("email"))
        password = safe_text(request.form.get("password"))

        if email and password:
            session["awaiting_secret_auth"] = email
            return redirect(url_for("verify_secret"))

        flash("נא למלא אימייל וסיסמה.", "error")

    return render_template("login.html")


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = safe_text(request.form.get("email"))

        if not email:
            flash("נא להזין כתובת דוא\"ל.", "error")
            return redirect(url_for("forgot_password"))

        token = serializer.dumps(email, salt="password-reset")
        reset_url = url_for("reset_password", token=token, _external=True)

        try:
            send_reset_email(email, reset_url)
            flash("נשלח קישור לאיפוס סיסמה לכתובת הדוא\"ל המוסדית.", "success")
        except Exception as e:
            print("MAIL ERROR:", e)
            flash("אירעה שגיאה בשליחת המייל. בדקי את הגדרות SMTP.", "error")

        return redirect(url_for("forgot_password"))

    return render_template("forgot_password.html")


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    try:
        email = serializer.loads(token, salt="password-reset", max_age=3600)
    except Exception:
        flash("קישור האיפוס פג תוקף או לא תקין.", "error")
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        new_pass = safe_text(request.form.get("password"))
        confirm_pass = safe_text(request.form.get("confirm_password"))

        if new_pass != confirm_pass:
            flash("הסיסמאות אינן תואמות.", "error")
            return redirect(request.url)

        flash(f"הסיסמה עבור {email} אופסה בהצלחה.", "success")
        return redirect(url_for("login"))

    return render_template("reset_password.html")


@app.route("/verify-secret", methods=["GET", "POST"])
def verify_secret():
    if "awaiting_secret_auth" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        secret = safe_text(request.form.get("secret_password"))
        lecturer_secret = os.getenv("LECTURER_SECRET", "123456")

        if secret == lecturer_secret:
            email = session.pop("awaiting_secret_auth", "lecturer@zefat.ac.il")
            session["lecturer_email"] = email
            flash("התחברת בהצלחה!", "success")
            return redirect(url_for("dashboard"))

        flash("סיסמת מרצים סודית שגויה.", "error")

    return render_template("verify_secret.html")


@app.route("/logout")
def logout():
    session.pop("lecturer_email", None)
    session.pop("awaiting_secret_auth", None)
    flash("יצאת בהצלחה מהמערכת.", "success")
    return redirect(url_for("index"))


# ======================================================
# אזור מרצים
# ======================================================

def check_auth():
    if "lecturer_email" not in session:
        flash("נא להתחבר למערכת המרצים תחילה.", "error")
        return redirect(url_for("login"))

    return None


@app.route("/dashboard")
def dashboard():
    auth_redirect = check_auth()

    if auth_redirect:
        return auth_redirect

    stats = load_dashboard_stats()
    return render_template("dashboard.html", stats=stats)


@app.route("/reset-dashboard-data", methods=["POST"])
def reset_dashboard_data():
    auth_redirect = check_auth()

    if auth_redirect:
        return auth_redirect

    save_dashboard_stats(default_dashboard_stats())
    flash("נתוני הפאנל אופסו בהצלחה.", "success")
    return redirect(url_for("dashboard"))


@app.route("/analytics", methods=["GET", "POST"])
def analytics():
    auth_redirect = check_auth()

    if auth_redirect:
        return auth_redirect

    if request.method == "POST":
        results_file = request.files.get("results_file")

        if not results_file or results_file.filename == "":
            return render_template("analytics.html", error="לא נבחר קובץ.")

        try:
            df = read_uploaded_dataframe(results_file)
            summary, tables, charts = build_analytics_payload(df)

            return render_template(
                "analytics.html",
                summary=summary,
                tables=tables,
                charts=charts,
                success="הקובץ נותח בהצלחה והנתונים עודכנו בפאנל המרצים."
            )

        except Exception as e:
            print("ANALYTICS ERROR:", e)
            return render_template(
                "analytics.html",
                error=f"שגיאה בניתוח הקובץ: {e}"
            )

    return render_template("analytics.html")


@app.route("/placement-system")
def placement_system():
    auth_redirect = check_auth()

    if auth_redirect:
        return auth_redirect

    return redirect("https://www.studentsplacement.org/")


@app.route("/students-form")
def students_form():
    return redirect("https://www.studentssurvey.org")


@app.route("/mentors-form")
def mentors_form():
    return redirect("https://mentormappingsurvey.org")


if __name__ == "__main__":
    app.run(debug=True)
