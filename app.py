from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
import logging

app = Flask(__name__)

FRONT_URL = "https://volxo-ad-insight.onrender.com"  # domínio do front

# CORS para as rotas /api/*
CORS(app, resources={r"/api/*": {"origins": FRONT_URL}})

logging.basicConfig(level=logging.INFO)

@app.get("/")
def home():
    return "OK"

@app.get("/health")
def health():
    return {"status": "up"}

@app.post("/api/generate-report")
def generate_report():
    # logs para debug
    app.logger.info("POST /api/generate-report | form=%s | files=%s",
                    dict(request.form), list(request.files.keys()))
    channels = request.form.get("channels", "")
    custom = request.form.get("customInstructions")
    files = request.files.getlist("files")

    # por enquanto, devolvemos algo simples (só para comprovar a integração)
    content = (
        f"Relatório gerado. Canais: {channels}. "
        f"Instruções: {custom or '—'}. "
        f"Arquivos recebidos: {len(files)}"
    )
    return jsonify({"content": content})
