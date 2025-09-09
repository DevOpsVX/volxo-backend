import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI

# -------------------- Config --------------------
FRONT_ORIGIN = os.getenv("FRONT_ORIGIN", "*").strip() or "*"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

app = Flask(__name__)
CORS(
    app,
    resources={r"/api/*": {"origins": FRONT_ORIGIN}},
    methods=["POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# Cliente OpenAI
if not OPENAI_API_KEY:
    # Não encerramos a app; retornamos erro amigável na chamada
    client = None
else:
    client = OpenAI(api_key=OPENAI_API_KEY)

# -------------------- Util --------------------
def safe_float(v, default=0.0):
    try:
        if v is None:
            return default
        if isinstance(v, (int, float)):
            return float(v)
        s = str(v).strip()
        s = s.replace("R$", "").replace(".", "").replace(",", ".")
        return float(s)
    except Exception:
        return default

def safe_int(v, default=0):
    try:
        return int(round(safe_float(v, default)))
    except Exception:
        return default

def summarize_campaigns(camps):
    """
    Retorna um resumo numérico consolidado e também linhas normalizadas (strings limpas).
    """
    total_spend = 0.0
    total_impr = 0
    total_results = 0
    lines = []

    for c in camps:
        name = str(c.get("name") or c.get("campanha") or "").strip()
        status = str(c.get("status") or "").strip()
        spend = safe_float(c.get("spend"))
        impressions = safe_int(c.get("impressions"))
        # Prioriza conversas/resultados
        results = safe_int(c.get("results") or c.get("conversations"))
        cpa = safe_float(c.get("cpa")) if results > 0 else (spend / results if results > 0 else 0.0)
        roas = safe_float(c.get("roas"))
        reach = safe_int(c.get("reach"))

        total_spend += spend
        total_impr += impressions
        total_results += results

        lines.append({
            "name": name,
            "status": status,
            "spend": spend,
            "impressions": impressions,
            "results": results,
            "cpa": cpa if c.get("cpa") is not None else (spend / results if results > 0 else 0.0),
            "roas": roas,
            "reach": reach
        })

    return {
        "total_spend": total_spend,
        "total_impr": total_impr,
        "total_results": total_results,
        "rows": lines
    }

def build_user_prompt(brand, channel, period, camps, observations):
    """
    Prompt com dados brutos organizados. Evita markdown pesado para não "poluir" o PDF.
    """
    resumo = summarize_campaigns(camps)
    linhas_texto = []
    for r in resumo["rows"]:
        linhas_texto.append(
            f"- Campanha: {r['name']}\n"
            f"  Status: {r['status'] or 'Não informado'}\n"
            f"  Gasto: R$ {r['spend']:.2f}\n"
            f"  Impressões: {r['impressions']}\n"
            f"  Resultados/Conversas: {r['results']}\n"
            f"  CPA: R$ {r['cpa']:.2f}\n"
            f"  ROAS: {r['roas']:.2f}\n"
            f"  Alcance: {r['reach']}\n"
        )

    obs_txt = (observations or "").strip()
    if obs_txt:
        obs_txt = f"\nOBSERVAÇÕES DO USUÁRIO:\n{obs_txt}\n"

    return (
        f"MARCA: {brand}\n"
        f"CANAL: {channel}\n"
        f"PERÍODO: {period}\n"
        f"RESUMO GERAL: gasto=R$ {resumo['total_spend']:.2f}, "
        f"impressões={resumo['total_impr']}, resultados={resumo['total_results']}\n\n"
        f"CAMPANHAS:\n" + "\n".join(linhas_texto) + f"\n{obs_txt}"
        "\nINSTRUÇÕES PARA A NARRATIVA:\n"
        "1) Escreva para o cliente final, de forma clara e positiva (sem mencionar que está sendo otimista).\n"
        "2) Explique o significado das principais métricas (gasto, impressões, conversas/resultados, CPA, ROAS, alcance).\n"
        "3) Comente o desempenho de cada campanha individualmente, destacando o que funcionou.\n"
        "4) Se fizer sentido, compare campanhas; se houver apenas uma, foque na evolução e no potencial.\n"
        "5) Recomende próximos passos práticos (otimizações de orçamento, criativos, segmentação, objetivo de campanha etc.).\n"
        "6) Evite markdown pesado (*, ##). Use apenas títulos simples e parágrafos curtos.\n"
        "7) Texto em português do Brasil.\n"
    )

SYSTEM_PROMPT = (
    "Você é um analista de dados sênior, também gestor de tráfego (Meta e Google Ads) "
    "e copywriter experiente. Sua missão é produzir uma análise clara, convincente e "
    "orientada a valor para o CLIENTE FINAL, mantendo um tom confiante e positivo sem "
    "declarar isso explicitamente. Explique métricas, destaque aprendizados e proponha "
    "próximos passos práticos. Evite jargões desnecessários e não use markdown pesado."
)

# -------------------- Rotas --------------------
@app.post("/api/ai-insight")
def ai_insight():
    if client is None:
        return jsonify({"error": "OPENAI_API_KEY não configurada no servidor."}), 500

    try:
        data = request.get_json(silent=True) or {}
        brand = str(data.get("brand") or "Marca").strip()
        channel = str(data.get("channel") or "META").strip()
        period = str(data.get("period") or "Período não informado").strip()
        campaigns = data.get("campaigns") or []
        observations = data.get("observations") or ""

        if not isinstance(campaigns, list) or len(campaigns) == 0:
            return jsonify({"error": "Payload inválido: 'campaigns' precisa ser uma lista com ao menos 1 item."}), 400

        user_prompt = build_user_prompt(brand, channel, period, campaigns, observations)

        # Chamada ao modelo (GPT-4o-mini por padrão; ajuste se desejar)
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.6,
            max_tokens=900,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )

        text = completion.choices[0].message.content.strip()
        return jsonify({"narrative": text})

    except Exception as e:
        return jsonify({"error": f"Falha ao gerar análise: {str(e)}"}), 500

@app.get("/api/health")
def health():
    return jsonify({"ok": True})

# -------------------- Main (dev local) --------------------
if __name__ == "__main__":
    # Para desenvolvimento local: flask run (ou python app.py)
    # Em produção (Render), use: gunicorn app:app
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
