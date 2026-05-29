import streamlit as st
import boto3
import json
import time
import uuid
import os
import base64

# ─── CONFIGURAÇÕES ───────────────────────────────────────────────────────────
STEP_FUNCTION_ARN = "arn:aws:states:us-east-2:906513713169:stateMachine:testeequipe3"
S3_BUCKET = "farmazinibot-historico"

# ─── CLIENTES AWS ────────────────────────────────────────────────────────────
client = boto3.client(
    "stepfunctions",
    aws_access_key_id=st.secrets["AWS_ACCESS_KEY_ID"],
    aws_secret_access_key=st.secrets["AWS_SECRET_ACCESS_KEY"],
    region_name=st.secrets["AWS_DEFAULT_REGION"]
)

s3 = boto3.client(
    "s3",
    aws_access_key_id=st.secrets["AWS_ACCESS_KEY_ID"],
    aws_secret_access_key=st.secrets["AWS_SECRET_ACCESS_KEY"],
    region_name=st.secrets["AWS_DEFAULT_REGION"]
)

# ─── FUNÇÕES S3 ──────────────────────────────────────────────────────────────
def carregar_historico(session_id):
    try:
        obj = s3.get_object(Bucket=S3_BUCKET, Key=f"{session_id}.json")
        return json.loads(obj["Body"].read().decode("utf-8"))
    except Exception:
        return []

def salvar_historico(session_id, messages):
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=f"{session_id}.json",
        Body=json.dumps(messages, ensure_ascii=False),
        ContentType="application/json"
    )

def gerar_sugestoes(pergunta, resposta):
    """Gera 3 sugestões de próximas perguntas com base no contexto."""
    prompt_sugestoes = f"""Com base nessa conversa sobre farmácia:
Pergunta do usuário: {pergunta}
Resposta do bot: {resposta}

Gere exatamente 3 sugestões curtas de próximas perguntas que o usuário pode querer fazer.
Responda APENAS com um JSON assim, sem mais nada:
{{"sugestoes": ["pergunta 1", "pergunta 2", "pergunta 3"]}}"""

    try:
        bedrock = boto3.client(
            "bedrock-runtime",
            aws_access_key_id=st.secrets["AWS_ACCESS_KEY_ID"],
            aws_secret_access_key=st.secrets["AWS_SECRET_ACCESS_KEY"],
            region_name=st.secrets["AWS_DEFAULT_REGION"]
        )
        response = bedrock.invoke_model(
            modelId="amazon.titan-text-express-v1",
            body=json.dumps({
                "inputText": prompt_sugestoes,
                "textGenerationConfig": {"maxTokenCount": 200, "temperature": 0.7}
            })
        )
        body = json.loads(response["body"].read())
        texto = body["results"][0]["outputText"]
        inicio = texto.find("{")
        fim = texto.rfind("}") + 1
        return json.loads(texto[inicio:fim]).get("sugestoes", [])[:3]
    except Exception:
        return [
            "Tem esse remédio na Drogaria Vera Cruz?",
            "Qual o genérico mais barato?",
            "Precisa de receita para comprar?"
        ]

# ─── INTERFACE ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FarmazziniBot",
    page_icon="💊",
    layout="centered"
)

# ─── FUNDO ROSADO + ESTILOS ───────────────────────────────────────────────────
st.markdown("""
<style>
    .stApp {
        background-color: #FFF0F3;
    }
    .stChatInput > div {
        background-color: #FFE4EA !important;
        border-radius: 24px !important;
        border: 1px solid #F5B8C8 !important;
    }
    .block-container {
        background-color: transparent !important;
    }
    div[data-testid="stButton"] button {
        background-color: #fff;
        color: #CC0000;
        border: 1.5px solid #F5B8C8;
        border-radius: 20px;
        font-size: 13px;
        padding: 6px 12px;
        width: 100%;
    }
    div[data-testid="stButton"] button:hover {
        background-color: #FFE4EA;
        border-color: #CC0000;
        color: #CC0000;
    }
</style>
""", unsafe_allow_html=True)

# ─── LOGO ────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
logo_path = os.path.join(BASE_DIR, "logo.png")

with open(logo_path, "rb") as f:
    img_base64 = base64.b64encode(f.read()).decode()

st.markdown(
    f"""
    <div style="text-align:center; margin-top:10px;">
        <img src="data:image/png;base64,{img_base64}" width="500"/>
        <p style="color:#999; margin-top:8px;">
            Consulte preços e disponibilidade na Farma Ponte e Drogaria Vera Cruz
        </p>
    </div>
    """,
    unsafe_allow_html=True
)

# ─── SESSÃO ──────────────────────────────────────────────────────────────────
params = st.query_params
if "session_id" not in params:
    session_id = str(uuid.uuid4())
    st.query_params["session_id"] = session_id
else:
    session_id = params["session_id"]

if "messages" not in st.session_state:
    st.session_state.messages = carregar_historico(session_id)

if "quick_prompt" not in st.session_state:
    st.session_state.quick_prompt = None

if "sugestoes" not in st.session_state:
    st.session_state.sugestoes = []

# ─── PERGUNTAS RÁPIDAS INICIAIS ───────────────────────────────────────────────
PERGUNTAS_RAPIDAS = [
    "💊 Preço da Dipirona?",
    "🩺 Tem Amoxicilina?",
    "💉 Preço da insulina?",
    "🧴 Tem protetor solar?",
    "💰 Remédios em promoção?",
]

if len(st.session_state.messages) == 0:
    st.markdown("""
    <div style="text-align:center; margin: 24px 0 8px;">
        <span style="font-size:13px; color:#999;">Perguntas frequentes:</span>
    </div>
    """, unsafe_allow_html=True)

    cols = st.columns(len(PERGUNTAS_RAPIDAS))
    for i, pergunta in enumerate(PERGUNTAS_RAPIDAS):
        with cols[i]:
            if st.button(pergunta, key=f"inicio_{i}"):
                st.session_state.quick_prompt = pergunta
                st.rerun()

# ─── HISTÓRICO ───────────────────────────────────────────────────────────────
for message in st.session_state.messages:
    if message["role"] == "user":
        st.markdown(f"""
        <div style="display:flex; justify-content:flex-end; margin:8px 0;">
            <div style="background:#CC0000; color:white; padding:10px 14px;
                        border-radius:18px 18px 4px 18px; max-width:70%;">
                {message["content"]}
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div style="display:flex; justify-content:flex-start; margin:8px 0;">
            <div style="background:#fff; color:#1A1A1A; padding:10px 14px;
                        border-radius:18px 18px 18px 4px; max-width:70%;
                        border:1px solid #F5B8C8;">
                {message["content"]}
            </div>
        </div>
        """, unsafe_allow_html=True)

# ─── SUGESTÕES APÓS ÚLTIMA RESPOSTA ──────────────────────────────────────────
if st.session_state.sugestoes:
    st.markdown("""
    <div style="margin: 4px 0 2px 0;">
        <span style="font-size:12px; color:#999;">Perguntar também:</span>
    </div>
    """, unsafe_allow_html=True)
    cols = st.columns(3)
    for i, sugestao in enumerate(st.session_state.sugestoes):
        with cols[i]:
            if st.button(sugestao, key=f"sug_{i}_{sugestao[:10]}"):
                st.session_state.quick_prompt = sugestao
                st.session_state.sugestoes = []
                st.rerun()

# ─── FUNÇÃO DE ENVIO ──────────────────────────────────────────────────────────
def enviar_pergunta(prompt):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.session_state.sugestoes = []

    st.markdown(f"""
    <div style="display:flex; justify-content:flex-end; margin:8px 0;">
        <div style="background:#CC0000; color:white; padding:10px 14px;
                    border-radius:18px 18px 4px 18px; max-width:70%;">
            {prompt}
        </div>
    </div>
    """, unsafe_allow_html=True)

    with st.spinner("Consultando..."):
        try:
            execution = client.start_execution(
                stateMachineArn=STEP_FUNCTION_ARN,
                input=json.dumps({
                    "pergunta": prompt,
                    "session_id": session_id,
                    "historico": st.session_state.messages
                })
            )

            execution_arn = execution["executionArn"]

            while True:
                result = client.describe_execution(executionArn=execution_arn)
                status = result["status"]
                if status == "SUCCEEDED":
                    output = json.loads(result["output"])
                    resposta = output.get("resposta", "Não foi possível obter resposta.")
                    break
                elif status in ["FAILED", "TIMED_OUT", "ABORTED"]:
                    resposta = "Erro ao processar a consulta. Tente novamente."
                    break
                time.sleep(1)

        except Exception as e:
            resposta = f"Erro ao consultar: {str(e)}"

    st.session_state.messages.append({"role": "assistant", "content": resposta})
    salvar_historico(session_id, st.session_state.messages)

    st.markdown(f"""
    <div style="display:flex; justify-content:flex-start; margin:8px 0;">
        <div style="background:#fff; color:#1A1A1A; padding:10px 14px;
                    border-radius:18px 18px 18px 4px; max-width:70%;
                    border:1px solid #F5B8C8;">
            {resposta}
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Gera sugestões de próximas perguntas
    with st.spinner("Gerando sugestões..."):
        st.session_state.sugestoes = gerar_sugestoes(prompt, resposta)

    st.rerun()

# ─── PROCESSAR PERGUNTA RÁPIDA ────────────────────────────────────────────────
if st.session_state.quick_prompt:
    prompt = st.session_state.quick_prompt
    st.session_state.quick_prompt = None
    enviar_pergunta(prompt)

# ─── INPUT MANUAL ─────────────────────────────────────────────────────────────
if prompt := st.chat_input("Ex: Qual o preço da Dipirona na Farma Ponte?"):
    enviar_pergunta(prompt)
