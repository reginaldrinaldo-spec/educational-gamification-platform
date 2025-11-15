from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required, get_jwt_identity,
)
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import os

db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()

def create_app():
    app = Flask(__name__)
    
    # ---------- CORE CONFIG ----------
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY", app.config["SECRET_KEY"])
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=12)
    
    # ---------- DATABASE CONFIG (PostgreSQL for Render) ----------
    # Render usually provides DATABASE_URL like:
    # postgres://USER:PASSWORD@HOST:PORT/DBNAME
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is required for PostgreSQL.")
    
    # SQLAlchemy prefers postgresql://
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    
    register_routes(app)
    
    return app

# ---------- SQLALCHEMY MODELS ----------

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
    metrics = db.Column(db.JSON, nullable=False)  # arbitrary gamification metrics
    
    user = db.relationship("User", back_populates="analytics")
    session = db.relationship("GameSession", back_populates="analytics")
    
    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "metrics": self.metrics,
        }

# ---------- ROUTES / ENDPOINTS ----------

def register_routes(app: Flask):
    # 1. User registration/login (JWT auth)
    # 2. Get user profile
    # 3. Browse available modules
    # 4. Start a game session
    # 5. Submit answers/progress
    # 6. Get session results
    # 7. View leaderboard
    # 8. Get analytics
    # 9. Health check
    
    # ----- AUTH -----
    
    @app.post("/auth/register")
    def register():
        data = request.get_json() or {}
        username = data.get("username", "").strip()
        email = data.get("email", "").strip().lower()
        password = data.get("password")
        
        if not username or not email or not password:
            return jsonify({"error": "username, email and password are required"}), 400
        
        if User.query.filter((User.username == username) | (User.email == email)).first():
            return jsonify({"error": "username or email already taken"}), 409
        
        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
        )
        db.session.add(user)
        db.session.commit()
        
        access_token = create_access_token(identity=user.id)
        return jsonify({"access_token": access_token, "user": user.to_dict(), }), 201
    
    @app.post("/auth/login")
    def login():
        data = request.get_json() or {}
        identifier = data.get("username") or data.get("email")
        password = data.get("password")
        
        if not identifier or not password:
            return jsonify({"error": "username/email and password are required"}), 400
        
        user = User.query.filter(
            (User.username == identifier) | (User.email == identifier.lower())
        ).first()
        
        if not user or not check_password_hash(user.password_hash, password):
            return jsonify({"error": "invalid credentials"}), 401
        
        access_token = create_access_token(identity=user.id)
        return jsonify({"access_token": access_token, "user": user.to_dict(), }), 200
    
    # ----- USER PROFILE -----
    
    @app.get("/users/me")
    @jwt_required()
    def get_me():
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "user not found"}), 404
        
        return jsonify(user.to_dict()), 200
    
    # ----- MODULES (browse available modules) -----
    
    @app.get("/modules")
    @jwt_required(optional=True)  # can be public if you want
    def list_modules():
        difficulty = request.args.get("difficulty")
        subject = request.args.get("subject")
        
        query = Module.query
        if difficulty:
            query = query.filter_by(difficulty=difficulty)
        if subject:
            query = query.filter_by(subject=subject)
        
        modules = query.order_by(Module.id.asc()).all()
        return jsonify([m.to_dict() for m in modules]), 200
    
    # ----- GAME SESSIONS -----
    
    @app.post("/sessions")
    @jwt_required()
    def start_session():
        """Start a game session for a given module."""
        user_id = get_jwt_identity()
        data = request.get_json() or {}
        module_id = data.get("module_id")
        
        if not module_id:
            return jsonify({"error": "module_id is required"}), 400
        
        module = Module.query.get(module_id)
        if not module:
            return jsonify({"error": "module not found"}), 404
        
        session = GameSession(
            user_id=user_id,
            module_id=module_id,
            score=0,
        )
        db.session.add(session)
        db.session.commit()
        
        return jsonify({"message": "session started", "session": session.to_dict(), }), 201
    
    @app.post("/sessions/<int:session_id>/progress")
    @jwt_required()
    def submit_progress(session_id):
        """
        Submit answers/progress.
        Body example:
        {
            "score_delta": 10,
            "completed": true,
            "metrics": {
                "questions_answered": 10,
                "correct": 8,
                "time_spent_seconds": 120
            }
        }
        """
        user_id = get_jwt_identity()
        session = GameSession.query.get(session_id)
        
        if not session or session.user_id != user_id:
            return jsonify({"error": "session not found"}), 404
        
        data = request.get_json() or {}
        score_delta = data.get("score_delta", 0)
        completed = data.get("completed", False)
        metrics = data.get("metrics", {})
        
        if not isinstance(score_delta, int):
            return jsonify({"error": "score_delta must be integer"}), 400
        
        session.score += score_delta
        if completed and session.completed_at is None:
            session.completed_at = datetime.utcnow()
        
        analytics_entry = Analytics(
            user_id=user_id,
            session_id=session.id,
            metrics=metrics,
        )
        db.session.add(analytics_entry)
        db.session.add(session)
        db.session.commit()
        
        return jsonify({
            "message": "progress updated",
            "session": session.to_dict(),
            "analytics": analytics_entry.to_dict(),
        }), 200
    
    @app.get("/sessions/<int:session_id>/results")
    @jwt_required()
    def get_session_results(session_id):
        """Get session results (score + analytics)."""
        user_id = get_jwt_identity()
        session = GameSession.query.get(session_id)
        
        if not session or session.user_id != user_id:
            return jsonify({"error": "session not found"}), 404
        
        module = session.module
        analytics_entries = Analytics.query.filter_by(session_id=session.id).all()
        
        return jsonify({
            "session": session.to_dict(),
            "module": module.to_dict() if module else None,
            "analytics": [a.to_dict() for a in analytics_entries],
        }), 200
    
    # ----- LEADERBOARD -----
    
    @app.get("/leaderboard")
    @jwt_required(optional=True)
    def leaderboard():
        """
        View leaderboard.
        Query params:
        - module_id (optional): filter by specific module
        - limit (optional): max entries, default 10
        """
        module_id = request.args.get("module_id", type=int)
        limit = request.args.get("limit", default=10, type=int)
        
        query = GameSession.query
        if module_id:
            query = query.filter_by(module_id=module_id)
        
        # Only completed sessions
        query = query.filter(GameSession.completed_at.isnot(None))
        
        sessions = (
            query.order_by(GameSession.score.desc(), GameSession.completed_at.asc())
            .limit(limit)
            .all()
        )
        
        data = []
        for s in sessions:
            user = s.user
            module = s.module
            data.append({
                "session_id": s.id,
                "user_id": s.user_id,
                "username": user.username if user else None,
                "module_id": s.module_id,
                "module_title": module.title if module else None,
                "score": s.score,
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
            })
        
        return jsonify(data), 200
    
    # ----- ANALYTICS -----
    
    @app.get("/analytics")
    @jwt_required()
    def get_analytics():
        """
        Get analytics entries for the current user.
        Optional: ?session_id=...
        """
        user_id = get_jwt_identity()
        session_id = request.args.get("session_id", type=int)
        
        query = Analytics.query.filter_by(user_id=user_id)
        if session_id:
            query = query.filter_by(session_id=session_id)
        
        entries = query.order_by(Analytics.id.desc()).all()
        return jsonify([e.to_dict() for e in entries]), 200
    
    # ----- HEALTH CHECK -----
    
    @app.get("/health")
    def health():
        try:
            # Simple DB connectivity check
            db.session.execute(db.select(1))
            db_ok = True
        except Exception:
            db_ok = False
        
        return jsonify({
            "status": "ok" if db_ok else "degraded",
            "database": "up" if db_ok else "down",
        }), 200 if db_ok else 503

# For Render / gunicorn: expose app
app = create_app()

if __name__ == "__main__":
    # Local dev
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
