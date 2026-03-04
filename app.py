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

app = Flask(__name__)
app.secret_key = "bizpulse_secret_key_123"

# Database
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:Keshab@localhost/bizpulse'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# =========================
# Models
# =========================
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), nullable=False, unique=True)
    email = db.Column(db.String(100), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    last_login = db.Column(db.DateTime, nullable=True)
    projects = db.relationship('Project', backref='owner', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    dataset_path = db.Column(db.String(255), nullable=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, server_default=db.func.now())

# =========================
# Routes
# =========================
@app.route("/")
def home():
    return redirect(url_for("auth"))

# -------------------------
# Auth
# -------------------------
@app.route("/auth", methods=["GET","POST"])
def auth():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "register":
            username = request.form["username"]
            email = request.form["email"]
            password = request.form["password"]
            if User.query.filter((User.username==username)|(User.email==email)).first():
                return render_template("auth.html", message="User already exists!", tab="register")
            user = User(username=username, email=email)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            return render_template("auth.html", message="User Registered Successfully! 🎉", tab="login")
        elif action == "login":
            username_or_email = request.form["username_or_email"]
            password = request.form["password"]
            user = User.query.filter((User.username==username_or_email)|(User.email==username_or_email)).first()
            if not user or not user.check_password(password):
                return render_template("auth.html", message="Invalid credentials!", tab="login")
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
    return render_template("dashboard.html", user=user, total_users=total_users, total_projects=total_projects)

# -------------------------
# Profile
# -------------------------
@app.route("/profile", methods=["GET","POST"])
def profile():
    if "user_id" not in session:
        return redirect(url_for("auth"))
    user = User.query.get(session["user_id"])
    message = ""
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = request.form.get("password")
        existing = User.query.filter(((User.username==username)|(User.email==email))&(User.id!=user.id)).first()
        if existing:
            message = "Username or email already taken!"
        else:
            user.username = username
            user.email = email
            if password:
                user.set_password(password)
            db.session.commit()
            message = "Profile updated successfully!"
    return render_template("profile.html", user=user, message=message)

# -------------------------
# Projects
# -------------------------
@app.route("/projects", methods=["GET","POST"])
def projects():
    if "user_id" not in session:
        return redirect(url_for("auth"))
    user = User.query.get(session["user_id"])
    message = ""
    if request.method == "POST":
        name = request.form.get("name")
        file = request.files.get("dataset")
        path = None
        if file and file.filename.endswith('.csv'):
            filename = f"{user.id}_{int(time.time())}_{secure_filename(file.filename)}"
            path = os.path.join(UPLOAD_FOLDER, filename)
            file.save(path)
        if name:
            proj = Project(name=name, dataset_path=path, owner_id=user.id)
            db.session.add(proj)
            db.session.commit()
            message = "Project added!"
    project_list = Project.query.filter_by(owner_id=user.id).all()
    return render_template("projects.html", projects=project_list, message=message)

@app.route("/projects/delete/<int:pid>")
def delete_project(pid):
    if "user_id" not in session:
        return redirect(url_for("auth"))
    proj = Project.query.get(pid)
    if proj and proj.owner_id==session["user_id"]:
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

    user = User.query.get(session["user_id"])
    projects = Project.query.filter_by(owner_id=user.id).all()
    report_html = ""

    for p in projects:
        report_html += f"<h3>{p.name}</h3>"
        if not p.dataset_path or not os.path.exists(p.dataset_path):
            report_html += "<p>No dataset uploaded</p>"
            continue
        try:
            df = pd.read_csv(p.dataset_path)
            numeric_cols = df.select_dtypes(include=['number']).columns
            categorical_cols = df.select_dtypes(include=['object']).columns

            # Numeric histograms
            for col in numeric_cols:
                plt.figure(figsize=(10,6))
                df[col].hist(bins=15, color='skyblue', edgecolor='black')
                plt.title(f'Histogram of {col}', fontsize=16)
                plt.xlabel(col, fontsize=14)
                plt.ylabel('Count', fontsize=14)
                plt.tight_layout()
                hist_file = f"hist_{p.id}_{col}.png"
                hist_path = os.path.join(UPLOAD_FOLDER, hist_file)
                plt.savefig(hist_path)
                plt.close()
                report_html += f"<img src='/uploads/{hist_file}' width='700'><br>"

            # Correlation heatmap
            if len(numeric_cols) > 1:
                plt.figure(figsize=(10,8))
                sns.heatmap(df[numeric_cols].corr(), annot=True, cmap='coolwarm', fmt=".2f", linewidths=.5)
                plt.title("Correlation Heatmap", fontsize=16)
                plt.tight_layout()
                corr_file = f"corr_{p.id}.png"
                corr_path = os.path.join(UPLOAD_FOLDER, corr_file)
                plt.savefig(corr_path)
                plt.close()
                report_html += f"<img src='/uploads/{corr_file}' width='700'><br>"

            # Categorical bar plots (first 3)
            for col in categorical_cols[:3]:
                plt.figure(figsize=(10,6))
                df[col].value_counts().plot(kind='bar', color='orange', edgecolor='black')
                plt.title(f'Value Counts of {col}', fontsize=16)
                plt.xlabel(col, fontsize=14)
                plt.ylabel('Count', fontsize=14)
                plt.xticks(rotation=45, ha='right')
                plt.tight_layout()
                cat_file = f"cat_{p.id}_{col}.png"
                cat_path = os.path.join(UPLOAD_FOLDER, cat_file)
                plt.savefig(cat_path)
                plt.close()
                report_html += f"<img src='/uploads/{cat_file}' width='700'><br>"
        except Exception as e:
            report_html += f"<p style='color:red'>Error reading dataset: {e}</p>"

    return f'''
    <html>
    <head>
        <title>Reports</title>
        <style>
            body {{ font-family: Arial, sans-serif; background:#eef2f7; padding:20px; }}
            img {{ margin:20px 0; border:1px solid #ccc; border-radius:5px; display:block; margin-left:auto; margin-right:auto; }}
            h3 {{ text-align:center; color:#007BFF; }}
            a {{ display:block; margin-top:20px; text-align:center; }}
        </style>
    </head>
    <body>
        <h2 style="text-align:center">Your Reports</h2>
        {report_html if report_html else "<p style='text-align:center'>No projects to report.</p>"}
        <a href="/dashboard">Back</a>
    </body>
    </html>
    '''

# -------------------------
# Serve static images
# -------------------------
@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_file(os.path.join(UPLOAD_FOLDER, filename))

# -------------------------
# Logout
# -------------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth"))

# =========================
# Run App
# =========================
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)