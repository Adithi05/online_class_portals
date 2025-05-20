import os
from flask import Flask, render_template, redirect, url_for, request, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# ─── CONFIG ─────────────────────────────────────────────
app = Flask(__name__, template_folder='template')  # usually plural 'templates'
app.secret_key = os.environ.get("SECRET_KEY", "random_secret")

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Use absolute path for UPLOAD_FOLDER
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024  # 200MB
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')

ALLOWED_EXT = {'mp4', 'mov', 'avi', 'mkv'}

# ─── INIT ───────────────────────────────────────────────
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ─── MODELS ─────────────────────────────────────────────
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(10), nullable=False)  # 'student' or 'tutor'
    courses = db.relationship('Course', backref='uploader', lazy=True)

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)
    video_filename = db.Column(db.String(200), nullable=False)
    uploader_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

# ─── LOGIN HANDLER ──────────────────────────────────────
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ─── HELPERS ────────────────────────────────────────────
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXT

# ─── ROUTES ─────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html', user=current_user)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        uname = request.form['username']
        pw = request.form['password']
        role = request.form['role']
        if User.query.filter_by(username=uname).first():
            flash('Username already exists.')
            return redirect(url_for('register'))

        user = User(username=uname, role=role)
        user.set_password(pw)
        db.session.add(user)
        db.session.commit()
        flash('Registration successful! Please log in.')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        uname = request.form['username']
        pw = request.form['password']
        user = User.query.filter_by(username=uname).first()
        if user and user.check_password(pw):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid username or password.')
        return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.')
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'tutor':
        courses = Course.query.filter_by(uploader_id=current_user.id).all()
    else:
        courses = Course.query.all()
    return render_template('dashboard.html', courses=courses)

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload_course():
    if current_user.role != 'tutor':
        flash("Only tutors can upload courses.")
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        title = request.form['title']
        desc = request.form['description']
        video = request.files.get('video')

        if not video or not allowed_file(video.filename):
            flash("Please upload a valid video file.")
            return redirect(request.url)

        filename = secure_filename(video.filename)
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        video.save(save_path)

        course = Course(
            title=title,
            description=desc,
            video_filename=filename,
            uploader_id=current_user.id
        )
        db.session.add(course)
        db.session.commit()
        flash("Course uploaded successfully!")
        return redirect(url_for('dashboard'))

    return render_template('upload.html')

@app.route('/course/<int:course_id>')
@login_required
def course_detail(course_id):
    course = Course.query.get_or_404(course_id)
    return render_template('course_detail.html', course=course)

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    # Serve uploaded video file
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/delete_course/<int:course_id>', methods=['POST'])
@login_required
def delete_course(course_id):
    course = Course.query.get_or_404(course_id)

    # Only allow the tutor who uploaded the course to delete it
    if course.uploader_id != current_user.id:
        flash("You are not authorized to delete this course.")
        return redirect(url_for('dashboard'))

    # Delete video file from static/uploads if it exists
    video_path = os.path.join(app.config['UPLOAD_FOLDER'], course.video_filename)
    if os.path.exists(video_path):
        os.remove(video_path)

    # Delete course record from database
    db.session.delete(course)
    db.session.commit()
    flash("Course deleted successfully!")
    return redirect(url_for('dashboard'))

# ─── INITIALIZATION ─────────────────────────────────────
initialized = False

@app.before_request
def initialize_once():
    global initialized
    if not initialized:
        with app.app_context():
            db.create_all()
            if not User.query.filter_by(username='admin').first():
                admin = User(username='admin', role='admin')
                admin.set_password('admin123')
                db.session.add(admin)
                db.session.commit()
                print("Default admin user created.")
        initialized = True

if __name__ == '__main__':
    app.run(debug=True)
