import streamlit as st
import boto3
import json
import time
import uuid
import os
import base64
import random

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

def gerar_sugestoes_fallback(pergunta, resposta):
    """
    Gera sugestões de fallback contextuais analisando palavras-chave
    da pergunta e resposta, em vez de retornar sempre as mesmas.
    """
    texto = (pergunta + " " + resposta).lower()

    banco_sugestoes = {
        "preço": [
            "Tem alguma promoção disponível?",
            "Qual o genérico mais barato?",
            "O preço é o mesmo nas duas farmácias?",
        ],
        "genérico": [
            "Quais marcas de genérico têm disponíveis?",
        ],
        "disponível": [
            "Qual a disponibilidade desse produto?",
            "Tem na outra farmácia?",
        ],
        "dipirona": [
            "Tem Dipirona infantil?",
            "Dipirona líquida está disponível?",
        ],
        "dorflex": [
            "Quais marcas de Dorflex tem na Vera Cruz?",
            "Tem algum similar ao Dorflex?",
        ],
        "vitamina": [
            "Quais marcas de vitamina C têm?",
            "Tem vitamina D disponível?",
            "Combo vitamínico está em promoção?",
        ],
        "protetor": [
            "Qual protetor solar tem FPS 50+?",
            "Tem protetor solar infantil?",
            "Protetor solar facial está disponível?",
        ],
        "farmácia": [
            "Qual farmácia tem o menor preço?",
        ],
    }

    sugestoes_encontradas = []
    for palavra_chave, opcoes in banco_sugestoes.items():
        if palavra_chave in texto:
            sugestoes_encontradas.extend(opcoes)

    if len(sugestoes_encontradas) >= 3:
        return random.sample(sugestoes_encontradas, 3)

    # Fallback genérico com aleatoriedade
    genericas = [
        "Tem esse remédio nas duas farmácias?",
        "Qual o genérico mais barato para isso?",
        "Precisa de receita para comprar?",
        "Tem promoção essa semana?",
        "Qual a diferença entre as marcas?",
        "Tem opção infantil desse produto?",
        "Qual a dosagem recomendada?",
    ]
    return random.sample(genericas, 3)


def gerar_sugestoes(pergunta, resposta):
    """Gera 3 sugestões de próximas perguntas com base no contexto."""
    prompt_sugestoes = f"""Você é um assistente de farmácia. Com base nessa troca de mensagens, gere exatamente 3 sugestões de perguntas que o cliente pode querer fazer em seguida.

Pergunta do cliente: {pergunta}
Resposta do bot: {resposta}

Regras:
- As sugestões devem ser diretamente relacionadas ao assunto da conversa
- Cada pergunta deve ser diferente das outras e explorar um ângulo distinto (ex: preço, disponibilidade, alternativas, dosagem, receita)
- Frases curtas, no máximo 10 palavras cada
- Não repita perguntas óbvias que já foram respondidas
- Responda APENAS com JSON válido, sem nenhum texto adicional, sem markdown, sem explicações

Formato exato:
{{"sugestoes": ["pergunta 1", "pergunta 2", "pergunta 3"]}}"""

    try:
        bedrock = boto3.client(
            "bedrock-runtime",
            aws_access_key_id=st.secrets["AWS_ACCESS_KEY_ID"],
            aws_secret_access_key=st.secrets["AWS_SECRET_ACCESS_KEY"],
            region_name=st.secrets["AWS_DEFAULT_REGION"]
        )
        response = bedrock.invoke_model(
            modelId="us.anthropic.claude-haiku-4-5-20251001-v1:0",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 200,
                "messages": [
                    {"role": "user", "content": prompt_sugestoes}
                ]
            })
        )
        body = json.loads(response["body"].read())
        texto = body["content"][0]["text"]
        inicio = texto.find("{")
        fim = texto.rfind("}") + 1
        if inicio == -1 or fim == 0:
            raise ValueError("JSON não encontrado na resposta")
        sugestoes = json.loads(texto[inicio:fim]).get("sugestoes", [])
        # Garante exatamente 3 sugestões não vazias
        sugestoes = [s for s in sugestoes if s.strip()][:3]
        if len(sugestoes) < 3:
            raise ValueError("Menos de 3 sugestões retornadas")
        return sugestoes
    except Exception as e:
        # Fallback dinâmico e contextual em vez de 3 perguntas fixas
        print(f"Erro ao gerar sugestões: {str(e)}")
        return gerar_sugestoes_fallback(pergunta, resposta)

# ─── AUTENTICAÇÃO ────────────────────────────────────────────────────────────
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False

if not st.session_state.autenticado:
    st.markdown("""
    <div style="display:flex; justify-content:center; margin-top:100px;">
        <div style="background:white; padding:40px; border-radius:16px; 
                    border:1.5px solid #CC0000; width:350px; text-align:center;">
            <h2 style="color:#CC0000;">🔐 Acesso Restrito</h2>
            <p style="color:#999;">Digite a senha para acessar o FarmazziniBot</p>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    senha = st.text_input("Senha", type="password", key="input_senha")
    
    if st.button("Entrar"):
        if senha == st.secrets["SENHA_ACESSO"]:
            st.session_state.autenticado = True
            st.rerun()
        else:
            st.error("Senha incorreta!")
    
    st.stop()

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
        background-color: #ffeceb;
    }
    .stChatInput > div {
        background-color: #ffeceb !important;
        border-radius: 24px !important;
        border: 1px solid #CC0000 !important;
    }
    .block-container {
        background-color: transparent !important;
    }
    div[data-testid="stButton"] button {
        background-color: #fff;
        color: #CC0000;
        border: 1.5px solid #CC0000;
        border-radius: 20px;
        font-size: 13px;
        padding: 6px 12px;
        width: 100%;
    }
    div[data-testid="stButton"] button:hover {
        background-color: #ffeceb;
        border-color: #CC0000;
        color: #CC0000;
    }
    .mensagem-boas-vindas {
        background: linear-gradient(135deg, #fff5f5 0%, #ffffff 100%);
        border: 1.5px solid #CC0000;
        border-radius: 18px 18px 18px 4px;
        padding: 16px 20px;
        margin: 12px 0 20px 0;
        color: #1A1A1A;
        font-size: 15px;
        line-height: 1.6;
        max-width: 80%;
    }
    .mensagem-boas-vindas .titulo {
        font-weight: 700;
        color: #CC0000;
        font-size: 16px;
        margin-bottom: 8px;
    }
    .mensagem-boas-vindas ul {
        margin: 8px 0 4px 0;
        padding-left: 20px;
    }
    .mensagem-boas-vindas li {
        margin-bottom: 4px;
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
        <p style="color:#b87f7b; margin-top:8px;">
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

# ─── MENSAGEM DE BOAS-VINDAS ──────────────────────────────────────────────────
if len(st.session_state.messages) == 0:
    st.markdown("""
    <div style="display:flex; justify-content:center; margin:8px 0;">
        <div class="mensagem-boas-vindas" style="text-align:center;">
            <div class="titulo">👋 Olá! Eu sou o FarmazziniBot</div>
            Seu assistente virtual das farmácias <strong>Farma Ponte</strong> e <strong>Drogaria Vera Cruz</strong>. Estou aqui para te ajudar com:
            <ul style="text-align:left;">
                <li>💊 <strong>Preços</strong> de medicamentos e produtos</li>
                <li>🏪 <strong>Disponibilidade</strong> nas duas farmácias</li>
                <li>🔄 <strong>Comparação</strong> entre marcas e genéricos</li>
            </ul>
            É só me perguntar! 😊
        </div>
    </div>
    """, unsafe_allow_html=True)

# ─── PERGUNTAS RÁPIDAS INICIAIS ───────────────────────────────────────────────
PERGUNTAS_RAPIDAS = [
    "💊 Marcas de Dipirona e preços",
    "🩺 Comparar farmácias",
    "💉 Preço do Dorflex?",
    "🧴 Tem protetor solar?",
    "💰 Remédios em promoção?",
]

if len(st.session_state.messages) == 0:
    st.markdown("""
    <div style="text-align:center; margin: 8px 0 8px;">
        <span style="font-size:13px; color:#b87f7b;">Perguntas frequentes:</span>
    </div>
    """, unsafe_allow_html=True)

    cols = st.columns(len(PERGUNTAS_RAPIDAS))
    for i, pergunta in enumerate(PERGUNTAS_RAPIDAS):
        with cols[i]:
            if st.button(pergunta, key=f"inicio_{i}"):
                st.session_state.quick_prompt = pergunta
                st.rerun()

# ─── HISTÓRICO ───────────────────────────────────────────────────────────────
if "grafico_url_pendente" not in st.session_state:
    st.session_state.grafico_url_pendente = None

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
if st.session_state.grafico_url_pendente:
    st.image(st.session_state.grafico_url_pendente, use_container_width=True)
    st.session_state.grafico_url_pendente = None

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
    grafico_url = None

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
                    grafico_url = output.get("grafico_url", None)
                    break
                elif status in ["FAILED", "TIMED_OUT", "ABORTED"]:
                    resposta = "Não possuo a base de dados necessária para responder essa pergunta, ou o produto não existe nas farmácias Vera Cruz e Farma Ponte. Você tem alguma outra pergunta?"
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
    if grafico_url:
        st.session_state.grafico_url_pendente = grafico_url

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
