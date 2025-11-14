from flask import Flask, jsonify, request
from flask_cors import CORS
import os
import jwt
from datetime import datetime, timedelta
from functools import wraps
from sqlalchemy import create_engine, Column, String, Integer, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()

# ==================== DATABASE CONFIGURATION ====================
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith('postgresql://'):
    DATABASE_URL = DATABASE_URL.replace('postgresql://', 'postgresql+psycopg2://')

engine = create_engine(
    DATABASE_URL or 'sqlite:///gamification.db',
    connect_args={'check_same_thread': False} if not DATABASE_URL else {},
    poolclass=NullPool if DATABASE_URL else None
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ==================== DATABASE MODELS ====================
class User(Base):
    __tablename__ = 'users'
    id = Column(String, primary_key=True, default=lambda: str(__import__('uuid').uuid4()))
    email = Column(String, unique=True, nullable=False, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    full_name = Column(String)
    role = Column(String, default='student')  # 'student', 'teacher', 'admin'
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    total_points = Column(Integer, default=0)

class GameSession(Base):
    __tablename__ = 'game_sessions'
    id = Column(String, primary_key=True, default=lambda: str(__import__('uuid').uuid4()))
    user_id = Column(String, nullable=False, index=True)
    module_id = Column(String, nullable=False)
    status = Column(String, default='active')  # 'active', 'completed', 'paused'
    score = Column(Integer, default=0)
    points_earned = Column(Integer, default=0)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
Base.metadata.create_all(bind=engine)
print("✅ Database models created successfully!")

# ==================== FLASK APP INITIALIZATION ====================
app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'edu-gamification-2025')
app.config['JWT_EXPIRATION_HOURS'] = 24

# ==================== HELPER FUNCTIONS ====================
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_jwt_token(user_id, email, role, expires_in_hours=24):
    """Create JWT token for authenticated user"""
    payload = {
        'user_id': user_id,
        'email': email,
        'role': role,
        'exp': datetime.utcnow() + timedelta(hours=expires_in_hours),
        'iat': datetime.utcnow()
    }
    token = jwt.encode(payload, app.config['SECRET_KEY'], algorithm='HS256')
    return token

def verify_jwt_token(token):
    """Verify and decode JWT token"""
    try:
        payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        return {'error': 'Token expired'}
    except jwt.InvalidTokenError:
        return {'error': 'Invalid token'}

def token_required(f):
    """Decorator to require JWT token in Authorization header"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                token = auth_header.split(" ")[1]
            except IndexError:
                return jsonify({'error': 'Invalid authorization header'}), 401
        
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
        
        payload = verify_jwt_token(token)
        if 'error' in payload:
            return jsonify(payload), 401
        
        request.user = payload
        return f(*args, **kwargs)
    return decorated

# ==================== HEALTH CHECK ====================
@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "message": "API is running"}), 200

@app.route('/api/test', methods=['GET'])
def test():
    return jsonify({"message": "Educational Gamification Platform API"}), 200

# ==================== FASE 7: AUTHENTICATION ENDPOINTS ====================

@app.route('/api/auth/register', methods=['POST'])
def register():
    """Register a new user (Student or Teacher)"""
    try:
        data = request.get_json()
        
        if not data or not data.get('email') or not data.get('password') or not data.get('username'):
            return jsonify({'error': 'Missing required fields: email, password, username'}), 400
        
        db = SessionLocal()
        
        # Check if user already exists
        existing_user = db.query(User).filter(
            (User.email == data['email']) | (User.username == data['username'])
        ).first()
        
        if existing_user:
            db.close()
            return jsonify({'error': 'Email or username already exists'}), 409
        
        # Create new user
        new_user = User(
            email=data['email'],
            username=data['username'],
            full_name=data.get('full_name', ''),
            password_hash=generate_password_hash(data['password']),
            role=data.get('role', 'student')
        )
        
        db.add(new_user)
        db.commit()
        
        # Create JWT token
        token = create_jwt_token(new_user.id, new_user.email, new_user.role)
        
        db.close()
        
        return jsonify({
            'message': 'User registered successfully',
            'user': {
                'id': new_user.id,
                'email': new_user.email,
                'username': new_user.username,
                'full_name': new_user.full_name,
                'role': new_user.role
            },
            'token': token
        }), 201
        
    except Exception as e:
        return jsonify({'error': f'Registration failed: {str(e)}'}), 500

@app.route('/api/auth/login', methods=['POST'])
def login():
    """Login user with email/username and password"""
    try:
        data = request.get_json()
        
        if not data or not data.get('email') or not data.get('password'):
            return jsonify({'error': 'Missing email and password'}), 400
        
        db = SessionLocal()
        
        # Find user by email or username
        user = db.query(User).filter(
            (User.email == data['email']) | (User.username == data['email'])
        ).first()
        
        if not user or not check_password_hash(user.password_hash, data['password']):
            db.close()
            return jsonify({'error': 'Invalid email or password'}), 401
        
        if not user.is_active:
            db.close()
            return jsonify({'error': 'Account is inactive'}), 403
        
        # Create JWT token
        token = create_jwt_token(user.id, user.email, user.role)
        
        db.close()
        
        return jsonify({
            'message': 'Login successful',
            'user': {
                'id': user.id,
                'email': user.email,
                'username': user.username,
                'full_name': user.full_name,
                'role': user.role,
                'total_points': user.total_points
            },
            'token': token
        }), 200
        
    except Exception as e:
        return jsonify({'error': f'Login failed: {str(e)}'}), 500

@app.route('/api/auth/profile', methods=['GET'])
@token_required
def get_profile():
    """Get current user profile (requires JWT token)"""
    try:
        db = SessionLocal()
        user = db.query(User).filter(User.id == request.user['user_id']).first()
        
        if not user:
            db.close()
            return jsonify({'error': 'User not found'}), 404
        
        profile = {
            'id': user.id,
            'email': user.email,
            'username': user.username,
            'full_name': user.full_name,
            'role': user.role,
            'total_points': user.total_points,
            'created_at': user.created_at.isoformat(),
            'is_active': user.is_active
        }
        
        db.close()
        
        return jsonify(profile), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to get profile: {str(e)}'}), 500

@app.route('/api/auth/logout', methods=['POST'])
@token_required
def logout():
    """Logout user (client-side token deletion)"""
    return jsonify({'message': 'Logout successful'}), 200

# ==================== GAMIFICATION ENDPOINTS ====================

@app.route('/api/game/start', methods=['POST'])
@token_required
def start_game_session():
    """Start a new game session"""
    try:
        data = request.get_json()
        module_id = data.get('module_id', 'module-1')
        
        db = SessionLocal()
        
        session = GameSession(
            user_id=request.user['user_id'],
            module_id=module_id,
            status='active'
        )
        
        db.add(session)
        db.commit()
        
        db.close()
        
        return jsonify({
            'message': 'Game session started',
            'session_id': session.id,
            'module_id': session.module_id,
            'started_at': session.started_at.isoformat()
        }), 201
        
    except Exception as e:
        return jsonify({'error': f'Failed to start game: {str(e)}'}), 500

@app.route('/api/game/submit-score', methods=['POST'])
@token_required
def submit_game_score():
    """Submit score for a game session"""
    try:
        data = request.get_json()
        session_id = data.get('session_id')
        score = data.get('score', 0)
        points = data.get('points', 0)
        
        if not session_id:
            return jsonify({'error': 'session_id is required'}), 400
        
        db = SessionLocal()
        
        game_session = db.query(GameSession).filter(GameSession.id == session_id).first()
        if not game_session:
            db.close()
            return jsonify({'error': 'Session not found'}), 404
        
        # Update session
        game_session.score = score
        game_session.points_earned = points
        game_session.status = 'completed'
        game_session.completed_at = datetime.utcnow()
        
        # Update user points
        user = db.query(User).filter(User.id == request.user['user_id']).first()
        if user:
            user.total_points += points
            db.add(user)
        
        db.add(game_session)
        db.commit()
        
        db.close()
        
        return jsonify({
            'message': 'Score submitted successfully',
            'session_id': game_session.id,
            'score': game_session.score,
            'points_earned': game_session.points_earned,
            'total_user_points': user.total_points if user else points
        }), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to submit score: {str(e)}'}), 500

@app.route('/api/leaderboard', methods=['GET'])
def get_leaderboard():
    """Get top users by points"""
    try:
        limit = request.args.get('limit', 10, type=int)
        db = SessionLocal()
        
        top_users = db.query(User).filter(User.is_active == True).order_by(
            User.total_points.desc()
        ).limit(limit).all()
        
        leaderboard = [{
            'rank': idx + 1,
            'username': user.username,
            'total_points': user.total_points,
            'email': user.email
        } for idx, user in enumerate(top_users)]
        
        db.close()
        
        return jsonify(leaderboard), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to get leaderboard: {str(e)}'}), 500

# ==================== MAIN ====================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
