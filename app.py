from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
import os

app = Flask(__name__)
FRONT_URL = "https://volxo-ad-insight.onrender.com"
CORS(app, resources={r"/api/*": {"origins": FRONT_URL}})

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@app.post("/api/generate-report")
def generate_report():
    channels = request.form.get("channels", "")
    custom = request.form.get("customInstructions", "")
    files = request.files.getlist("files")

    file_names = [f.filename for f in files]

    # 🔥 Prompt atualizado
    prompt = f"""
    Você é um analista de dados sênior, gestor de tráfego Meta Ads e Google Ads sênior,
    e também um copywriter experiente.

    Sua função é gerar relatórios de desempenho de campanhas de tráfego pago,
    escritos diretamente para o cliente final.  

    O relatório deve ser:
    - Claro, bem estruturado e de fácil entendimento
    - Profissional e estratégico
    - Voltado para explicar os resultados, oportunidades e próximos passos ao cliente
    - Sempre em tom positivo e confiante, mas sem dizer explicitamente que é otimista

    Informações fornecidas:
    - Canais selecionados: {channels}
    - Instruções adicionais: {custom}
    - Arquivos recebidos: {file_names}

    Estruture o relatório com:
    1. Resumo Executivo
    2. Análise de Métricas
    3. Cenário Atual
    4. Oportunidades Identificadas
    5. Recomendações Estratégicas
    6. Próximos Passos
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=1200
    )

    content = response.choices[0].message.content
    return jsonify({"content": content})
