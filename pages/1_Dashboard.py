import streamlit as st
import boto3
import json
import time
import re
import plotly.express as px

st.set_page_config(
    page_title="Dashboard — FarmazziniBot",
    page_icon="📊",
    layout="wide"
)
# ─── AUTENTICAÇÃO COMPARTILHADA ──────────────────────────────────────────────
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False

if not st.session_state.autenticado:
    st.warning("Você precisa fazer login na página principal primeiro.")
    st.stop()

# ─── CONFIGURAÇÕES ───────────────────────────────────────────────────────────
REGIAO = "us-east-2"
DATABASE = "base-concorrentes-equipe-3"
OUTPUT = "s3://athena-equipe-3/"

# ─── CLIENTE ATHENA ──────────────────────────────────────────────────────────
athena = boto3.client(
    "athena",
    aws_access_key_id=st.secrets["AWS_ACCESS_KEY_ID"],
    aws_secret_access_key=st.secrets["AWS_SECRET_ACCESS_KEY"],
    region_name=REGIAO
)

# ─── FUNÇÃO PARA EXECUTAR QUERIES ────────────────────────────────────────────
def executar_query(sql):
    response = athena.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": DATABASE},
        ResultConfiguration={"OutputLocation": OUTPUT}
    )
    execution_id = response["QueryExecutionId"]

    while True:
        status = athena.get_query_execution(
            QueryExecutionId=execution_id
        )["QueryExecution"]["Status"]["State"]
        if status == "SUCCEEDED":
            break
        elif status in ["FAILED", "CANCELLED"]:
            return []
        time.sleep(1)

    results = athena.get_query_results(QueryExecutionId=execution_id)
    columns = [col["Label"] for col in results["ResultSet"]["ResultSetMetadata"]["ColumnInfo"]]
    rows = []
    for row in results["ResultSet"]["Rows"][1:]:
        valores = [col.get("VarCharValue", "") for col in row["Data"]]
        rows.append(dict(zip(columns, valores)))
    return rows

# ─── BUSCA PARTIÇÃO MAIS RECENTE ─────────────────────────────────────────────
@st.cache_data(ttl=3600)
def buscar_particao_recente():
    rows = executar_query("""
        SELECT MAX(ano) as ano, MAX(mes) as mes, MAX(dia) as dia
        FROM "base-concorrentes-equipe-3".scrappings
        WHERE ano = (SELECT MAX(ano) FROM "base-concorrentes-equipe-3".scrappings)
        AND mes = (SELECT MAX(mes) FROM "base-concorrentes-equipe-3".scrappings
                  WHERE ano = (SELECT MAX(ano) FROM "base-concorrentes-equipe-3".scrappings))
    """)
    if rows:
        return rows[0]["ano"], rows[0]["mes"], rows[0]["dia"]
    return "2026", "05", "31"

# ─── INTERFACE ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Dashboard — FarmazziniBot",
    page_icon="📊",
    layout="wide"
)

st.markdown("""
<style>
    .stApp { background-color: #ffeceb; }
    .block-container { background-color: transparent !important; padding-top: 2rem; }
</style>
""", unsafe_allow_html=True)

st.markdown("## 📊 Dashboard — FarmazziniBot")
st.markdown("---")

ano, mes, dia = buscar_particao_recente()
st.caption(f"Dados da última coleta: {dia}/{mes}/{ano}")

# ─── MÉTRICAS PRINCIPAIS ─────────────────────────────────────────────────────
with st.spinner("Carregando métricas..."):

    total_por_farmacia = executar_query(f"""
        SELECT "farmácia", COUNT(*) as total
        FROM scrappings
        WHERE ano = '{ano}' AND mes = '{mes}' AND dia = '{dia}'
        GROUP BY "farmácia"
    """)

    disponibilidade = executar_query(f"""
        SELECT disponibilidade, COUNT(*) as total
        FROM scrappings
        WHERE ano = '{ano}' AND mes = '{mes}' AND dia = '{dia}'
        GROUP BY disponibilidade
    """)

    media_por_farmacia = executar_query(f"""
        SELECT "farmácia",
               ROUND(AVG(preco_pix), 2) as media_pix,
               ROUND(AVG(preco_cartao), 2) as media_cartao
        FROM scrappings
        WHERE ano = '{ano}' AND mes = '{mes}' AND dia = '{dia}'
        AND disponibilidade = 'Disponível'
        GROUP BY "farmácia"
    """)

    evolucao = executar_query("""
        SELECT ano, mes, dia,
               ROUND(AVG(preco_pix), 2) as media_pix,
               "farmácia"
        FROM scrappings
        WHERE disponibilidade = 'Disponível'
        GROUP BY ano, mes, dia, "farmácia"
        ORDER BY ano, mes, dia
    """)

    total_coletas = executar_query("""
        SELECT COUNT(DISTINCT ano || mes || dia) as total_dias
        FROM scrappings
    """)

# ─── CARDS DE RESUMO ─────────────────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)

total_produtos = sum(int(r["total"]) for r in total_por_farmacia)
disponiveis = next((int(r["total"]) for r in disponibilidade if r["disponibilidade"] == "Disponível"), 0)
pct_disponivel = round(disponiveis / total_produtos * 100, 1) if total_produtos > 0 else 0
n_coletas = int(total_coletas[0]["total_dias"]) if total_coletas else 0

with col1:
    st.metric("produtos na base", f"{total_produtos:,}".replace(",", "."))
with col2:
    st.metric("disponíveis agora", f"{disponiveis:,}".replace(",", "."), f"{pct_disponivel}%")
with col3:
    st.metric("coletas realizadas", n_coletas)
with col4:
    if len(media_por_farmacia) >= 2:
        medias = {r["farmácia"]: float(r["media_pix"]) for r in media_por_farmacia}
        farmacias = list(medias.keys())
        diff = round(abs(medias[farmacias[0]] - medias[farmacias[1]]), 2)
        mais_barata = min(medias, key=medias.get)
        st.metric("diferença média de preço", f"R$ {diff:.2f}", f"{mais_barata} mais barata")

st.markdown("---")

# ─── GRÁFICOS ────────────────────────────────────────────────────────────────
col_esq, col_dir = st.columns([3, 2])

with col_esq:
    st.markdown("#### evolução da média de preço (pix)")
    if evolucao:
        import pandas as pd
        df_ev = pd.DataFrame(evolucao)
        df_ev["data"] = df_ev["ano"] + "-" + df_ev["mes"] + "-" + df_ev["dia"]
        df_ev["media_pix"] = pd.to_numeric(df_ev["media_pix"], errors="coerce")
        df_pivot = df_ev.pivot(index="data", columns="farmácia", values="media_pix")
        fig = px.line(df_ev, x="data", y="media_pix", color="farmácia",
              color_discrete_map={"farma ponte": "#CC0000", "Drogaria Vera Cruz": "#185FA5"})
        st.plotly_chart(fig, use_container_width=True)

with col_dir:
    st.markdown("#### disponibilidade atual")
    if disponibilidade:
        import pandas as pd
        df_disp = pd.DataFrame(disponibilidade)
        df_disp["total"] = pd.to_numeric(df_disp["total"])
        df_disp = df_disp.set_index("disponibilidade")
        fig2 = px.bar(df_disp.reset_index(), x="disponibilidade", y="total",
              color="disponibilidade",
              color_discrete_map={"Disponível": "#1D9E75", "Indisponível": "#E24B4A"})
        st.plotly_chart(fig2, use_container_width=True)

st.markdown("---")

# ─── TABELA POR FARMÁCIA ─────────────────────────────────────────────────────
st.markdown("#### resumo por farmácia")
if total_por_farmacia and media_por_farmacia:
    import pandas as pd
    df_total = pd.DataFrame(total_por_farmacia)
    df_media = pd.DataFrame(media_por_farmacia)
    df_merged = df_total.merge(df_media, on="farmácia")
    df_merged.columns = ["farmácia", "total de produtos", "média preço pix (R$)", "média preço cartão (R$)"]
    st.dataframe(df_merged, use_container_width=True, hide_index=True)
