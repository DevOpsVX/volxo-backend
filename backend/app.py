import os
from fastapi import FastAPI, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from openai import OpenAI

# Pega a chave do ambiente
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY não está definida!")

client = OpenAI(api_key=OPENAI_API_KEY)

app = FastAPI()

# CORS (libera seu frontend no Render)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # pode trocar para ["https://seu-front.onrender.com"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/generate-report")
async def generate_report(
    channels: str = Form(...),
    customInstructions: Optional[str] = Form(None),
    files: Optional[List[UploadFile]] = None
):
    """
    Recebe canais, instruções e arquivos -> retorna relatório em texto
    """
    # Constrói prompt inicial
    base_prompt = f"""
    Você é um analista de dados sênior especializado em campanhas Meta Ads e Google Ads.
    Gere um relatório claro, otimista e estratégico.

    Canais selecionados: {channels}
    """
    if customInstructions:
        base_prompt += f"\n\nInstruções adicionais do usuário: {customInstructions}"

    # Se arquivos forem enviados, adiciona info
    if files:
        base_prompt += f"\n\nO usuário enviou {len(files)} arquivo(s) com dados para análise."

    # Chamada ao modelo
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Você é um analista de tráfego pago experiente."},
            {"role": "user", "content": base_prompt},
        ],
        max_tokens=1000,
        temperature=0.7
    )

    content = response.choices[0].message.content
    return {"content": content}
