# app.py
# Backend Flask para análises e narrativa de relatório (português)
# Pronto para Render. Requer: Flask, flask-cors, (opcional) openai>=1.0

import os
import math
from datetime import datetime
from typing import List, Dict, Any

from flask import Flask, request, jsonify
from flask_cors import CORS

# --- Config ---
FRONT_ORIGIN = os.getenv("FRONT_ORIGIN", os.getenv("FRONT_URL", "*"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_APIKEY") or os.getenv("OPENAI_KEY")

# --- App ---
app = Flask(__name__)
# Libera apenas sua origem em produção (troque "*" pelo domínio do seu front)
CORS(app, resources={r"/api/*": {"origins": FRONT_ORIGIN}})


# ---------- Utilidades ----------
def br_money(x: float) -> str:
    try:
        return f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"


def safe_float(v, default=0.0) -> float:
    try:
        if v in (None, "", "—", "-"):
            return default
        if isinstance(v, str):
            v = v.replace("R$", "").replace(".", "").replace(",", ".").strip()
        return float(v)
    except Exception:
        return default


def pct(n, d) -> str:
    d = d or 0
    if d <= 0:
        return "0,00%"
    val = 100.0 * (n / d)
    return f"{val:,.2f}%".replace(",", "X").replace(".", ",").replace("X", ".")


def round2(v: float) -> float:
    try:
        return float(f"{v:.2f}")
    except Exception:
        return v


# ---------- Núcleo da narrativa ----------
def construir_narrativa(payload: Dict[str, Any]) -> str:
    """
    Espera um JSON com o formato:
    {
      "brand": "Volxo",
      "channel": "META"|"GOOGLE",
      "period": "Últimos 7 dias",
      "observations": "texto opcional do usuário",
      "campaigns": [
        {
          "name": "...",
          "status": "Ativa"|"Inativa"|"...",
          "spend": 111.41,
          "impressions": 8617,
          "reach": 0,                # se houver
          "results": 146,            # ex.: conversas/lead/click, o que vier do front
          "cpa": 0.76,
          "roas": 0.0,
          "conversations": 0         # se houver
        },
        ...
      ]
    }
    """
    brand = payload.get("brand") or "sua marca"
    channel = payload.get("channel") or "META"
    period = payload.get("period") or "Último período"
    user_obs = payload.get("observations") or ""
    raw_camps: List[Dict[str, Any]] = payload.get("campaigns") or []

    # Sanitiza e calcula métricas agregadas
    camps = []
    for c in raw_camps:
        camps.append({
            "name": c.get("name") or "Campanha",
            "status": (c.get("status") or "").strip(),
            "spend": round2(safe_float(c.get("spend"))),
            "impressions": int(safe_float(c.get("impressions"))),
            "reach": int(safe_float(c.get("reach"))),
            "results": int(safe_float(c.get("results"))),
            "cpa": round2(safe_float(c.get("cpa"))),
            "roas": round2(safe_float(c.get("roas"))),
            "conversations": int(safe_float(c.get("conversations")))
        })

    total_spend = round2(sum(c["spend"] for c in camps))
    total_impr = sum(c["impressions"] for c in camps)
    total_results = sum(c["results"] for c in camps)

    # CPA médio ponderado por resultados (evita média “crua” enganosa)
    if total_results > 0:
        cpa_medio = round2(sum(c["cpa"] * c["results"] for c in camps if c["results"] > 0) / max(1, total_results))
    else:
        cpa_medio = 0.0

    # Destaques: melhor CPA e maior volume de resultados
    camp_melhor_cpa = None
    camp_mais_result = None
    for c in camps:
        if c["results"] > 0:
            if not camp_melhor_cpa or c["cpa"] < camp_melhor_cpa["cpa"]:
                camp_melhor_cpa = c
        if not camp_mais_result or c["results"] > camp_mais_result["results"]:
            camp_mais_result = c

    # ---- Montagem de texto (otimista e didático) ----
    linhas = []

    linhas.append(f"# Relatório de Desempenho — {brand}")
    linhas.append(f"_Canal:_ **{channel}**  •  _Período:_ **{period}**\n")

    # Resumo
    linhas.append("## Visão Geral")
    linhas.append(
        f"O investimento total observado foi de **{br_money(total_spend)}**, "
        f"com **{total_impr:,}** impressões e **{total_results}** resultados.".replace(",", ".")
    )
    if total_results > 0:
        linhas.append(f"O **CPA médio** ficou em **{br_money(cpa_medio)}**.")
    else:
        linhas.append("Ainda não há resultados suficientes para calcular **CPA médio** de forma confiável.")

    # Métricas e “o que significam”
    linhas.append("\n## Métricas — O que observar")
    linhas.append(
        "- **Gasto**: verba investida por campanha.\n"
        "- **Impressões**: quantas vezes seus anúncios foram exibidos.\n"
        "- **Resultados**: ações geradas (ex.: conversas, leads, cliques, compras), conforme seu objetivo.\n"
        "- **CPA**: custo por resultado; quanto menor, mais eficiente.\n"
        "- **ROAS**: retorno sobre gasto; acima de 1, indica retorno positivo em campanhas de compra."
    )

    # Destaques
    linhas.append("\n## Destaques")
    if camp_melhor_cpa and camp_melhor_cpa["results"] > 0:
        linhas.append(
            f"- **Maior eficiência (melhor CPA)**: “{camp_melhor_cpa['name']}” com CPA **{br_money(camp_melhor_cpa['cpa'])}** "
            f"e **{camp_melhor_cpa['results']}** resultados."
        )
    if camp_mais_result:
        linhas.append(
            f"- **Maior volume de resultados**: “{camp_mais_result['name']}” com **{camp_mais_result['results']}** resultados."
        )
    if not camps:
        linhas.append("- Sem campanhas processadas no período.")

    # Recomendações personalizadas por campanha
    linhas.append("\n## Recomendações por Campanha")
    for c in camps:
        nome = c["name"]
        linhas.append(f"**{nome}**")
        if c["results"] > 0 and c["cpa"] > 0:
            linhas.append(
                f"- Bons sinais de tração. Avaliar **incremento gradual de verba** mantendo a eficiência de **{br_money(c['cpa'])}** por resultado."
            )
        elif c["results"] == 0 and c["impressions"] > 0:
            linhas.append(
                "- Há entrega (impressões), porém sem conversões. Sugestão: revisar **objetivo da campanha** e **criativos** "
                "(benefício + urgência leve) e afinar **públicos/segmentação**."
            )
        else:
            linhas.append("- Sem dados suficientes; considerar **reativar/testar** com segmentação e objetivo alinhados.")

        if c["roas"] > 0:
            linhas.append(f"- ROAS atual: **{c['roas']:.2f}** — acompanhar margem e cesta de produtos/serviços.")
        linhas.append("")  # linha em branco

    # Próximos passos
    linhas.append("## Próximos Passos (prioridades)")
    linhas.append(
        "- **Escalar** campanhas com melhor CPA/resultado de forma **gradual** (evita perder eficiência).\n"
        "- **Testes A/B** de criativos e chamadas (promessa tangível + benefício claro).\n"
        "- **Retargeting** em quem engajou/visitou para elevar a taxa de conversão.\n"
        "- **Frequência e CTR**: monitorar para evitar fadiga e preservar performance.\n"
        "- **Acompanhamento semanal** dos KPIs com ajustes táticos."
    )

    if user_obs:
        linhas.append("\n## Observações do Cliente")
        linhas.append(user_obs)

    # Tom otimista sem “mencionar isso diretamente”
    linhas.append("\n---\n**Resumo otimista:** os dados mostram pontos de tração reais. "
                  "Com pequenos ajustes de orçamento, criativos e segmentação, "
                  "há espaço para crescer com segurança mantendo eficiência.")

    return "\n".join(linhas)


# ---------- Rotas ----------
@app.get("/api/health")
def health():
    return jsonify({"ok": True, "time": datetime.utcnow().isoformat() + "Z"})


@app.post("/api/ai-insight")
def ai_insight():
    """
    Rota que o front chama para gerar o texto analítico final.
    Aceita JSON (application/json) ou campo 'payload' em form-data contendo JSON.
    """
    try:
        if request.is_json:
            payload = request.get_json(silent=True) or {}
        else:
            raw = request.form.get("payload") or "{}"
            import json as _json
            payload = _json.loads(raw)

        # Garante chaves mínimas
        if "campaigns" not in payload:
            payload["campaigns"] = []

        # (Opcional) OpenAI – se a variável estiver setada, usamos como “acabamento”.
        if OPENAI_API_KEY:
            try:
                # Implementação simples sem dependência rígida se a lib não existir no deploy.
                # Caso você já tenha a lib openai>=1.0 instalada, descomente e use.
                #
                # from openai import OpenAI
                # client = OpenAI(api_key=OPENAI_API_KEY)
                # system = (
                #   "Você é um analista sênior de dados de performance e gestor de tráfego (Meta/Google), "
                #   "também com forte skill de copywriting. Escreva em português do Brasil, otimista, claro e didático, "
                #   "voltado ao cliente final (não técnico)."
                # )
                # user = f"Gere uma análise a partir deste JSON de campanhas:\n{payload}"
                # resp = client.chat.completions.create(
                #   model="gpt-4o-mini",
                #   messages=[{"role":"system","content":system},{"role":"user","content":user}],
                #   temperature=0.4,
                #   max_tokens=900
                # )
                # text = resp.choices[0].message.content.strip()
                # return jsonify({"ok": True, "narrative": text})

                # Fallback controlado: se não quiser usar a API, geramos narrativa local
                text = construir_narrativa(payload)
                return jsonify({"ok": True, "narrative": text})
            except Exception:
                # Em qualquer falha ao chamar a API, retornamos a versão local
                text = construir_narrativa(payload)
                return jsonify({"ok": True, "narrative": text})

        # Sem OPENAI_API_KEY → narrativa local
        text = construir_narrativa(payload)
        return jsonify({"ok": True, "narrative": text})

    except Exception as e:
        return jsonify({"ok": False, "error": f"Falha ao gerar análise: {e}"}), 400


# ---------- Main ----------
if __name__ == "__main__":
    # Para testes locais: FLASK_ENV=development python app.py
    port = int(os.getenv("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=bool(os.getenv("FLASK_DEBUG")))
