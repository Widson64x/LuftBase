"""Envio de e-mail corporativo com a conta SMTP guardada no Vault."""

from luftbase.integracoes.email.enderecos import (
    normalizar_enderecos_email,
    validar_endereco_email,
)
from luftbase.integracoes.email.modelos import (
    Anexo,
    EnvioPreparado,
    ImagemEmbutida,
    ResultadoEnvio,
)
from luftbase.integracoes.email.servico import (
    CID_LOGO,
    ServicoEmail,
    enviar_email,
    renderizar_template_email,
)
from luftbase.integracoes.email.texto import gerar_texto_de_html
from luftbase.integracoes.email.transporte import (
    ConexaoEmail,
    TransporteEmail,
    TransporteMemoria,
    TransporteSmtp,
)

__all__ = [
    "CID_LOGO",
    "Anexo",
    "ConexaoEmail",
    "EnvioPreparado",
    "ImagemEmbutida",
    "ResultadoEnvio",
    "ServicoEmail",
    "TransporteEmail",
    "TransporteMemoria",
    "TransporteSmtp",
    "enviar_email",
    "gerar_texto_de_html",
    "normalizar_enderecos_email",
    "renderizar_template_email",
    "validar_endereco_email",
]
