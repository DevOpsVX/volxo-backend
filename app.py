import io
import os
import time
import logging
from typing import List, Tuple, Dict, Any

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

# Dados / arquivos
import pandas as pd
from PIL import Image

# PDF
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
)
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.enums import TA_CENTER
from reportlab.lib import colors

# IA
OPENAI_ENABLED = bool(os.getenv("OPENAI_API_KEY"))
if OPENAI_ENABLED:
    from openai import OpenAI
    openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25MB

FRONT_URL = os.getenv("FRONT_URL", "https://volxo-ad-insight.onrender.com")
CORS(app, resources={r"/api/*": {"origins": [FRONT_URL, "*"]}})

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("volxo-backend")

# ---------- Utilidades ----------

def parse_inputs(files) -> Tuple[Dict[str, Any], List[str]]:
    """Lê CSVs (KPIs) e valida imagens (somente metadata)."""
    kpis: Dict[str, Any] = {}
    notes: List[str] = []

    for f in files:
        fname = (f.filename or "").lower()
        if fname.endswith(".csv"):
            try:
                df = pd.read_csv(f, nrows=50000)
                # Heurística simples de KPIs
                for col in df.columns:
                    cl = col.lower()
                    if "impr" in cl and pd.api.types.is_numeric_dtype(df[col]):
                        kpis["Impressões"] = int(pd.to_numeric(df[col], errors="coerce").fillna(0).sum())
                    if "click" in cl and pd.api.types.is_numeric_dtype(df[col]):
                        kpis["Cliques"] = int(pd.to_numeric(df[col], errors="coerce").fillna(0).sum())
                    if ("cost" in cl or "custo" in cl or "spend" in cl) and pd.api.types.is_numeric_dtype(df[col]):
                        kpis["Custo (R$)"] = float(pd.to_numeric(df[col], errors="coerce").fillna(0).sum())
                    if "conv" in cl and pd.api.types.is_numeric_dtype(df[col]):
                        kpis["Conversões"] = int(pd.to_numeric(df[col], errors="coerce").fillna(0).sum())
                # Derivados
                if "Cliques" in kpis and "Impressões" in kpis and kpis["Impressões"]:
                    kpis["CTR (%)"] = round(100 * kpis["Cliques"] / kpis["Impressões"], 2)
                if "Custo (R$)" in kpis and "Cliques" in kpis and kpis["Cliques"]:
                    kpis["CPC (R$)"] = round(kpis["Custo (R$)"] / kpis["Cliques"], 2)
                if "Custo (R$)" in kpis and "Conversões" in kpis and kpis["Conversões"]:
                    kpis["CPA (R$)"] = round(kpis["Custo (R$)"] / kpis["Conversões"], 2)

                notes.append(f"CSV {fname} processado com {len(df)} linhas.")
            except Exception as e:
                notes.append(f"Falha ao ler CSV {fname}: {e}")
        elif any(fname.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp")):
            try:
                img = Image.open(f.stream)
                notes.append(f"Imagem {fname} {img.size[0]}x{img.size[1]} recebida.")
            except Exception as e:
                notes.append(f"Falha imagem {fname}: {e}")
        else:
            notes.append(f"Arquivo ignorado: {fname or 'sem nome'}")
    return kpis, notes

def build_prompt(channels: List[str], custom: str, kpis: Dict[str, Any]) -> str:
    canais = ", ".join([c.strip() for c in channels if c.strip()]) or "Meta Ads"
    kpi_lines = "\n".join([f"- **{k}:** {v}" for k, v in kpis.items()]) or "- (KPIs não identificados)"
    extra = custom or "sem observações adicionais."

    # *Tom desejado*: analista de dados sênior + gestor de tráfego (Meta/Google) + copywriter,
    # otimista (sem mencionar isso explicitamente), voltado ao cliente final.
    return f"""
Você é um Analista de Dados Sênior e Gestor de Tráfego (Meta e Google Ads) com forte domínio de copywriting.
Explique de forma clara, estratégica e amigável ao cliente (sem jargões desnecessários), mantendo um tom confiante.

Contexto:
- Canais: {canais}
- Instruções do cliente: {extra}

KPIs (lidos dos arquivos):
{kpi_lines}

Tarefas:
1) Traga um sumário executivo curto (3–5 frases) destacando pontos positivos e oportunidades.
2) Faça uma análise de desempenho (alcance, engajamento, eficiência de mídia e conversão), com interpretações objetivas.
3) Aponte 3–6 recomendações práticas e priorizadas para os próximos 7–14 dias (ex.: segmentação, criativos, verba, lances).
4) Se algum KPI estiver ausente, explique o que seria ideal capturar para a próxima versão do relatório.

Formato: Markdown com títulos (##) e listas. Não invente números; use apenas os KPIs fornecidos quando aplicável.
"""

def generate_ai_text(prompt: str) -> str:
    if not OPENAI_ENABLED:
        # Fallback quando não há chave – texto padrão útil
        return (
            "## Sumário Executivo\n"
            "Dados recebidos. KPIs foram lidos e organizados. Abaixo segue uma análise estruturada de exemplo. "
            "Para análises mais profundas, adicione sua `OPENAI_API_KEY` no backend.\n\n"
            "## Análise de Desempenho\n"
            "- Alcance/Impressões, Cliques, Conversões e Custos foram agregados.\n"
            "- CTR, CPC e CPA (se disponíveis) ajudam a medir eficiência de criativo e mídia.\n\n"
            "## Recomendações (Próximos 7–14 dias)\n"
            "1. Aumentar orçamento nos conjuntos/campanhas com melhor CPA/CTR.\n"
            "2. Testar 2–3 novos criativos com foco em proposta de valor e prova social.\n"
            "3. Ajustar segmentações com base nos públicos de maior conversão.\n"
        )

    resp = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Você é um analista sênior objetivo e confiável."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.6,
    )
    return resp.choices[0].message.content.strip()

def build_pdf(content_md: str, kpis: Dict[str, Any]) -> bytes:
    """Gera um PDF com identidade visual dark/neon + logo centralizada."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)

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
        fontSize=12,
        leading=16,
    ))

    story = []

    # Logo centralizada
    logo_path = os.path.join(os.path.dirname(__file__), "download.png")
    if os.path.exists(logo_path):
        story.append(RLImage(logo_path, width=120, height=120))
        story.append(Spacer(1, 6))

    story.append(Paragraph("Relatório Inteligente de Campanhas", styles["TitleCenter"]))
    story.append(Spacer(1, 14))

    # KPIs
    if kpis:
        data = [["Métrica", "Valor"]] + [[k, str(v)] for k, v in kpis.items()]
        t = Table(data, colWidths=[220, 220])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#18B6E6")),
            ("TEXTCOLOR", (0,0), (-1,0), colors.black),
            ("TEXTCOLOR", (0,1), (-1,-1), colors.white),
            ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#18B6E6")),
            ("BACKGROUND", (0,1), (-1,-1), colors.black),
            ("ALIGN", (0,0), (-1,-1), "CENTER"),
        ]))
        story.append(Paragraph("KPIs Principais", styles["NormalWhite"]))
        story.append(t)
        story.append(Spacer(1, 14))

    # Conteúdo (render simples do markdown -> parágrafos)
    for line in content_md.splitlines():
        if line.strip().startswith("##"):
            story.append(Spacer(1, 6))
            story.append(Paragraph(line.replace("##", "").strip(), styles["TitleCenter"]))
            story.append(Spacer(1, 6))
        else:
            story.append(Paragraph(line if line.strip() else "<br/>", styles["NormalWhite"]))

    doc.build(story)
    return buf.getvalue()

# ---------- Rotas ----------

@app.get("/health")
def health():
    return {"ok": True, "openai": OPENAI_ENABLED}

@app.post("/api/preview")
def preview():
    t0 = time.time()
    channels = (request.form.get("channels") or "").split(",")
    custom = request.form.get("customInstructions") or ""
    files = request.files.getlist("files")

    kpis, notes = parse_inputs(files)
    prompt = build_prompt(channels, custom, kpis)
    content = generate_ai_text(prompt)

    elapsed = time.time() - t0
    tech = "\n".join([f"- {n}" for n in notes])
    content += f"\n\n---\n*Prévia gerada em {elapsed:.1f}s.*\n"

    if tech:
        content += f"\n**Notas técnicas (não saem no PDF final):**\n{tech}\n"

    return jsonify({"content": content})

@app.post("/api/generate-report")
def generate_report():
    channels = (request.form.get("channels") or "").split(",")
    custom = request.form.get("customInstructions") or ""
    files = request.files.getlist("files")

    kpis, _ = parse_inputs(files)
    prompt = build_prompt(channels, custom, kpis)
    content = generate_ai_text(prompt)

    pdf_bytes = build_pdf(content, kpis)
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name="relatorio.pdf",
    )
