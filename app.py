from flask import Flask, request, session, redirect, url_for, send_file, render_template
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import os
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
import time

# =========================
# Setup Upload Folder
# =========================
UPLOAD_FOLDER = os.path.join(os.getcwd(), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# =========================
# Flask App Setup
# =========================
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "bizpulse_secret_key_123")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# =========================
# Database
# =========================
db_uri = os.environ.get("DATABASE_URL")

if not db_uri:
    db_uri = "sqlite:///bizpulse.db"

app.config["SQLALCHEMY_DATABASE_URI"] = db_uri
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# =========================
# Models
# =========================
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    last_login = db.Column(db.DateTime)

    projects = db.relationship("Project", backref="owner", lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    dataset_path = db.Column(db.String(255))
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    created_at = db.Column(db.DateTime, server_default=db.func.now())


# =========================
# Routes
# =========================
@app.route("/")
def home():
    return redirect(url_for("auth"))

# -------------------------
# Authentication
# -------------------------
@app.route("/auth", methods=["GET", "POST"])
def auth():

    if request.method == "POST":

        action = request.form.get("action")

        # REGISTER
        if action == "register":

            username = request.form["username"]
            email = request.form["email"]
            password = request.form["password"]

            existing = User.query.filter(
                (User.username == username) |
                (User.email == email)
            ).first()

            if existing:
                return render_template("auth.html",
                                       message="User already exists!",
                                       tab="register")

            user = User(username=username, email=email)
            user.set_password(password)

            db.session.add(user)
            db.session.commit()

            return render_template("auth.html",
                                   message="Registered successfully!",
                                   tab="login")

        # LOGIN
        if action == "login":

            username_or_email = request.form["username_or_email"]
            password = request.form["password"]

            user = User.query.filter(
                (User.username == username_or_email) |
                (User.email == username_or_email)
            ).first()

            if not user or not user.check_password(password):
                return render_template("auth.html",
                                       message="Invalid credentials!",
                                       tab="login")

            session["user_id"] = user.id
            session["username"] = user.username

            user.last_login = datetime.now()
            db.session.commit()

            return redirect(url_for("dashboard"))

    return render_template("auth.html", message=None, tab="register")


# -------------------------
# Dashboard
# -------------------------
@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect(url_for("auth"))

    user = db.session.get(User, session["user_id"])

    total_users = User.query.count()
    total_projects = Project.query.filter_by(owner_id=user.id).count()

    return render_template(
        "dashboard.html",
        user=user,
        total_users=total_users,
        total_projects=total_projects
    )


# -------------------------
# Profile
# -------------------------
@app.route("/profile", methods=["GET", "POST"])
def profile():

    if "user_id" not in session:
        return redirect(url_for("auth"))

    user = User.query.get(session["user_id"])
    message = ""

    if request.method == "POST":

        username = request.form["username"]
        email = request.form["email"]
        password = request.form.get("password")

        existing = User.query.filter(
            ((User.username == username) |
             (User.email == email)) &
            (User.id != user.id)
        ).first()

        if existing:
            message = "Username or email already taken"

        else:

            user.username = username
            user.email = email

            if password:
                user.set_password(password)

            db.session.commit()
            message = "Profile updated"

    return render_template("profile.html",
                           user=user,
                           message=message)


# -------------------------
# Projects
# -------------------------
@app.route("/projects", methods=["GET", "POST"])
def projects():

    if "user_id" not in session:
        return redirect(url_for("auth"))

    user = User.query.get(session["user_id"])
    message = ""

    if request.method == "POST":

        name = request.form.get("name")
        file = request.files.get("dataset")

        path = None

        if file and file.filename.endswith(".csv"):

            filename = f"{user.id}_{int(time.time())}_{secure_filename(file.filename)}"

            path = os.path.join(app.config["UPLOAD_FOLDER"], filename)

            file.save(path)

        if name:

            proj = Project(
                name=name,
                dataset_path=path,
                owner_id=user.id
            )

            db.session.add(proj)
            db.session.commit()

            message = "Project added"

    project_list = Project.query.filter_by(owner_id=user.id).all()

    return render_template(
        "projects.html",
        projects=project_list,
        message=message
    )


@app.route("/projects/delete/<int:pid>")
def delete_project(pid):

    if "user_id" not in session:
        return redirect(url_for("auth"))

    proj = Project.query.get(pid)

    if proj and proj.owner_id == session["user_id"]:

        if proj.dataset_path and os.path.exists(proj.dataset_path):
            os.remove(proj.dataset_path)

        db.session.delete(proj)
        db.session.commit()

    return redirect(url_for("projects"))


# -------------------------
# Reports
# -------------------------
@app.route("/reports")
def reports():

    if "user_id" not in session:
        return redirect(url_for("auth"))

    projects = Project.query.filter_by(owner_id=session["user_id"]).all()

    return render_template(
        "reports.html",
        projects=projects,
        upload_folder="uploads"
    )


# -------------------------
# Logout
# -------------------------
@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("auth"))


# -------------------------
# Serve Uploads
# -------------------------
@app.route("/uploads/<path:filename>")
def uploaded_file(filename):

    return send_file(os.path.join(app.config["UPLOAD_FOLDER"], filename))


# =========================
# Run App
# =========================
if __name__ == "__main__":

    with app.app_context():
        db.create_all()