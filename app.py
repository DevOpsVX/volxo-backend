from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from openai import OpenAI

app = Flask(__name__)
# ajuste o domínio do seu front aqui:
FRONT_URL = os.environ.get("FRONT_URL", "https://volxo-ad-insight.onrender.com")
CORS(app, resources={r"/api/*": {"origins": [FRONT_URL]}})

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

SYSTEM_PROMPT = (
    "Você é um analista de dados sênior, gestor de tráfego (Meta/Google Ads) sênior e "
    "copywriter experiente. Produza um texto voltado para o CLIENTE, claro e didático, "
    "com tom otimista (sem dizer que é otimista). Explique sucintamente as métricas, "
    "faça comparações entre campanhas quando útil, e encerre com próximos passos práticos. "
    "Evite jargões excessivos. Use bullet points quando ajudar a leitura."
)

@app.post("/api/analyze")
def analyze():
    data = request.get_json(force=True)

    brand = data.get("brand", "Marca")
    channel = data.get("channel", "meta")
    period = data.get("period", "")
    kpis = data.get("kpis", {})
    table = data.get("table", [])

    # resumo estruturado para o prompt
    summary = {
        "brand": brand,
        "channel": channel,
        "period": period,
        "kpis": kpis,
        "table": table
    }

    # fallback se não houver chave
    if client is None:
        text = (
            f"### Visão Geral ({brand})\n"
            f"- Canal: {channel.upper()} • Período: {period}\n"
            f"- KPIs: gasto {kpis.get('totalSpendBRL')}, alcance {kpis.get('totalReach')}, "
            f"impressões {kpis.get('totalImpressions')}, resultados {kpis.get('totalResults')}.\n\n"
            "### Oportunidades\n"
            "- Redirecionar verba para campanhas com melhor CPA e maior volume de resultados.\n"
            "- Testar criativos e chamadas orientadas à conversão.\n"
            "- Ampliar cobertura em públicos quentes para escalar com eficiência."
        )
        return jsonify({"content": text})

    # chamada à OpenAI (modelo de texto)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content":
            "Gere um texto para o cliente com base nos dados a seguir (JSON). "
            "Explique o que significam as métricas, destaque pontos fortes, "
            "faça comparações úteis e escreva recomendações práticas ao final.\n\n"
            f"Dados:\n{summary}"
        }
    ]
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.4,
        )
        content = resp.choices[0].message.content
        return jsonify({"content": content})
    except Exception as e:
        return jsonify({"content": f"Não foi possível gerar a análise automática agora. {e}"}), 200

@app.get("/health")
def health():
    return jsonify({"ok": True})
