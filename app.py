from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    jwt_required,
    get_jwt_identity,
)
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from sqlalchemy import inspect
import os
from gamification_routes import gamification_bp

db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()


def create_app():
    app = Flask(__name__)

    # ---------- CORE CONFIG ----------
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY", app.config["SECRET_KEY"])
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=12)

    # ---------- DATABASE CONFIG ----------
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is required for PostgreSQL.")

    # Render gives postgres://; SQLAlchemy needs postgresql://
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
        
    # Enable CORS for frontend communication
    CORS(app, resources={r"/*": {"origins": ["https://meme-educational-frontend.vercel.app"]}})

    # Auto-create tables when DB is empty
    run_initial_setup(app)

    # Register all endpoints
    register_routes(app)

    return app


# ---------- MODELS ----------

class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    sessions = db.relationship("GameSession", back_populates="user", cascade="all, delete-orphan")
    analytics = db.relationship("Analytics", back_populates="user", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "created_at": self.created_at.isoformat(),
        }


class Module(db.Model):
    __tablename__ = "modules"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    difficulty = db.Column(db.String(50), nullable=True)
    subject = db.Column(db.String(100), nullable=True)

    sessions = db.relationship("GameSession", back_populates="module", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "difficulty": self.difficulty,
            "subject": self.subject,
        }


class GameSession(db.Model):
    __tablename__ = "game_sessions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    module_id = db.Column(db.Integer, db.ForeignKey("modules.id"), nullable=False)
    score = db.Column(db.Integer, default=0, nullable=False)
    completed_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User", back_populates="sessions")
    module = db.relationship("Module", back_populates="sessions")
    analytics = db.relationship("Analytics", back_populates="session", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "module_id": self.module_id,
            "score": self.score,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class Analytics(db.Model):
    __tablename__ = "analytics"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey("game_sessions.id"), nullable=False)
    metrics = db.Column(db.JSON, nullable=False)

    user = db.relationship("User", back_populates="analytics")
    session = db.relationship("GameSession", back_populates="analytics")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "metrics": self.metrics,
        }


class Quiz(db.Model):
    __tablename__ = "quizzes"
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    questions = db.relationship("Question", back_populates="quiz", cascade="all, delete-orphan")
    
    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "created_at": self.created_at.isoformat(),
            "question_count": len(self.questions),
        }


class Question(db.Model):
    __tablename__ = "questions"
    
    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey("quizzes.id"), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    options = db.Column(db.JSON, nullable=False)  # List of 4 options
    correct_answer = db.Column(db.String(10), nullable=False)  # "A", "B", "C", or "D"
    explanation = db.Column(db.Text, nullable=True)
    difficulty = db.Column(db.String(50), nullable=True)  # "easy", "medium", "hard"
    category = db.Column(db.String(100), nullable=True)  # "wiskunde_wetenschap", etc.
    
    quiz = db.relationship("Quiz", back_populates="questions")
    
    def to_dict(self):
        return {
            "id": self.id,
            "quiz_id": self.quiz_id,
            "question": self.question_text,
            "options": self.options,
            "correct_answer": self.correct_answer,
            "explanation": self.explanation,
            "difficulty": self.difficulty,
            "category": self.category,
        }

# ---------- AUTO SETUP ----------

def run_initial_setup(app: Flask):
    """
    If DB has no tables, auto-create them.
    This makes the app fully deployable on Render Free Tier (no shell).
    """
    try:
        with app.app_context():
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            if not tables:
                app.logger.info("No tables found — running db.create_all()...")
                db.create_all()
                app.logger.info("Tables created successfully.")
            else:
                app.logger.info(f"DB already contains tables: {tables}")
    except Exception as e:
        app.logger.error(f"Startup DB setup error: {e}")


# ---------- SEED HELPERS ----------

def get_or_create_user(username, email, password_plain):
    user = User.query.filter_by(username=username).first()
    if user:
        return user
    user = User(
        username=username,
        email=email.lower(),
        password_hash=generate_password_hash(password_plain),
        created_at=datetime.utcnow(),
    )
    db.session.add(user)
    db.session.commit()
    return user


def get_or_create_module(title, description, difficulty, subject):
    module = Module.query.filter_by(title=title).first()
    if module:
        return module
    module = Module(
        title=title,
        description=description,
        difficulty=difficulty,
        subject=subject,
    )
    db.session.add(module)
    db.session.commit()
    return module


def get_or_create_session(user, module, score, completed=True, completed_offset_minutes=0):
    session = (
        GameSession.query
        .filter_by(user_id=user.id, module_id=module.id)
        .first()
    )
    if session:
        return session

    completed_at = None
    if completed:
        completed_at = datetime.utcnow() - timedelta(minutes=completed_offset_minutes)

    session = GameSession(
        user_id=user.id,
        module_id=module.id,
        score=score,
        completed_at=completed_at,
    )
    db.session.add(session)
    db.session.commit()
    return session


def create_analytics_entry(user, session, metrics):
    existing = Analytics.query.filter_by(
        user_id=user.id,
        session_id=session.id
    ).first()
    if existing:
        return existing

    entry = Analytics(
        user_id=user.id,
        session_id=session.id,
        metrics=metrics
    )
    db.session.add(entry)
    db.session.commit()
    return entry


def run_seed_data():
    """Seed: modules, users, sessions, analytics."""
    intro_module = get_or_create_module(
        "Intro to Memes",
        "Basics of meme culture",
        "easy",
        "media_literacy",
    )
    advanced_module = get_or_create_module(
        "Advanced Memes",
        "Evolving meme complexity",
        "medium",
        "internet_culture",
    )
    theory_module = get_or_create_module(
        "Meme Theory",
        "Why memes work",
        "hard",
        "communication_theory",
    )

    testuser1 = get_or_create_user(
        "testuser1", "test1@example.com", "Password123!"
    )
    testuser2 = get_or_create_user(
        "testuser2", "test2@example.com", "Password123!"
    )

    session1 = get_or_create_session(testuser1, intro_module, 85, True, 30)
    session2 = get_or_create_session(testuser2, advanced_module, 92, True, 60)

    create_analytics_entry(testuser1, session1, {
        "correct": 8, "incorrect": 2, "time_spent": 180
    })
    create_analytics_entry(testuser2, session2, {
        "correct": 14, "incorrect": 1, "time_spent": 240
    })


# ---------- ROUTES ----------

def register_routes(app: Flask):
    # Register gamification blueprint
    app.register_blueprint(gamification_bp)

    # ----- AUTH -----
    @app.post("/auth/register")
    def register():
        data = request.get_json() or {}
        username = data.get("username", "").strip()
        email = data.get("email", "").strip().lower()
        password = data.get("password")
        
        if not username or not email or not password:
            return jsonify({"error": "username, email, password required"}), 400
        if User.query.filter((User.username == username) | (User.email == email)).first():
            return jsonify({"error": "username or email already in use"}), 409

        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
        )
        db.session.add(user)
        db.session.commit()
        
        token = create_access_token(identity=user.id)
        return jsonify({"access_token": token, "user": user.to_dict()}), 201

    @app.post("/auth/login")
    def login():
        data = request.get_json() or {}
        identifier = data.get("username") or data.get("email")
        password = data.get("password")
        
        if not identifier or not password:
            return jsonify({"error": "missing credentials"}), 400
        
        user = User.query.filter(
            (User.username == identifier) | (User.email == identifier.lower())
        ).first()
        
        if not user or not check_password_hash(user.password_hash, password):
            return jsonify({"error": "invalid credentials"}), 401
        
        token = create_access_token(identity=user.id)
        return jsonify({"access_token": token, "user": user.to_dict()}), 200
    # ----- USER PROFILE -----
    @app.get("/users/me")
    @jwt_required()
    def get_me():
        user = User.query.get(get_jwt_identity())
        if not user:
            return jsonify({"error": "user not found"}), 404
        return jsonify(user.to_dict())

    # ----- MODULES -----
    @app.get("/modules")
    @jwt_required(optional=True)
    def list_modules():
        difficulty = request.args.get("difficulty")
        subject = request.args.get("subject")

        query = Module.query
        if difficulty:
            query = query.filter_by(difficulty=difficulty)
        if subject:
            query = query.filter_by(subject=subject)

        modules = query.order_by(Module.id.asc()).all()
        return jsonify([m.to_dict() for m in modules])

    # ----- START SESSION -----
    @app.post("/sessions")
    @jwt_required()
    def start_session():
        user_id = get_jwt_identity()
        module_id = request.json.get("module_id")

        if not module_id:
            return jsonify({"error": "module_id required"}), 400

        module = Module.query.get(module_id)
        if not module:
            return jsonify({"error": "module not found"}), 404

        session = GameSession(user_id=user_id, module_id=module_id, score=0)
        db.session.add(session)
        db.session.commit()

        return jsonify({"session": session.to_dict()}), 201

    # ----- SUBMIT PROGRESS -----
    @app.post("/sessions/<int:session_id>/progress")
    @jwt_required()
    def submit_progress(session_id):
        user_id = get_jwt_identity()
        session = GameSession.query.get(session_id)

        if not session or session.user_id != user_id:
            return jsonify({"error": "session not found"}), 404

        data = request.get_json() or {}
        session.score += int(data.get("score_delta", 0))

        if data.get("completed") and not session.completed_at:
            session.completed_at = datetime.utcnow()

        analytics_entry = Analytics(
            user_id=user_id,
            session_id=session.id,
            metrics=data.get("metrics", {}),
        )
        db.session.add(analytics_entry)
        db.session.commit()

        return jsonify({
            "session": session.to_dict(),
            "analytics": analytics_entry.to_dict()
        })

    # ----- SESSION RESULTS -----
    @app.get("/sessions/<int:session_id>/results")
    @jwt_required()
    def session_results(session_id):
        user_id = get_jwt_identity()
        session = GameSession.query.get(session_id)

        if not session or session.user_id != user_id:
            return jsonify({"error": "session not found"}), 404

        analytics_entries = Analytics.query.filter_by(session_id=session.id).all()

        return jsonify({
            "session": session.to_dict(),
            "analytics": [a.to_dict() for a in analytics_entries]
        })

    # ----- LEADERBOARD -----
    @app.get("/leaderboard")
    @jwt_required(optional=True)
    def leaderboard():
        module_id = request.args.get("module_id", type=int)
        limit = request.args.get("limit", type=int, default=10)

        q = GameSession.query.filter(GameSession.completed_at.isnot(None))
        if module_id:
            q = q.filter_by(module_id=module_id)

        sessions = q.order_by(GameSession.score.desc()).limit(limit).all()

        return jsonify([
            {
                "session_id": s.id,
                "user_id": s.user_id,
                "username": s.user.username,
                "module_id": s.module_id,
                "module_title": s.module.title,
                "score": s.score,
                "completed_at": s.completed_at.isoformat(),
            }
            for s in sessions
        ])

    # ----- ANALYTICS -----
    @app.get("/analytics")
    @jwt_required()
    def analytics_view():
        user_id = get_jwt_identity()
        session_id = request.args.get("session_id", type=int)

        q = Analytics.query.filter_by(user_id=user_id)
        if session_id:
            q = q.filter_by(session_id=session_id)

        return jsonify([a.to_dict() for a in q.all()])

    # ----- HEALTH CHECK -----
    @app.get("/health")
    def health():
        try:
            db.session.execute(db.select(1))
            return jsonify({"status": "ok", "database": "up"}), 200
        except Exception:
            return jsonify({"status": "degraded", "database": "down"}), 503

    # ----- ADMIN SEED ENDPOINT -----
    @app.post("/admin/seed-database")
    def seed_database():
        """
        Protected seeding endpoint.
        Requires:
            Header: X-Admin-Seed-Token: <token>
            Env var: ADMIN_SEED_TOKEN
        Only runs ONCE.
        """
        admin_token = os.environ.get("ADMIN_SEED_TOKEN")
        provided = request.headers.get("X-Admin-Seed-Token")

        if not admin_token:
            return jsonify({"error": "ADMIN_SEED_TOKEN not set"}), 500
        if not provided or provided != admin_token:
            return jsonify({"error": "unauthorized"}), 401

        # Check if already seeded
        if Module.query.filter_by(title="Intro to Memes").first():
            return jsonify({"error": "seed already applied"}), 409

        try:
            run_seed_data()
            return jsonify({"message": "seed successful"}), 201
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": str(e)}), 500



    # ----- ADMIN SEED QUIZ ENDPOINT -----
    @app.post("/admin/seed-quiz")
    def seed_quiz():
        """
        Seed quiz questions from JSON payload.
        Requires:
            Header: X-Admin-Seed-Token: <token>
            Body: {"quiz_title": "...", "quiz_description": "...", "questions": [...]}
        """
        admin_token = os.environ.get("ADMIN_SEED_TOKEN")
        provided = request.headers.get("X-Admin-Seed-Token")

        if not admin_token:
            return jsonify({"error": "ADMIN_SEED_TOKEN not set"}), 500

        if not provided or provided != admin_token:
            return jsonify({"error": "unauthorized"}), 401

        data = request.get_json() or {}
        quiz_title = data.get("quiz_title", "Educational Quiz")
        quiz_description = data.get("quiz_description", "")
        questions_data = data.get("questions", [])

        if not questions_data:
            return jsonify({"error": "no questions provided"}), 400

        try:
            # Create quiz
            quiz = Quiz(
                title=quiz_title,
                description=quiz_description,
                created_at=datetime.utcnow()
            )
            db.session.add(quiz)
            db.session.flush()  # Get quiz ID

            # Add questions
            for q_data in questions_data:
                question = Question(
                    quiz_id=quiz.id,
                    question_text=q_data.get("question", ""),
                    options=q_data.get("options", []),
                    correct_answer=q_data.get("correct_answer", ""),
                    explanation=q_data.get("explanation", ""),
                    difficulty=q_data.get("difficulty", "medium"),
                    category=q_data.get("category", "")
                )
                db.session.add(question)

            db.session.commit()
            
            return jsonify({
                "message": "quiz seeded successfully",
                "quiz_id": quiz.id,
                "question_count": len(questions_data)
            }), 201

        except Exception as e:
            db.session.rollback()
            return jsonify({"error": str(e)}), 500

    # ----- GET QUIZZES -----
    @jwt_required(optional=True)
    def list_quizzes():
        quizzes = Quiz.query.order_by(Quiz.created_at.desc()).all()
        return jsonify([q.to_dict() for q in quizzes])

    @app.get("/quizzes/<int:quiz_id>")
    @jwt_required(optional=True)
    def get_quiz(quiz_id):
        quiz = Quiz.query.get(quiz_id)
        if not quiz:
            return jsonify({"error": "quiz not found"}), 404
        
        questions = [q.to_dict() for q in quiz.questions]
        result = quiz.to_dict()
        result["questions"] = questions
        return jsonify(result)

    @app.get("/quizzes/<int:quiz_id>/questions")
    @jwt_required(optional=True)
    def get_quiz_questions(quiz_id):
        quiz = Quiz.query.get(quiz_id)
        if not quiz:
            return jsonify({"error": "quiz not found"}), 404
        return jsonify([q.to_dict() for q in quiz.questions])
# ---------- APP INSTANCE ----------

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
