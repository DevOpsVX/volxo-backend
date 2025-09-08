import io
import os
import time
import logging
from typing import List, Tuple, Dict, Any

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

import pandas as pd
from PIL import Image

from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
)
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.enums import TA_CENTER
from reportlab.lib import colors

# ----------------- OpenAI (com fallback robusto) -----------------
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_ENABLED = bool(OPENAI_KEY)
openai_client = None
if OPENAI_ENABLED:
    try:
        from openai import OpenAI
        openai_client = OpenAI(api_key=OPENAI_KEY)
    except Exception as _:
        # Se falhar import, force fallback
        OPENAI_ENABLED = False

# ----------------- App & CORS -----------------
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25MB

FRONT_URL = os.getenv("FRONT_URL", "https://volxo-ad-insight.onrender.com")
# libera o front + curinga (útil no Render/preview)
CORS(app, resources={r"/api/*": {"origins": [FRONT_URL, "*"]}})

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("volxo-backend")


# ----------------- Utilidades -----------------
def parse_inputs(files) -> Tuple[Dict[str, Any], List[str]]:
    """Lê CSVs e extrai KPIs básicos; para imagens, só valida e registra metadados."""
    kpis: Dict[str, Any] = {}
    notes: List[str] = []

    for f in files:
        fname = (f.filename or "").lower()

        if fname.endswith(".csv"):
            try:
                df = pd.read_csv(f, nrows=50000)
                # Heurísticas simples
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
                if kpis.get("Impressões") and kpis.get("Cliques"):
                    kpis["CTR (%)"] = round(100 * kpis["Cliques"] / kpis["Impressões"], 2)
                if kpis.get("Cliques") and kpis.get("Custo (R$)"):
                    kpis["CPC (R$)"] = round(kpis["Custo (R$)"] / kpis["Cliques"], 2)
                if kpis.get("Conversões") and kpis.get("Custo (R$)"):
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

    return f"""
Você é um Analista de Dados Sênior e Gestor de Tráfego (Meta e Google Ads) com forte domínio de copywriting.
Explique de forma clara, estratégica e amigável ao cliente (sem jargões), mantendo um tom confiante e construtivo.

Contexto:
- Canais: {canais}
- Instruções do cliente: {extra}

KPIs (dos arquivos fornecidos):
{kpi_lines}

Tarefas:
1) Forneça um Sumário Executivo (3–5 frases) com conquistas e oportunidades.
2) Analise o desempenho (alcance, cliques, custo, conversões, eficiência de mídia).
3) Liste 3–6 recomendações práticas e priorizadas para os próximos 7–14 dias.
4) Se faltar algum KPI, diga o que seria ideal coletar para a próxima versão.

Formato: Markdown com títulos (##) e listas. Não invente números; use somente os KPIs lidos quando existirem.
"""


def generate_ai_text(prompt: str) -> str:
    # Fallback seguro mesmo quando OPENAI_API_KEY existe mas está inválida
    if not openai_client:
        return (
            "## Sumário Executivo\n"
            "Dados recebidos e KPIs calculados. Para uma análise mais profunda, adicione a `OPENAI_API_KEY` válida.\n\n"
            "## Análise de Desempenho\n"
            "- Avaliamos alcance, cliques, custo e conversões. CTR, CPC e CPA foram calculados quando disponíveis.\n\n"
            "## Recomendações (Próximos 7–14 dias)\n"
            "1. Realocar verba para campanhas com melhor eficiência (CPA/CTR).\n"
            "2. Testar criativos com proposta de valor clara e prova social.\n"
            "3. Refinar segmentações e horários de veiculação com base no histórico.\n"
        )
    try:
        resp = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Você é um analista sênior, objetivo e confiável."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.6,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        log.warning("OpenAI falhou, usando fallback. Erro: %s", e)
        return (
            "## Sumário Executivo\n"
            "Não foi possível consultar o modelo agora; usando análise base com KPIs.\n\n"
            "## Análise de Desempenho\n"
            "- Alcance, cliques, custo e conversões sintetizados.\n\n"
            "## Recomendações\n"
            "1. Aumentar investimento onde CPA está mais baixo.\n"
            "2. Testar novos criativos e títulos.\n"
            "3. Ajustar públicos e negativar termos irrelevantes.\n"
        )


def build_pdf(content_md: str, kpis: Dict[str, Any]) -> bytes:
    """Gera PDF com tema dark/neon e logo centralizada."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=36, bottomMargin=36, leftMargin=36, rightMargin=36)

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="H1Center",
        parent=styles["Heading1"],
        alignment=TA_CENTER,
        textColor=colors.HexColor("#18B6E6"),
        fontSize=20,
    ))
    styles.add(ParagraphStyle(
        name="NormalWhite",
        parent=styles["Normal"],
        textColor=colors.white,
        fontSize=11,
        leading=16,
    ))

    story = []

    # Logo centralizada (se existir em backend/download.png)
    logo_path = os.path.join(os.path.dirname(__file__), "download.png")
    if os.path.exists(logo_path):
        story.append(RLImage(logo_path, width=120, height=120))
        story.append(Spacer(1, 6))

    story.append(Paragraph("Relatório Inteligente de Campanhas", styles["H1Center"]))
    story.append(Spacer(1, 12))

    if kpis:
        data = [["Métrica", "Valor"]] + [[k, str(v)] for k, v in kpis.items()]
        t = Table(data, colWidths=[240, 240])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#18B6E6")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
            ("TEXTCOLOR", (0, 1), (-1, -1), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#18B6E6")),
            ("BACKGROUND", (0, 1), (-1, -1), colors.black),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ]))
        story.append(Paragraph("KPIs Principais", styles["NormalWhite"]))
        story.append(t)
        story.append(Spacer(1, 12))

    # Render simples do markdown (títulos "##" e linhas normais)
    for raw in content_md.splitlines():
        line = raw.strip("\n")
        if line.startswith("##"):
            story.append(Spacer(1, 6))
            story.append(Paragraph(line.replace("##", "").strip(), styles["H1Center"]))
            story.append(Spacer(1, 6))
        else:
            story.append(Paragraph(line if line else "<br/>", styles["NormalWhite"]))

    doc.build(story)
    return buf.getvalue()


# ----------------- Rotas -----------------
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
        content += f"\n**Notas técnicas (não vão para o PDF):**\n{tech}\n"

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
