import io
import os
import re
import time
from typing import List, Dict, Iterable

import pandas as pd
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)

# Libera o front (ajuste ALLOWED_ORIGIN no Render para travar por domínio)
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")
CORS(app, resources={r"/api/*": {"origins": ALLOWED_ORIGIN}})

# ------- Utilidades de parsing robusto ------- #

SEPARATORS: Iterable[str] = (",", ";", "\t", "|")
ENCODINGS: Iterable[str] = ("utf-8", "utf-8-sig", "latin1", "cp1252")

# Mapas de nomes de colunas (lowercase / sem acento).
COLMAP: Dict[str, list[str]] = {
    "impressions": [
        "impressions", "impressões", "impressoes", "impr", "impressao"
    ],
    "clicks": [
        "clicks", "cliques", "clique", "clics"
    ],
    "spend": [
        "spend", "gasto", "investimento", "amount spent", "custo", "valor gasto"
    ],
    "conversions": [
        "conversions", "conversões", "conversoes", "purchases", "leads",
        "resultados", "conversion"
    ],
    "revenue": [
        "revenue", "receita", "valor de conversão", "conversion value",
        "purchase value", "valor de compra", "valor conversao"
    ],
    "campaign": [
        "campaign", "campanha", "nome da campanha"
    ],
}

def normalize(s: str) -> str:
    """lower + remove acentos simples e espaços extras."""
    s = s.strip().lower()
    s = (s
         .replace("á", "a").replace("à", "a").replace("ã", "a").replace("â", "a")
         .replace("é", "e").replace("ê", "e")
         .replace("í", "i")
         .replace("ó", "o").replace("ô", "o").replace("õ", "o")
         .replace("ú", "u")
         .replace("ç", "c"))
    s = re.sub(r"\s+", " ", s)
    return s

def pick_column(df: pd.DataFrame, keys: list[str]) -> str | None:
    """Encontra a melhor coluna equivalente no DataFrame."""
    if df.empty:
        return None
    cols_norm = {normalize(c): c for c in df.columns}
    for key in keys:
        k = normalize(key)
        for n, original in cols_norm.items():
            if k == n or k in n:
                return original
    return None

NUM_RE = re.compile(r"[-+]?\d[\d.,]*")

def to_number_series(s: pd.Series) -> pd.Series:
    """
    Converte strings com 'R$', '%', separadores pt-BR, etc. em float.
    Regras:
      - remove tudo que não for dígito, ponto ou vírgula
      - se houver vírgula e ponto, assume '.' milhar e ',' decimal (pt-BR)
      - se houver só vírgula, troca por ponto
    """
    if s is None:
        return pd.Series(dtype="float64")

    def conv(x):
        if pd.isna(x):
            return 0.0
        if isinstance(x, (int, float)):
            return float(x)
        x = str(x)
        m = NUM_RE.search(x.replace(" ", ""))
        if not m:
            return 0.0
        x = m.group(0)
        # ambos , e . presentes -> assume , decimal
        if "," in x and "." in x:
            x = x.replace(".", "").replace(",", ".")
        elif "," in x and "." not in x:
            x = x.replace(",", ".")
        # remove símbolos restantes
        x = x.replace("R$", "").replace("%", "")
        try:
            return float(x)
        except Exception:
            return 0.0

    return s.map(conv)

def read_csv_forgiving(file_storage) -> pd.DataFrame:
    raw = file_storage.read()
    last_error = None
    for enc in ENCODINGS:
        for sep in SEPARATORS:
            try:
                df = pd.read_csv(io.BytesIO(raw), sep=sep, encoding=enc)
                if df.shape[1] > 0:
                    return df
            except Exception as e:
                last_error = e
                continue
    # fallback autodetect (pode falhar, mas tentamos tudo)
    try:
        return pd.read_csv(io.BytesIO(raw))
    except Exception as e:
        raise ValueError(f"Falha ao ler CSV: {last_error or e}")

# ------- Rota ------- #

@app.get("/healthz")
def health():
    return jsonify({"ok": True})

@app.post("/api/generate-report")
def generate_report():
    t0 = time.time()
    channels = (request.form.get("channels") or "").strip()
    custom = (request.form.get("customInstructions") or "").strip()
    files = request.files.getlist("files") or []

    csvs: List[pd.DataFrame] = []
    images: List[str] = []
    others: List[str] = []

    for f in files:
        name = (f.filename or "").lower()
        if name.endswith(".csv"):
            try:
                df = read_csv_forgiving(f)
                csvs.append(df)
            except Exception:
                others.append(name or "csv_invalido.csv")
        elif name.endswith((".png", ".jpg", ".jpeg", ".webp")):
            images.append(name)
        else:
            others.append(name or "arquivo")

    channels_human = ", ".join([c.strip() for c in channels.split(",") if c.strip()]) or "—"

    # Sem CSV -> retorna observação técnica útil (não é erro)
    if not csvs:
        content = f"""### Relatório gerado
**Canais:** {channels_human}.
**Instruções:** {custom or "—"}.

_Nenhum CSV válido foi detectado. Envie um arquivo de exportação (Meta/Google Ads) para calcular KPIs._
"""
        if images or others:
            content += "\n#### Observações técnicas\n"
            if images:
                content += f"- Imagens recebidas: {', '.join(images)}\n"
            if others:
                content += f"- Outros arquivos: {', '.join(others)}\n"
            content += f"\n_Processado em {time.time() - t0:.1f}s._\n"
        return jsonify({"content": content})

    # Junta CSVs
    df = pd.concat(csvs, ignore_index=True)

    # Descobrir colunas
    col_impr = pick_column(df, COLMAP["impressions"])
    col_clicks = pick_column(df, COLMAP["clicks"])
    col_spend = pick_column(df, COLMAP["spend"])
    col_conv = pick_column(df, COLMAP["conversions"])
    col_rev = pick_column(df, COLMAP["revenue"])
    col_campaign = pick_column(df, COLMAP["campaign"])

    # Converter numéricas
    impr = to_number_series(df[col_impr]) if col_impr else pd.Series([0]*len(df))
    clicks = to_number_series(df[col_clicks]) if col_clicks else pd.Series([0]*len(df))
    spend = to_number_series(df[col_spend]) if col_spend else pd.Series([0]*len(df))
    conv = to_number_series(df[col_conv]) if col_conv else pd.Series([0]*len(df))
    revenue = to_number_series(df[col_rev]) if col_rev else pd.Series([0]*len(df))

    # Totais
    T_impr = float(impr.sum())
    T_clicks = float(clicks.sum())
    T_spend = float(spend.sum())
    T_conv = float(conv.sum())
    T_revenue = float(revenue.sum())

    CTR = (T_clicks / T_impr * 100) if T_impr else 0.0
    CPC = (T_spend / T_clicks) if T_clicks else 0.0
    CPA = (T_spend / T_conv) if T_conv else 0.0
    ROAS = (T_revenue / T_spend) if T_spend else 0.0
    CR = (T_conv / T_clicks * 100) if T_clicks else 0.0

    # Ranking por campanha (se existir)
    top_md = ""
    if col_campaign:
        agg = pd.DataFrame({
            "campaign": df[col_campaign],
            "impr": impr,
            "clicks": clicks,
            "spend": spend,
            "conv": conv,
            "rev": revenue,
        }).groupby("campaign", as_index=False).sum(numeric_only=True)

        agg["ctr_%"] = (agg["clicks"] / agg["impr"] * 100).fillna(0.0)
        agg["cpc"] = (agg["spend"] / agg["clicks"]).fillna(0.0)
        agg["cpa"] = (agg["spend"] / agg["conv"]).fillna(0.0)
        agg["roas"] = (agg["rev"] / agg["spend"]).fillna(0.0)

        # Top 5 por spend
        top = agg.sort_values("spend", ascending=False).head(5)
        lines = ["| Campanha | Spend | Conv | CPA | ROAS | CTR |",
                 "|---|---:|---:|---:|---:|---:|"]
        for _, r in top.iterrows():
            lines.append(
                f"| {str(r['campaign'])[:40]} | R$ {r['spend']:,.2f} | {int(r['conv'])} | R$ {r['cpa']:,.2f} | {r['roas']:.2f}x | {r['ctr_%']:.2f}% |"
            )
        top_md = "\n".join(lines)

    # Narrativa & recomendações (otimista)
    narrative = f"""### Visão Geral

O desempenho recente indica **engajamento consistente** e **eficiência de investimento**. A taxa de cliques e o custo por resultado mostram qualidade criativa e boa aderência de público. Há oportunidades claras para **escalar o que já performa** e otimizar onde há atrito.

### KPIs Consolidados
- **Impressões:** {int(T_impr)}
- **Cliques:** {int(T_clicks)} — **CTR:** {CTR:.2f}%
- **Investimento:** R$ {T_spend:,.2f} — **CPC:** R$ {CPC:,.2f}
- **Conversões:** {int(T_conv)} — **CPA:** R$ {CPA:,.2f}
- **Receita:** R$ {T_revenue:,.2f} — **ROAS:** {ROAS:.2f}x
- **Taxa de Conversão (CR):** {CR:.2f}%

### Oportunidades e próximos passos
1. **Criativos vencedores**: aumente gradualmente a verba nos conjuntos com **CTR acima da mediana** e CPA competitivo.
2. **Audiências**: expanda **lookalikes 1–3%** nos públicos com melhor ROAS e refine exclusões para reduzir sobreposição.
3. **Orçamento & Lances**: ajustes de **±10–15%** nos grupos mais eficientes para escalar mantendo estabilidade de entrega.
4. **A/B testing contínuo**: roteirize variações de headline e call-to-action, priorizando os formatos que trouxeram **CPC menor**.

"""  # noqa: E501

    if top_md:
        narrative += "### Top 5 campanhas por investimento\n" + top_md + "\n"

    technical = "#### Observações técnicas\n"
    if images:
        technical += f"- Imagens recebidas: {', '.join(images)}\n"
    if others:
        technical += f"- Outros arquivos: {', '.join(others)}\n"
    technical += f"\n_Processado em {time.time() - t0:.1f}s._\n"

    header = f"""### Relatório gerado
**Canais:** {channels_human}.
**Instruções:** {custom or "—"}.
"""

    content = "\n".join([header, narrative, technical]).strip()
    return jsonify({"content": content})
