# backend/app.py
import io, os, time, logging
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from PIL import Image
import pandas as pd

# PDF libs
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.enums import TA_CENTER
from reportlab.lib import colors

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
                        if "impr" in col.lower(): kpis["Impressões"] = int(df[col].sum())
                        if "click" in col.lower(): kpis["Cliques"] = int(df[col].sum())
                        if "cost" in col.lower(): kpis["Custo (R$)"] = float(df[col].sum())
                        if "conv" in col.lower(): kpis["Conversões"] = int(df[col].sum())
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

        elapsed = time.time() - t0

        # === GERAR PDF COM ESTILO DARK/NEON ===
        pdf_buffer = io.BytesIO()
        doc = SimpleDocTemplate(pdf_buffer, pagesize=A4)

        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(
            name="TitleCenter",
            parent=styles["Heading1"],
            alignment=TA_CENTER,
            textColor=colors.HexColor("#18B6E6"),
            fontSize=20
        ))
        styles.add(ParagraphStyle(
            name="NormalWhite",
            parent=styles["Normal"],
            textColor=colors.white,
            fontSize=12
        ))

        story = []

        # Logo
        logo_path = os.path.join(os.path.dirname(__file__), "download.png")
        if os.path.exists(logo_path):
            story.append(RLImage(logo_path, width=120, height=120))
            story.append(Spacer(1, 12))

        # Título
        story.append(Paragraph("Relatório Inteligente de Campanhas", styles["TitleCenter"]))
        story.append(Spacer(1, 20))

        # Info básica
        story.append(Paragraph(f"Canais analisados: {', '.join(channels) or 'Meta'}", styles["NormalWhite"]))
        story.append(Paragraph(f"Instruções adicionais: {custom or 'Nenhuma'}", styles["NormalWhite"]))
        story.append(Spacer(1, 20))

        # Tabela de KPIs
        if kpis:
            data = [["Métrica", "Valor"]] + [[k, str(v)] for k,v in kpis.items()]
            t = Table(data, colWidths=[200, 200])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#18B6E6")),
                ("TEXTCOLOR", (0,0), (-1,0), colors.black),
                ("TEXTCOLOR", (0,1), (-1,-1), colors.white),
                ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#18B6E6")),
                ("BACKGROUND", (0,1), (-1,-1), colors.black),
                ("ALIGN", (0,0), (-1,-1), "CENTER")
            ]))
            story.append(Paragraph("KPIs Principais", styles["NormalWhite"]))
            story.append(t)
            story.append(Spacer(1, 20))

        # Observações
        if notes:
            story.append(Paragraph("Observações Técnicas:", styles["NormalWhite"]))
            for n in notes:
                story.append(Paragraph(f"- {n}", styles["NormalWhite"]))

        story.append(Spacer(1, 20))
        story.append(Paragraph(f"Processado em {elapsed:.1f}s", styles["NormalWhite"]))

        doc.build(story)

        pdf_buffer.seek(0)
        return send_file(pdf_buffer, mimetype="application/pdf", as_attachment=True, download_name="relatorio.pdf")

    except Exception as e:
        log.exception("Erro na geração")
        return jsonify({"error": str(e), "content": "Erro ao gerar PDF"}), 500
