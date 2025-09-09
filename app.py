from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from openai import OpenAI

app = Flask(__name__)
FRONT_URL = os.environ.get("FRONT_URL", "*")
CORS(app, resources={r"/api/*": {"origins": FRONT_URL}}, supports_credentials=True)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/api/analyze")
def analyze():
    if not client:
        return jsonify({"error": "OPENAI_API_KEY não configurada"}), 503

    js = request.get_json(force=True, silent=True) or {}
    brand = js.get("brand", "Marca")
    channel = js.get("channel", "meta")
    totals = js.get("totals") or {}
    rows = js.get("rows") or []

    # Prompt: analista sênior de dados + gestor de tráfego + copywriter
    sys = (
        "Você é um analista de dados sênior e gestor de tráfego (Meta e Google) "
        "com experiência de copywriter. Produza uma análise clara, objetiva e profissional, "
        "voltada ao cliente final (não técnica). Mantenha tom construtivo e otimista, "
        "sem dizer explicitamente que é otimista."
    )
    # Contexto resumido para o modelo
    lines = []
    for r in rows[:40]:
      lines.append(f"- {r.get('campaign','')} | gasto R$ {r.get('spent',0):.2f} | imp {int(r.get('impressions',0))} | res {int(r.get('results',0))} | CPA R$ {(r.get('cpa') or ( (r.get('spent') or 0)/ (r.get('results') or 1) )):.2f} | ROAS {float(r.get('roas') or 0):.2f}")

    user = f"""
Marca: {brand}
Canal: {channel}

Totais: gasto R$ {float(totals.get('spent') or 0):.2f}, impressões {int(totals.get('impressions') or 0)}, resultados {int(totals.get('results') or 0)}

Campanhas:
{chr(10).join(lines)}

Instruções:
1) Abra com um parágrafo de visão geral.
2) Explique as **métricas extraídas** e o **significado** delas para o cliente.
3) Compare campanhas que se destacam (melhor CPA/resultado vs piores) quando houver dados.
4) Liste **oportunidades e próximos passos** (ex.: redirecionar verba, testes A/B de criativos/mensagens, ajustes de segmentação e lances).
5) Feche com um resumo encorajador de próximos passos.

Formate com subtítulos (##) e listas quando fizer sentido. Escreva em Português do Brasil.
"""
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role":"system","content":sys},{"role":"user","content":user}],
            temperature=0.6,
        )
        content = resp.choices[0].message.content
        return jsonify({"content": content})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
