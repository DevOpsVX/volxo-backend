import os, io, base64
import pandas as pd
from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "https://volxo-ad-insight.onrender.com"}})

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# --- helpers ---------------------------------------------------------------
COMMON_MAP = {
    "date": ["date", "data", "dia"],
    "campaign": ["campaign", "campanha", "nome_da_campanha"],
    "impressions": ["impressions", "impressoes", "impressões"],
    "clicks": ["clicks", "cliques"],
    "spend": ["spend", "custo", "gasto", "amount_spent"],
    "conversions": ["conversions", "resultados", "purchases", "leads"],
    "revenue": ["revenue", "valor_vendas", "purchase_value"]
}

def normalize_cols(df: pd.DataFrame):
    df = df.copy()
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    return df

def first_col(df, keys):
    for k in keys:
        if k in df.columns: return k
    # procurar por equivalentes
    for wanted in keys:
        for col in df.columns:
            if wanted in col: return col
    return None

def detect_and_rename(df):
    df = normalize_cols(df)
    mapping = {}
    for canonical, opts in COMMON_MAP.items():
        col = first_col(df, opts+[canonical])
        if col: mapping[col] = canonical
    df = df.rename(columns=mapping)
    return df, set(mapping.values())

def kpis_from_df(df):
    # garantir numéricos
    for col in ["impressions", "clicks", "spend", "conversions", "revenue"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    totals = {c: float(df[c].sum()) if c in df.columns else 0.0
              for c in ["impressions","clicks","spend","conversions","revenue"]}

    ctr  = (totals["clicks"]/totals["impressions"]*100) if totals["impressions"] else 0.0
    cpc  = (totals["spend"]/totals["clicks"]) if totals["clicks"] else 0.0
    cpa  = (totals["spend"]/totals["conversions"]) if totals["conversions"] else 0.0
    roas = (totals["revenue"]/totals["spend"]) if totals["spend"] else 0.0

    kpis = {
        "impressions": round(totals["impressions"]),
        "clicks": round(totals["clicks"]),
        "conversions": round(totals["conversions"]),
        "spend": round(totals["spend"], 2),
        "revenue": round(totals["revenue"], 2),
        "ctr_pct": round(ctr, 2),
        "cpc": round(cpc, 2),
        "cpa": round(cpa, 2),
        "roas": round(roas, 2)
    }

    # timeseries (se tiver data)
    ts = []
    if "date" in df.columns:
        g = df.groupby("date", as_index=False)[["impressions","clicks","conversions","spend","revenue"]].sum()
        for _,r in g.iterrows():
            ctr = (r["clicks"]/r["impressions"]*100) if r["impressions"] else 0
            cpc = (r["spend"]/r["clicks"]) if r["clicks"] else 0
            cpa = (r["spend"]/r["conversions"]) if r["conversions"] else 0
            ts.append({
                "date": str(r["date"]),
                "impressions": int(r["impressions"]),
                "clicks": int(r["clicks"]),
                "conversions": int(r["conversions"]),
                "spend": float(round(r["spend"],2)),
                "revenue": float(round(r["revenue"],2)),
                "ctr_pct": float(round(ctr,2)),
                "cpc": float(round(cpc,2)),
                "cpa": float(round(cpa,2)),
            })

    # top campanhas
    camps = []
    if "campaign" in df.columns:
        g = df.groupby("campaign", as_index=False)[["impressions","clicks","conversions","spend","revenue"]].sum()
        g["ctr_pct"] = (g["clicks"]/g["impressions"]*100).fillna(0)
        g["cpc"] = (g["spend"]/g["clicks"]).replace([pd.NA, pd.NaT], 0).fillna(0)
        g["cpa"] = (g["spend"]/g["conversions"]).replace([pd.NA, pd.NaT], 0).fillna(0)
        g = g.sort_values("conversions", ascending=False).head(10)
        for _,r in g.iterrows():
            camps.append({
                "campaign": r["campaign"],
                "impressions": int(r["impressions"]),
                "clicks": int(r["clicks"]),
                "conversions": int(r["conversions"]),
                "spend": float(round(r["spend"],2)),
                "revenue": float(round(r["revenue"],2)),
                "ctr_pct": float(round(r["ctr_pct"],2)),
                "cpc": float(round(r["cpc"],2)),
                "cpa": float(round(r["cpa"],2)),
            })

    return kpis, ts, camps

def image_to_dataurl(file_storage):
    ext = os.path.splitext(file_storage.filename or "")[1].lower().strip(".")
    b64 = base64.b64encode(file_storage.read()).decode("utf-8")
    mime = f"image/{'jpeg' if ext in ['jpg','jpeg'] else 'png'}"
    return f"data:{mime};base64,{b64}"

# --- endpoint --------------------------------------------------------------
@app.post("/api/generate-report")
def generate_report():
    channels = (request.form.get("channels") or "").lower()
    custom   = request.form.get("customInstructions") or ""

    csv_frames = []
    images_dataurls = []
    for f in request.files.getlist("files"):
        name = (f.filename or "").lower()
        if name.endswith(".csv"):
            try:
                df = pd.read_csv(f)
            except Exception:
                f.seek(0)
                df = pd.read_csv(f, sep=";")
            df, detected = detect_and_rename(df)
            csv_frames.append(df)
        elif name.endswith((".png",".jpg",".jpeg")):
            images_dataurls.append(image_to_dataurl(f))

    # agrega CSVs (se houver)
    kpis = {}; timeseries = []; campaigns = []
    if csv_frames:
        big = pd.concat(csv_frames, ignore_index=True)
        kpis, timeseries, campaigns = kpis_from_df(big)

    # prompt IA
    sys_prompt = (
        "Você é um analista de dados sênior, gestor de tráfego Meta e Google Ads sênior, "
        "e copywriter experiente. Gere relatórios claros, estratégicos, de fácil entendimento, "
        "voltados ao cliente final, mantendo um tom positivo e confiante (sem dizer que é otimista)."
    )

    kpis_md = (
        f"| KPI | Valor |\n|---|---|\n"
        f"| Impressões | {kpis.get('impressions','-')} |\n"
        f"| Cliques | {kpis.get('clicks','-')} |\n"
        f"| Conversões | {kpis.get('conversions','-')} |\n"
        f"| CTR | {kpis.get('ctr_pct','-')}% |\n"
        f"| CPC | R$ {kpis.get('cpc','-')} |\n"
        f"| CPA | R$ {kpis.get('cpa','-')} |\n"
        f"| Investimento | R$ {kpis.get('spend','-')} |\n"
        f"| Receita | R$ {kpis.get('revenue','-')} |\n"
        f"| ROAS | {kpis.get('roas','-')} |\n"
    ) if kpis else "Sem dados numéricos processados."

    user_prompt = f"""
Canais: {channels or 'não informado'}
Instruções do usuário: {custom or '—'}

KPIs calculados:
{kpis_md}

Se existirem, considere as criativas (imagens) para insights de mensagem/oferta/persona.

Estruture o relatório em:
1. Resumo executivo
2. Análise de métricas (cite os KPIs acima)
3. Cenário atual
4. Oportunidades identificadas
5. Recomendações estratégicas (com prioridade)
6. Próximos passos
"""

    # montar conteúdo (texto + imagens, se houver)
    content = [{"type": "text", "text": user_prompt}]
    for url in images_dataurls[:4]:  # limita a 4 imagens
        content.append({"type": "image_url", "image_url": {"url": url}})

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": content}
        ],
        temperature=0.7,
        max_tokens=1300
    )
    text = resp.choices[0].message.content

    return jsonify({
        "content": text,            # markdown do relatório
        "kpis": kpis,               # números para tabelas
        "timeseries": timeseries,   # para gráficos
        "campaigns": campaigns      # top campanhas
    })
