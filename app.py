from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# -- CORS: libere SOMENTE o domínio do seu front:
FRONT_URL = "https://volxo-ad-insight.onrender.com"

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONT_URL],
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["*"],
    allow_credentials=False,
)

@app.post("/api/generate-report")
async def generate_report(
    channels: str = Form(...),
    customInstructions: str | None = Form(None),
    files: list[UploadFile] = File(default=[]),
):
    # TODO: processe files / channels e gere o conteúdo
    content = "Seu relatório gerado aqui..."
    return {"content": content}
