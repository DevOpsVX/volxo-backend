from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
FRONT_URL = "https://volxo-ad-insight.onrender.com"  # seu domínio do front
CORS(app, resources={r"/api/*": {"origins": FRONT_URL}})

@app.post("/api/generate-report")
def generate_report():
    channels = request.form.get("channels", "")
    custom = request.form.get("customInstructions")
    files = request.files.getlist("files")
    return jsonify({"content": "Seu relatório gerado aqui..."})
