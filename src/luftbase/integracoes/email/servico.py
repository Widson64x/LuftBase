"""Servico de e-mail liberado pela plataforma a partir do segredo do Vault."""

from __future__ import annotations

import logging
import smtplib
import ssl
from collections.abc import Callable, Iterable, Mapping, Sequence
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from functools import lru_cache
from importlib import resources

from luftbase.configuracao.ambientes import Ambiente
from luftbase.infraestrutura.cofre.credenciais import CredencialEmail
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
from luftbase.integracoes.email.texto import gerar_texto_de_html
from luftbase.integracoes.email.transporte import TransporteEmail, TransporteSmtp
from luftbase.nucleo.excecoes import EmailNaoConfigurado, ErroEmail
from luftbase.nucleo.tempo import agora_local

CID_LOGO = "luftbase-logo"
PREFIXO_TESTE = "[TESTE]"
NOME_REMETENTE_PADRAO = "Luft Logistics"

Renderizador = Callable[[str, Mapping[str, object]], str]
Auditor = Callable[[ResultadoEnvio], None]

_logger = logging.getLogger("luftbase.email")


@lru_cache(maxsize=1)
def _ler_logo_padrao() -> bytes:
    arquivo = resources.files("luftbase.interface").joinpath("static/img/email/luft-logo.png")
    return arquivo.read_bytes()


@lru_cache(maxsize=1)
def _ambiente_jinja_pacote():  # type: ignore[no-untyped-def]
    from jinja2 import Environment, PackageLoader, select_autoescape

    return Environment(
        loader=PackageLoader("luftbase.interface", "templates"),
        autoescape=select_autoescape(["html"]),
    )


def renderizar_template_email(template: str, contexto: Mapping[str, object]) -> str:
    """Usa o Jinja da aplicacao quando ha contexto Flask; senao, so os templates do LuftBase."""

    from flask import current_app, has_app_context, has_request_context, render_template

    if has_app_context():
        if has_request_context():
            return render_template(template, **contexto)
        # Comando de CLI (`flask alertas avaliar`...): ha app mas nao ha requisicao, e os context
        # processors do LuftBase leem a sessao. Uma requisicao de teste vazia basta e mantem os
        # templates da propria aplicacao disponiveis.
        with current_app.test_request_context():
            return render_template(template, **contexto)
    return str(_ambiente_jinja_pacote().get_template(template).render(**contexto))


def _texto_de_cabecalho(valor: str, campo: str) -> str:
    texto = valor.strip()
    if "\r" in texto or "\n" in texto:
        raise ErroEmail(f"O campo {campo!r} nao pode conter quebras de linha.")
    return texto


def _descrever_falha(erro: BaseException) -> str:
    """Mensagem segura para o usuario; respostas do servidor nao carregam a senha."""

    if isinstance(erro, smtplib.SMTPAuthenticationError):
        return "Usuario ou senha do e-mail recusados pelo servidor SMTP."
    if isinstance(erro, smtplib.SMTPRecipientsRefused):
        return "Todos os destinatarios foram recusados pelo servidor SMTP."
    if isinstance(erro, smtplib.SMTPSenderRefused):
        return "O servidor SMTP recusou o remetente."
    if isinstance(erro, smtplib.SMTPDataError):
        return f"O servidor SMTP recusou a mensagem (codigo {erro.smtp_code})."
    if isinstance(erro, smtplib.SMTPException):
        return f"Falha SMTP: {type(erro).__name__}."
    if isinstance(erro, ssl.SSLError):
        return "Falha na negociacao TLS com o servidor SMTP."
    if isinstance(erro, TimeoutError):
        return "Tempo esgotado ao comunicar com o servidor SMTP."
    if isinstance(erro, OSError):
        return "Nao foi possivel conectar ao servidor SMTP."
    return "Falha inesperada ao enviar o e-mail."


class ServicoEmail:
    """Monta, redireciona em modo teste, envia em lote e audita mensagens."""

    def __init__(
        self,
        credencial: CredencialEmail | None,
        *,
        ambiente: Ambiente,
        nome_sistema: str | None = None,
        transporte: TransporteEmail | None = None,
        renderizador: Renderizador | None = None,
        auditor: Auditor | None = None,
    ) -> None:
        self._credencial = credencial
        self._ambiente = ambiente
        self._nome_sistema = (nome_sistema or "").strip() or None
        self._transporte = transporte or (TransporteSmtp(credencial) if credencial else None)
        self._renderizador = renderizador or renderizar_template_email
        self._auditor = auditor

    @property
    def configurado(self) -> bool:
        """Indica se o segredo `integracoes/email` existe no ambiente."""

        return self._credencial is not None

    @property
    def destinos_teste(self) -> tuple[str, ...]:
        """Enderecos que recebem todo envio enquanto o modo teste estiver ativo."""

        return self._credencial.redirecionar_para if self._credencial else ()

    @property
    def modo_teste(self) -> bool:
        """Verdadeiro quando `redirecionar_para` esta preenchido no Vault."""

        return bool(self.destinos_teste)

    @property
    def remetente(self) -> str | None:
        """Endereco usado no cabecalho `From`."""

        return self._credencial.remetente if self._credencial else None

    def preparar(
        self,
        para: str | Iterable[str],
        assunto: str,
        *,
        template: str | None = None,
        contexto: Mapping[str, object] | None = None,
        html: str | None = None,
        texto: str | None = None,
        anexos: Sequence[Anexo] = (),
        imagens: Sequence[ImagemEmbutida] = (),
        copia: str | Iterable[str] = (),
        copia_oculta: str | Iterable[str] = (),
        responder_para: str | None = None,
        nome_remetente: str | None = None,
    ) -> EnvioPreparado:
        """Monta a mensagem sem abrir conexao; erros de uso geram `ErroEmail`."""

        credencial = self._credencial
        if credencial is None:
            raise EmailNaoConfigurado(
                "O e-mail nao esta configurado: o segredo 'integracoes/email' nao existe "
                f"no Vault do ambiente {self._ambiente.value}."
            )
        if template is not None and html is not None:
            raise ErroEmail("Informe `template` ou `html`, nunca os dois.")
        if template is None and html is None and texto is None:
            raise ErroEmail("A mensagem precisa de `template`, `html` ou `texto`.")

        assunto_limpo = _texto_de_cabecalho(assunto, "assunto")
        if not assunto_limpo:
            raise ErroEmail("O assunto do e-mail e obrigatorio.")

        principais = normalizar_enderecos_email(para)
        em_copia = normalizar_enderecos_email(copia)
        ocultos = normalizar_enderecos_email(copia_oculta)
        originais = tuple(dict.fromkeys((*principais, *em_copia, *ocultos)))
        if not originais:
            raise ErroEmail("Informe ao menos um destinatario.")

        redirecionado = bool(credencial.redirecionar_para)
        if redirecionado:
            principais, em_copia = credencial.redirecionar_para, ()
            destinatarios = credencial.redirecionar_para
            if not assunto_limpo.startswith(PREFIXO_TESTE):
                assunto_limpo = f"{PREFIXO_TESTE} {assunto_limpo}"
        else:
            destinatarios = originais

        if template is not None:
            html = self._renderizador(
                template,
                {
                    **(contexto or {}),
                    "luft_email": self._contexto_padrao(assunto_limpo, redirecionado, originais),
                },
            )
        if texto is None and html is not None:
            texto = gerar_texto_de_html(html)

        remetente_nome = _texto_de_cabecalho(
            nome_remetente
            or self._nome_sistema
            or credencial.nome_remetente
            or NOME_REMETENTE_PADRAO,
            "nome_remetente",
        )
        mensagem = EmailMessage()
        mensagem["Subject"] = assunto_limpo
        mensagem["From"] = formataddr((remetente_nome, credencial.remetente))
        mensagem["To"] = ", ".join(principais)
        if em_copia:
            mensagem["Cc"] = ", ".join(em_copia)
        if responder_para:
            mensagem["Reply-To"] = validar_endereco_email(responder_para)
        mensagem["Date"] = formatdate(localtime=True)
        mensagem["Message-ID"] = make_msgid(domain=credencial.remetente.rpartition("@")[2])
        mensagem.set_content(texto or "")

        if html is not None:
            mensagem.add_alternative(html, subtype="html")
            self._embutir_imagens(mensagem, html, imagens)

        for anexo in anexos:
            tipo, _, subtipo = anexo.tipo_mime.partition("/")
            mensagem.add_attachment(
                anexo.conteudo,
                maintype=tipo or "application",
                subtype=subtipo or "octet-stream",
                filename=anexo.nome,
            )

        return EnvioPreparado(
            assunto=assunto_limpo,
            destinatarios=destinatarios,
            destinatarios_originais=originais,
            redirecionado=redirecionado,
            anexos=tuple(anexo.nome for anexo in anexos),
            mensagem=mensagem,
        )

    def enviar(
        self,
        para: str | Iterable[str],
        assunto: str,
        *,
        template: str | None = None,
        contexto: Mapping[str, object] | None = None,
        html: str | None = None,
        texto: str | None = None,
        anexos: Sequence[Anexo] = (),
        imagens: Sequence[ImagemEmbutida] = (),
        copia: str | Iterable[str] = (),
        copia_oculta: str | Iterable[str] = (),
        responder_para: str | None = None,
        nome_remetente: str | None = None,
    ) -> ResultadoEnvio:
        """Prepara e entrega uma unica mensagem."""

        envio = self.preparar(
            para,
            assunto,
            template=template,
            contexto=contexto,
            html=html,
            texto=texto,
            anexos=anexos,
            imagens=imagens,
            copia=copia,
            copia_oculta=copia_oculta,
            responder_para=responder_para,
            nome_remetente=nome_remetente,
        )
        return self.enviar_lote([envio])[0]

    def enviar_lote(self, envios: Sequence[EnvioPreparado]) -> list[ResultadoEnvio]:
        """Entrega varias mensagens na mesma sessao SMTP, uma falha nao interrompe as demais.

        Se a conexao cair ou nao puder ser aberta, as mensagens restantes sao marcadas
        como falhas com o motivo. Nenhuma excecao de entrega chega ao chamador.
        """

        if not envios:
            return []
        if self._transporte is None:
            raise EmailNaoConfigurado("O e-mail nao esta configurado neste ambiente.")

        resultados: list[ResultadoEnvio] = []
        try:
            with self._transporte.conectar() as conexao:
                for envio in envios:
                    try:
                        recusados = conexao.enviar(envio.mensagem, envio.destinatarios)
                    except (
                        smtplib.SMTPRecipientsRefused,
                        smtplib.SMTPSenderRefused,
                        smtplib.SMTPDataError,
                    ) as erro:
                        self._registrar_falha_tecnica(erro)
                        resultados.append(self._resultado(envio, erro=_descrever_falha(erro)))
                        continue
                    resultados.append(self._resultado(envio, recusados=tuple(sorted(recusados))))
        except Exception as erro:
            self._registrar_falha_tecnica(erro)
            motivo = _descrever_falha(erro)
            resultados.extend(
                self._resultado(envio, erro=motivo) for envio in envios[len(resultados) :]
            )

        for resultado in resultados:
            self._auditar(resultado)
        return resultados

    def _contexto_padrao(
        self,
        assunto: str,
        redirecionado: bool,
        originais: tuple[str, ...],
    ) -> dict[str, object]:
        return {
            "assunto": assunto,
            "sistema": self._nome_sistema or NOME_REMETENTE_PADRAO,
            "ambiente": self._ambiente.value,
            "cid_logo": CID_LOGO,
            "modo_teste": redirecionado,
            "destinatarios_reais": originais if redirecionado else (),
            "gerado_em": agora_local().strftime("%d/%m/%Y %H:%M"),
            "ano": agora_local().year,
        }

    @staticmethod
    def _embutir_imagens(
        mensagem: EmailMessage,
        html: str,
        imagens: Sequence[ImagemEmbutida],
    ) -> None:
        todas = list(imagens)
        # O logo so e anexado quando o HTML o usa, para nao pesar e-mails sem cabecalho.
        if f"cid:{CID_LOGO}" in html and all(imagem.cid != CID_LOGO for imagem in todas):
            todas.append(ImagemEmbutida(CID_LOGO, _ler_logo_padrao(), "image/png"))
        if not todas:
            return
        parte_html = mensagem.get_body(preferencelist=("html",))
        if not isinstance(parte_html, EmailMessage):
            raise ErroEmail("Nao foi possivel localizar a parte HTML da mensagem.")
        for imagem in todas:
            tipo, _, subtipo = imagem.tipo_mime.partition("/")
            parte_html.add_related(
                imagem.conteudo,
                maintype=tipo or "image",
                subtype=subtipo or "png",
                cid=f"<{imagem.cid}>",
            )

    @staticmethod
    def _resultado(
        envio: EnvioPreparado,
        *,
        erro: str | None = None,
        recusados: tuple[str, ...] = (),
    ) -> ResultadoEnvio:
        return ResultadoEnvio(
            sucesso=erro is None,
            assunto=envio.assunto,
            destinatarios=envio.destinatarios,
            destinatarios_originais=envio.destinatarios_originais,
            redirecionado=envio.redirecionado,
            erro=erro,
            recusados=recusados,
        )

    @staticmethod
    def _registrar_falha_tecnica(erro: BaseException) -> None:
        # Somente o tipo e o codigo: a resposta bruta do servidor pode ecoar dados da conta.
        codigo = getattr(erro, "smtp_code", None)
        _logger.warning("Falha no envio de e-mail: tipo=%s codigo=%s", type(erro).__name__, codigo)

    def _auditar(self, resultado: ResultadoEnvio) -> None:
        if self._auditor is None:
            return
        try:
            self._auditor(resultado)
        except Exception:
            # A mensagem ja saiu; falhar aqui faria a aplicacao reenviar em duplicidade.
            _logger.warning("Nao foi possivel auditar o envio de e-mail.", exc_info=True)


def enviar_email(
    para: str | Iterable[str],
    assunto: str,
    *,
    template: str | None = None,
    contexto: Mapping[str, object] | None = None,
    html: str | None = None,
    texto: str | None = None,
    anexos: Sequence[Anexo] = (),
    imagens: Sequence[ImagemEmbutida] = (),
    copia: str | Iterable[str] = (),
    copia_oculta: str | Iterable[str] = (),
    responder_para: str | None = None,
    nome_remetente: str | None = None,
) -> ResultadoEnvio:
    """Envia pelo servico da aplicacao Flask atual (`obter_luftbase().email`)."""

    from luftbase.plataforma import obter_luftbase

    return obter_luftbase().email.enviar(
        para,
        assunto,
        template=template,
        contexto=contexto,
        html=html,
        texto=texto,
        anexos=anexos,
        imagens=imagens,
        copia=copia,
        copia_oculta=copia_oculta,
        responder_para=responder_para,
        nome_remetente=nome_remetente,
    )
