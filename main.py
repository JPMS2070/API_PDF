from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import random
import string
import os
import uuid
from datetime import datetime, timedelta
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
import io

app = FastAPI(title="API Gerador de PDF - João Filho Advocacia")

# Pasta para salvar os PDFs gerados
OUTPUT_DIR = "pdfs_gerados"
os.makedirs(OUTPUT_DIR, exist_ok=True)

PDF_MODELO = "termo_modelo.pdf"


class ClienteRequest(BaseModel):
    nome: str = "Cliente"
    # Campos opcionais que o LeadHub pode enviar
    telefone: str = ""
    email: str = ""


def gerar_palavra_chave(tamanho=4) -> str:
    """Gera palavra-chave aleatória com letras maiúsculas, minúsculas e números"""
    chars = string.ascii_letters + string.digits
    # Garante pelo menos 1 maiúscula, 1 minúscula, 1 número
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
    packet = io.BytesIO()
    c = canvas.Canvas(packet, pagesize=(page_width, page_height))

    # ⚠️ AJUSTE ESTAS COORDENADAS conforme o seu PDF modelo
    # x, y = posição onde a palavra aparecerá (medido a partir do canto inferior esquerdo)
    # Para descobrir a posição correta, veja o guia no README
    x = page_width * 0.50   # ~centro horizontal do campo
    y = page_height * 0.83  # altura do campo na página 5

    c.setFont("Helvetica-Bold", 18)
    c.setFillColorRGB(0, 0, 0)  # Cor preta
    c.drawCentredString(x, y, palavra_chave)
    c.save()

    packet.seek(0)
    return packet


def gerar_pdf_personalizado(palavra_chave: str, nome_cliente: str) -> str:
    """Insere a palavra-chave no PDF modelo e salva o arquivo"""

    if not os.path.exists(PDF_MODELO):
        raise FileNotFoundError(f"PDF modelo '{PDF_MODELO}' não encontrado!")

    reader = PdfReader(PDF_MODELO)
    writer = PdfWriter()

    # Página onde a palavra-chave aparece (última página = índice -1)
    pagina_alvo = len(reader.pages) - 1

    for i, page in enumerate(reader.pages):
        if i == pagina_alvo:
            # Cria overlay com a palavra-chave
            overlay_buffer = criar_overlay_palavra_chave(
                palavra_chave,
                float(page.mediabox.width),
                float(page.mediabox.height)
            )
            overlay_reader = PdfReader(overlay_buffer)
            page.merge_page(overlay_reader.pages[0])

        writer.add_page(page)

    # Nome único para o arquivo
    unique_id = str(uuid.uuid4())[:8]
    nome_arquivo = f"termo_{unique_id}.pdf"
    caminho = os.path.join(OUTPUT_DIR, nome_arquivo)

    with open(caminho, "wb") as f:
        writer.write(f)

    return nome_arquivo


@app.get("/")
def health_check():
    return {"status": "online", "servico": "Gerador PDF João Filho Advocacia"}


@app.post("/gerar-pdf")
def gerar_pdf(cliente: ClienteRequest):
    """
    Endpoint principal chamado pelo LeadHub.
    Recebe dados do cliente, gera PDF com palavra-chave e retorna link para download.
    """
    try:
        palavra_chave = gerar_palavra_chave()
        nome_arquivo = gerar_pdf_personalizado(palavra_chave, cliente.nome)

        # URL base da sua API (configure a variável de ambiente BASE_URL no Railway)
        base_url = os.getenv("BASE_URL", "https://web-production-24b0a.up.railway.app/git")
        link_download = f"{base_url}/download/{nome_arquivo}"

        return {
            "sucesso": True,
            "cliente": cliente.nome,
            "palavra_chave": palavra_chave,
            "link_download": link_download,
            "mensagem": f"PDF gerado com sucesso para {cliente.nome}"
        }

    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao gerar PDF: {str(e)}")


@app.get("/download/{nome_arquivo}")
def download_pdf(nome_arquivo: str):
    """Endpoint para download do PDF gerado"""
    # Segurança: impede path traversal
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
    """Remove PDFs com mais de 24h (pode ser chamado via cron ou manualmente)"""
    removidos = 0
    agora = datetime.now()
    for arquivo in os.listdir(OUTPUT_DIR):
        caminho = os.path.join(OUTPUT_DIR, arquivo)
        criado_em = datetime.fromtimestamp(os.path.getctime(caminho))
        if agora - criado_em > timedelta(hours=24):
            os.remove(caminho)
            removidos += 1
    return {"removidos": removidos}
