from flask import Flask, request, jsonify
from flask_cors import CORS
import os, json

app = Flask(__name__)
FRONT_URL = os.getenv("FRONT_URL", "*")
CORS(app, resources={r"/api/*": {"origins": FRONT_URL}})

@app.get("/api/health")
def health():
    return {"ok": True}

@app.post("/api/generate-report")
def generate_report():
    """
    Espera JSON: {
      "brand": "Volxo",
      "periodText": "Últimos 7 dias",
      "channels": ["meta"],
      "campaigns": [{ name, spend, impressions, results, ctr, roas, reach, cpa }]
    }
    Retorna { "narrative": "..." }
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        brand = data.get("brand", "Marca")
        period = data.get("periodText", "período")
        campaigns = data.get("campaigns", [])

        # Narrativa simples e otimista (fallback no server, sem OpenAI)
        total_spend = sum(c.get("spend", 0) or 0 for c in campaigns)
        total_imp = sum(c.get("impressions", 0) or 0 for c in campaigns)
        total_conv = sum(c.get("results", 0) or 0 for c in campaigns)
        avg_cpa = (
            (sum((c.get("cpa") or 0) for c in campaigns) / max(len(campaigns), 1))
            if campaigns else 0
        )

        top_by_conv = sorted(campaigns, key=lambda x: x.get("results", 0) or 0, reverse=True)[:3]
        top_names = ", ".join(c["name"] for c in top_by_conv) or "—"

        narrative = f"""
# Relatório de Desempenho — {brand}
_Período: {period}._

**Visão geral.**
O investimento total foi de **R$ {total_spend:,.2f}**, com **{int(total_imp):,} impressões**
e **{int(total_conv):,} conversões/resultados**. O CPA médio observado ficou em **R$ {avg_cpa:,.2f}**.
Mantivemos uma entrega consistente, com potencial para ganho de escala controlada.

**Campanhas em destaque.**
Entre as campanhas com melhor tração em conversões estão: **{top_names}**.
Elas apresentam sinais de eficiência que podem ser replicados para ampliar a cobertura.

**Oportunidades e próximos passos.**
- Realocar verba para os conjuntos com **melhor CPA** e estabilidade de entrega.
- Testar variações de criativo e chamadas (ênfase em **benefício + urgência leve**).
- Manter audiência quente ativa e expandir gradativamente públicos semelhantes.
- Monitorar frequência e CTR para evitar fadiga e preservar a eficiência.

_Resumo otimista:_ estamos no caminho certo. Com pequenos ajustes de orçamento,
testes estruturados de criativos e foco em públicos de maior propensão, a tendência
é **crescer com controle de custos**.
        """.strip()

        return jsonify({"narrative": narrative})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
