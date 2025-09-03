# backend/app.py
import io, os, time, logging
from flask import Flask, request, jsonify
from flask_cors import CORS
from PIL import Image
import pandas as pd

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25MB

FRONT_URL = os.getenv("FRONT_URL", "https://volxo-ad-insight.onrender.com")
CORS(app, resources={r"/api/*": {"origins": [FRONT_URL, "*"]}})

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("volxo-backend")

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/api/generate-report")
def generate_report():
    t0 = time.time()
    try:
        channels = (request.form.get("channels") or "").split(",")
        custom = request.form.get("customInstructions") or ""
        files = request.files.getlist("files")

        log.info("Nova requisição | channels=%s | custom_len=%d | files=%d",
                 channels, len(custom), len(files))

        kpis = {}
        notes = []

        # Processa CSVs e imagens
        for f in files:
            fname = f.filename.lower()
            if fname.endswith(".csv"):
                try:
                    df = pd.read_csv(f, nrows=5000)
                    for col in df.columns:
                        if "impr" in col.lower(): kpis["impressions"] = int(df[col].sum())
                        if "click" in col.lower(): kpis["clicks"] = int(df[col].sum())
                        if "cost" in col.lower(): kpis["cost"] = float(df[col].sum())
                        if "conv" in col.lower(): kpis["conversions"] = int(df[col].sum())
                    notes.append(f"CSV {fname} lido com {len(df)} linhas.")
                except Exception as e:
                    notes.append(f"Falha ao ler {fname}: {e}")
            elif any(fname.endswith(ext) for ext in [".png",".jpg",".jpeg",".webp"]):
                try:
                    img = Image.open(io.BytesIO(f.read()))
                    notes.append(f"Imagem {fname} {img.size[0]}x{img.size[1]} processada (leve).")
                except Exception as e:
                    notes.append(f"Falha imagem {fname}: {e}")
            else:
                notes.append(f"Arquivo ignorado: {fname}")

        ch = ", ".join([c.strip() for c in channels if c.strip()]) or "meta"
        kpis_lines = []
        if kpis:
            if "impressions" in kpis: kpis_lines.append(f"- **Impressões:** {kpis['impressions']:,}")
            if "clicks" in kpis: kpis_lines.append(f"- **Cliques:** {kpis['clicks']:,}")
            if "cost" in kpis: kpis_lines.append(f"- **Custo:** R$ {kpis['cost']:.2f}")
            if "conversions" in kpis: kpis_lines.append(f"- **Conversões:** {kpis['conversions']:,}")

        body = [
            f"### Relatório gerado",
            f"**Canais:** {ch}.",
            f"**Instruções:** {custom or '—'}.",
        ]
        if kpis_lines:
            body += ["", "#### KPIs principais", *kpis_lines]
        if notes:
            body += ["", "#### Observações técnicas", *[f"- {n}" for n in notes]]

        elapsed = time.time() - t0
        body += ["", f"_Processado em {elapsed:.1f}s._"]

        return jsonify({"content": "\n".join(body)})
    except Exception as e:
        log.exception("Erro na geração")
        return jsonify({"error": str(e), "content": "Não foi possível gerar totalmente. Tente novamente com um arquivo menor."}), 500
