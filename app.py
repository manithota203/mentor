
from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "mentor_project_secret_key"


# Database connection
def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn


# Create database tables
def create_tables():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL,
            skills TEXT,
            bio TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mentee_id INTEGER,
            mentor_id INTEGER,
            status TEXT DEFAULT 'Pending'
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mentee_id INTEGER,
            task TEXT NOT NULL,
            completed INTEGER DEFAULT 0
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


# Home page
@app.route("/")
def home():
    return render_template("index.html")


# Registration
@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form.get("name") or request.form.get("full_name")
        email = request.form.get("email")
        password = request.form.get("password")
        role = request.form.get("role", "mentee").lower()
        skills = request.form.get("skills", "")
        bio = request.form.get("bio", "")

        if not all([name, email, password]):
            flash("Please fill all required fields.")
            return redirect(url_for("register"))

        if role not in ["mentor", "mentee"]:
            flash("Please select a valid role.")
            return redirect(url_for("register"))

        conn = get_db()

        try:
            conn.execute("""
                INSERT INTO users (name, email, password, role, skills, bio)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                name,
                email,
                generate_password_hash(password),
                role,
                skills,
                bio
            ))

            conn.commit()
            flash("Registration successful! Please login.")

        except sqlite3.IntegrityError:
            flash("Email already registered.")

        finally:
            conn.close()

        return redirect(url_for("login"))

    return render_template("register.html")


# Login
@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email")
        password = request.form.get("password")

        conn = get_db()

        user = conn.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        ).fetchone()

        conn.close()

        if user and check_password_hash(user["password"], password):

            session["user_id"] = user["id"]
            session["name"] = user["name"]
            session["role"] = user["role"]

            if user["role"] == "mentor":
                return redirect(url_for("mentor"))

            return redirect(url_for("student"))

        flash("Invalid email or password.")

    return render_template("login.html")


# Student dashboard
@app.route("/student")
def student():

    if "user_id" not in session or session["role"] != "mentee":
        return redirect(url_for("login"))

    return render_template("student.html")


# Mentor dashboard
@app.route("/mentor")
def mentor():

    if "user_id" not in session or session["role"] != "mentor":
        return redirect(url_for("login"))

    return render_template("mentor.html")


# Mentor Profile
@app.route("/mentor-profile", methods=["GET", "POST"])
def mentor_profile():

    if "user_id" not in session or session["role"] != "mentor":
        return redirect(url_for("login"))

    conn = get_db()

    if request.method == "POST":

        skills = request.form.get("skills", "").strip()
        bio = request.form.get("bio", "").strip()

        conn.execute("""
            UPDATE users
            SET skills = ?, bio = ?
            WHERE id = ? AND role = 'mentor'
        """, (skills, bio, session["user_id"]))

        conn.commit()
        flash("Profile updated successfully!")

    mentor = conn.execute("""
        SELECT * FROM users WHERE id = ?
    """, (session["user_id"],)).fetchone()

    conn.close()

    return render_template("mentor-profile.html", mentor=mentor)


# Find mentors
@app.route("/find-mentor")
def find_mentor():

    if "user_id" not in session or session["role"] != "mentee":
        return redirect(url_for("login"))

    conn = get_db()

    mentors = conn.execute("""
        SELECT * FROM users WHERE role = 'mentor'
    """).fetchall()

    conn.close()

    return render_template("find-mentor.html", mentors=mentors)


# Send mentor request
@app.route("/send-request", methods=["POST"])
def send_request():

    if "user_id" not in session or session["role"] != "mentee":
        return redirect(url_for("login"))

    mentor_id = request.form.get("mentor_id")

    conn = get_db()

    mentor = conn.execute(
        "SELECT id FROM users WHERE id = ? AND role = 'mentor'",
        (mentor_id,)
    ).fetchone()

    if not mentor:
        flash("Mentor not found.")

    else:

        existing = conn.execute("""
            SELECT id FROM requests
            WHERE mentee_id = ? AND mentor_id = ?
        """, (session["user_id"], mentor_id)).fetchone()

        if existing:
            flash("You have already requested this mentor.")

        else:
            conn.execute("""
                INSERT INTO requests (mentee_id, mentor_id)
                VALUES (?, ?)
            """, (session["user_id"], mentor_id))

            conn.commit()
            flash("Mentor request sent successfully!")

    conn.close()

    return redirect(url_for("find_mentor"))


# View requests
@app.route("/requests")
def view_requests():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    if session["role"] == "mentor":

        requests_list = conn.execute("""
            SELECT requests.id, users.name, users.email,
                   requests.status
            FROM requests
            JOIN users ON requests.mentee_id = users.id
            WHERE requests.mentor_id = ?
        """, (session["user_id"],)).fetchall()

    else:

        requests_list = conn.execute("""
            SELECT requests.id, users.name, requests.status
            FROM requests
            JOIN users ON requests.mentor_id = users.id
            WHERE requests.mentee_id = ?
        """, (session["user_id"],)).fetchall()

    conn.close()

    return render_template(
        "requests.html",
        requests=requests_list
    )


# Accept or reject request
@app.route("/update-request/<int:request_id>/<action>")
def update_request(request_id, action):

    if "user_id" not in session or session["role"] != "mentor":
        return redirect(url_for("login"))

    if action not in ["Accepted", "Rejected"]:
        return redirect(url_for("view_requests"))

    conn = get_db()

    conn.execute("""
        UPDATE requests
        SET status = ?
        WHERE id = ? AND mentor_id = ?
    """, (action, request_id, session["user_id"]))

    conn.commit()
    conn.close()

    flash("Request " + action.lower() + " successfully!")

    return redirect(url_for("view_requests"))


# Learning progress
@app.route("/progress", methods=["GET", "POST"])
def progress_page():

    if "user_id" not in session or session["role"] != "mentee":
        return redirect(url_for("login"))

    conn = get_db()

    if request.method == "POST":

        task = request.form.get("task", "").strip()

        if task:
            conn.execute("""
                INSERT INTO progress (mentee_id, task)
                VALUES (?, ?)
            """, (session["user_id"], task))

            conn.commit()

    progress_items = conn.execute("""
        SELECT * FROM progress WHERE mentee_id = ?
    """, (session["user_id"],)).fetchall()

    conn.close()

    return render_template(
        "progress.html",
        progress_items=progress_items
    )


# Mark task completed
@app.route("/complete-task/<int:task_id>")
def complete_task(task_id):

    if "user_id" not in session or session["role"] != "mentee":
        return redirect(url_for("login"))

    conn = get_db()

    conn.execute("""
        UPDATE progress
        SET completed = 1
        WHERE id = ? AND mentee_id = ?
    """, (task_id, session["user_id"]))

    conn.commit()
    conn.close()

    return redirect(url_for("progress_page"))


# Student feedback submission
@app.route("/feedback", methods=["GET", "POST"])
def feedback_page():

    if "user_id" not in session or session.get("role") != "mentee":
        return redirect(url_for("login"))

    if request.method == "POST":

        message = request.form.get("message", "").strip()

        if message:

            conn = get_db()

            conn.execute("""
                INSERT INTO feedback (student_id, message)
                VALUES (?, ?)
            """, (session["user_id"], message))

            conn.commit()
            conn.close()

            flash("Feedback submitted successfully!")
            return redirect(url_for("feedback_page"))

        flash("Please enter your feedback.")

    return render_template("feedback.html")


# Mentor views student feedback
@app.route("/view-feedback")
def view_feedback():

    if "user_id" not in session or session.get("role") != "mentor":
        return redirect(url_for("login"))

    conn = get_db()

    feedback_list = conn.execute("""
        SELECT feedback.message,
               feedback.created_at,
               users.name
        FROM feedback
        JOIN users ON feedback.student_id = users.id
        WHERE users.role = 'mentee'
        ORDER BY feedback.created_at DESC
    """).fetchall()

    conn.close()

    return render_template(
        "view-feedback.html",
        feedback_list=feedback_list
    )


# Logout
@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("home"))


# Run application
if __name__ == "__main__":

    create_tables()

    app.run(debug=True)
