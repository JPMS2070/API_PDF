from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import random
import string
import os
import uuid
from datetime import datetime, timedelta
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
import io

app = FastAPI(title="API Gerador de PDF - João Filho Advocacia")

# Pasta para salvar os PDFs gerados
OUTPUT_DIR = "pdfs_gerados"
os.makedirs(OUTPUT_DIR, exist_ok=True)

PDF_MODELO = "termo_modelo.pdf"


class ClienteRequest(BaseModel):
    nome: Optional[str] = "Cliente"
    telefone: Optional[str] = ""
    email: Optional[str] = ""


def gerar_palavra_chave() -> str:
    """Gera palavra-chave aleatória com letras maiúsculas, minúsculas e números"""
    chars = string.ascii_letters + string.digits
    senha = [
        random.choice(string.ascii_uppercase),
        random.choice(string.ascii_lowercase),
        random.choice(string.digits),
        random.choice(chars)
    ]
    random.shuffle(senha)
    return ''.join(senha)


def criar_overlay_palavra_chave(palavra_chave: str, page_width: float, page_height: float) -> io.BytesIO:
    """Cria uma camada PDF com a palavra-chave posicionada sobre o campo em branco"""
    agora = datetime.now().strftime("%d/%m/%Y")
    packet = io.BytesIO()
    c = canvas.Canvas(packet, pagesize=(page_width, page_height))

    x = page_width * 0.50
    y = page_height * 0.83
    x_date = page_width * 0.25
    y_date = page_height * 0.09

    c.setFont("Helvetica-Bold", 18)
    c.setFillColorRGB(0, 0, 0)
    c.drawCentredString(x, y, palavra_chave)
    c.drawCentredString(x_date, y_date, agora)
    c.save()

    packet.seek(0)
    return packet


def gerar_pdf_personalizado(palavra_chave: str, nome_cliente: str) -> str:
    """Insere a palavra-chave no PDF modelo e salva o arquivo"""

    if not os.path.exists(PDF_MODELO):
        raise FileNotFoundError(f"PDF modelo '{PDF_MODELO}' não encontrado!")

    reader = PdfReader(PDF_MODELO)
    writer = PdfWriter()

    pagina_alvo = len(reader.pages) - 1

    for i, page in enumerate(reader.pages):
        if i == pagina_alvo:
            overlay_buffer = criar_overlay_palavra_chave(
                palavra_chave,
                float(page.mediabox.width),
                float(page.mediabox.height),
            )
            overlay_reader = PdfReader(overlay_buffer)
            page.merge_page(overlay_reader.pages[0])
        writer.add_page(page)

    unique_id = str(uuid.uuid4())[:8]
    nome_arquivo = f"termo_{unique_id}.pdf"
    caminho = os.path.join(OUTPUT_DIR, nome_arquivo)

    with open(caminho, "wb") as f:
        writer.write(f)

    return nome_arquivo


def montar_resposta(nome_cliente: str):
    """Lógica central de geração do PDF — usada por todos os endpoints"""
    palavra_chave = gerar_palavra_chave()
    nome_arquivo = gerar_pdf_personalizado(palavra_chave, nome_cliente)
    base_url = os.getenv("BASE_URL", "https://web-copy-production-c376.up.railway.app")
    link_download = f"{base_url}/download/{nome_arquivo}"

    return {
        "sucesso": True,
        "cliente": nome_cliente,
        "palavra_chave": palavra_chave,
        "link_download": link_download,
        "mensagem": f"PDF gerado com sucesso para {nome_cliente}"
    }


@app.get("/")
def health_check():
    return {"status": "online", "servico": "Gerador PDF João Filho Advocacia"}


# ✅ Endpoint GET — LiderHub chama sem precisar de body
# Exemplo: /gerar-pdf-link ou /gerar-pdf-link?nome=Maria
@app.get("/gerar-pdf-link")
def gerar_pdf_get(nome: Optional[str] = Query(default="Cliente")):
    try:
        return montar_resposta(nome)
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao gerar PDF: {str(e)}")


# ✅ Endpoint POST — para chamadas com body JSON
@app.post("/gerar-pdf")
def gerar_pdf_post(cliente: ClienteRequest):
    try:
        return montar_resposta(cliente.nome or "Cliente")
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao gerar PDF: {str(e)}")


@app.get("/download/{nome_arquivo}")
def download_pdf(nome_arquivo: str):
    """Endpoint para download do PDF gerado"""
    if "/" in nome_arquivo or "\\" in nome_arquivo or ".." in nome_arquivo:
        raise HTTPException(status_code=400, detail="Nome de arquivo inválido")

    caminho = os.path.join(OUTPUT_DIR, nome_arquivo)

    if not os.path.exists(caminho):
        raise HTTPException(status_code=404, detail="PDF não encontrado ou expirado")

    return FileResponse(
        path=caminho,
        media_type="application/pdf",
        filename="Termo_Seguranca_Joao_Filho.pdf"
    )


@app.delete("/limpar-pdfs")
def limpar_pdfs_antigos():
    """Remove PDFs com mais de 24h"""
    removidos = 0
    agora = datetime.now()
    for arquivo in os.listdir(OUTPUT_DIR):
        caminho = os.path.join(OUTPUT_DIR, arquivo)
        criado_em = datetime.fromtimestamp(os.path.getctime(caminho))
        if agora - criado_em > timedelta(hours=24):
            os.remove(caminho)
            removidos += 1
    return {"removidos": removidos}
