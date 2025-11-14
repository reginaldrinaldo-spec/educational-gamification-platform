from flask import Flask, jsonify
import os
from sqlalchemy import create_engine, text
import jwt

app = Flask(__name__)

# Test database connection
db_url = os.environ.get('DATABASE_URL')
if db_url:
    # SQLAlchemy expects postgresql:// not postgres://
    if db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql://', 1)
    engine = create_engine(db_url)
else:
    engine = None

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "message": "API is running"}), 200

@app.route('/api/test', methods=['GET'])
def test():
    return jsonify({"message": "Educational Gamification Platform API"}), 200

@app.route('/api/db-status', methods=['GET'])
def db_status():
    if not engine:
        return jsonify({"status": "no-database", "message": "DATABASE_URL not configured"}), 200
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return jsonify({"status": "connected", "message": "Database connection successful"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
