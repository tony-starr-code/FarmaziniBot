import streamlit as st
import boto3
import json
import time
import uuid

# ─── CONFIGURAÇÕES ───────────────────────────────────────────────────────────
STEP_FUNCTION_ARN = "arn:aws:states:us-east-2:906513713169:stateMachine:testeequipe3"
REGIAO = "us-east-2"

# ─── CLIENTE AWS ─────────────────────────────────────────────────────────────
client = boto3.client("stepfunctions", region_name=REGIAO)

# ─── INTERFACE ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FarmazziniBot",
    page_icon="💊",
    layout="centered"
)

import os
import base64

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
logo_path = os.path.join(BASE_DIR, "logo.png")

with open(logo_path, "rb") as f:
    img_base64 = base64.b64encode(f.read()).decode()

st.markdown(
    f"""
    <div style="text-align:center; margin-top:10px;">
        <img src="data:image/png;base64,{img_base64}" width="500"/>
        <p style="color:gray; margin-top:8px;">
            Consulte preços e disponibilidade na Farma Ponte e Drogaria Vera Cruz
        </p>
    </div>
    """,
    unsafe_allow_html=True
)

# ─── SESSÃO ──────────────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

# ─── HISTÓRICO ───────────────────────────────────────────────────────────────
for message in st.session_state.messages:
    if message["role"] == "user":
        st.markdown(f"""
        <div style="display:flex; justify-content:flex-end; margin:8px 0;">
            <div style="background:#CC0000; color:white; padding:10px 14px; border-radius:18px 18px 4px 18px; max-width:70%;">
                {message["content"]}
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div style="display:flex; justify-content:flex-start; margin:8px 0;">
            <div style="background:#F0F0F0; color:#1A1A1A; padding:10px 14px; border-radius:18px 18px 18px 4px; max-width:70%;">
                {message["content"]}
            </div>
        </div>
        """, unsafe_allow_html=True)

# ─── INPUT ───────────────────────────────────────────────────────────────────
if prompt := st.chat_input("Ex: Qual o preço da Dipirona na Farma Ponte?"):
    st.session_state.messages.append({"role": "user", "content": prompt})

    st.markdown(f"""
    <div style="display:flex; justify-content:flex-end; margin:8px 0;">
        <div style="background:#CC0000; color:white; padding:10px 14px; border-radius:18px 18px 4px 18px; max-width:70%;">
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
                    "session_id": st.session_state.session_id
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

    st.markdown(f"""
    <div style="display:flex; justify-content:flex-start; margin:8px 0;">
        <div style="background:#F0F0F0; color:#1A1A1A; padding:10px 14px; border-radius:18px 18px 18px 4px; max-width:70%;">
            {resposta}
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.session_state.messages.append({"role": "assistant", "content": resposta})