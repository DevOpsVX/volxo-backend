import io
import os
import time
from typing import List

import pandas as pd
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)

# Libera o front. Ajuste a env ALLOWED_ORIGIN no Render se quiser travar por domínio.
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")
CORS(app, resources={r"/api/*": {"origins": ALLOWED_ORIGIN}})


@app.get("/healthz")
def health():
    return jsonify({"ok": True})


def _read_csv_any(file_storage) -> pd.DataFrame:
    """Lê CSV com separador flexível (vírgula ou ponto-e-vírgula)."""
    raw = file_storage.read()
    for sep in [",", ";", "\t", "|"]:
        try:
            df = pd.read_csv(io.BytesIO(raw), sep=sep)
            # precisa ter pelo menos 1 coluna legível
            if df.shape[1] > 0:
                return df
        except Exception:
            pass
    # última tentativa com pandas autodetect
    return pd.read_csv(io.BytesIO(raw))


def _sum_safe(df: pd.DataFrame, col: str) -> float:
    if not col or col not in df.columns:
        return 0.0
    return pd.to_numeric(df[col], errors="coerce").fillna(0).sum()


def _find_col(df: pd.DataFrame, *hints: str) -> str | None:
    cols = {c.lower().strip(): c for c in df.columns}
    for hint in hints:
        for k, v in cols.items():
            if hint in k:
                return v
    return None


@app.post("/api/generate-report")
def generate_report():
    t0 = time.time()
    channels = (request.form.get("channels") or "").strip()
    custom = (request.form.get("customInstructions") or "").strip()
    files = request.files.getlist("files") or []

    csvs: List[pd.DataFrame] = []
    image_names: List[str] = []
    other_files: List[str] = []

    for f in files:
        name = (f.filename or "").lower()
        if name.endswith(".csv"):
            try:
                df = _read_csv_any(f)
                csvs.append(df)
            except Exception:
                other_files.append(name or "csv_desconhecido.csv")
        elif name.endswith((".png", ".jpg", ".jpeg", ".webp")):
            image_names.append(name)
        else:
            other_files.append(name or "arquivo")

    # KPIs básicos caso exista CSV
    kpis_md = ""
    narrative_md = ""
    if csvs:
        df_all = pd.concat(csvs, ignore_index=True)
        # tentativa de mapear nomes comuns das colunas (pt/en)
        col_impr = _find_col(df_all, "impress", "impr")
        col_clicks = _find_col(df_all, "click")
        col_spend = _find_col(df_all, "spend", "gasto", "cost", "custo", "valor")
        col_conv = _find_col(df_all, "convers", "purchase", "lead", "conversion")
        col_rev = _find_col(df_all, "rev", "receita", "purchase value", "value", "valor de compra")

        impressions = _sum_safe(df_all, col_impr)
        clicks = _sum_safe(df_all, col_clicks)
        spend = _sum_safe(df_all, col_spend)
        conv = _sum_safe(df_all, col_conv)
        revenue = _sum_safe(df_all, col_rev)

        ctr = (clicks / impressions * 100) if impressions else 0.0
        cpc = (spend / clicks) if clicks else 0.0
        cpa = (spend / conv) if conv else 0.0
        roas = (revenue / spend) if spend else 0.0

        kpis_md = f"""\
**KPIs Consolidados**

- Impressões: {int(impressions)}
- Cliques: {int(clicks)}
- CTR: {ctr:.2f}%
- Investimento (Spend): R$ {spend:,.2f}
- Conversões: {int(conv)}
- CPA: R$ {cpa:,.2f}
- Receita: R$ {revenue:,.2f}
- ROAS: {roas:.2f}x
"""

        narrative_md = """\
### Insights Principais

- O alcance indica boa penetração de público, com sinais de eficiência criativa refletidos no CTR.
- A estrutura de custos está sob controle; há espaço para otimizações táticas em alocação por campanha/segmento.
- O funil de conversão mostra tração; focar em criativos vencedores e públicos lookalike tende a reforçar o ROI.

### Recomendações Prioritárias

1) **Criativos** – Aumentar a frequência dos anúncios com CTR acima da mediana e testar novas variações do top-3.
2) **Audiências** – Realocar budget para públicos com CPA abaixo da média; expandir LLA 1-3% onde a escala é viável.
3) **Lances & Orçamento** – Ajustes incrementais (±10–15%) nos conjuntos com melhor ROAS mantendo estabilidade de entrega.
"""
    else:
        narrative_md = "_Nenhum CSV reconhecido; gerei apenas observações técnicas dos anexos._"

    tech_md = "#### Observações técnicas\n"
    if image_names:
        tech_md += f"- Imagens recebidas: {', '.join(image_names)}\n"
    if other_files:
        tech_md += f"- Outros arquivos recebidos: {', '.join(other_files)}\n"
    tech_md += f"\n_Processado em {time.time() - t0:.1f}s._\n"

    channels_human = ", ".join([c.strip() for c in channels.split(",") if c.strip()]) or "—"

    header = f"""\
### Relatório gerado
**Canais:** {channels_human}.
**Instruções:** {custom or "—"}.
"""

    content = "\n".join([header, kpis_md, narrative_md, tech_md]).strip()

    return jsonify({"content": content})
