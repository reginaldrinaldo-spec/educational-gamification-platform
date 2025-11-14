from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "message": "API is running"}), 200

@app.route('/api/test', methods=['GET'])
def test():
    return jsonify({"message": "Educational Gamification Platform API"}), 200

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
