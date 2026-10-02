"""Testes da integracao de e-mail: segredo, montagem, modo teste, lote e templates."""

from __future__ import annotations

import smtplib
from collections.abc import Mapping
from email.message import EmailMessage

import pytest
from flask import Flask

from luftbase import Anexo, PlataformaLuft, ResultadoEnvio, enviar_email
from luftbase.configuracao import Ambiente, resolver_caminhos_vault
from luftbase.infraestrutura.cofre.credenciais import CredencialEmail, Segredo, SegurancaSmtp
from luftbase.infraestrutura.cofre.servico import CarregadorCredenciais
from luftbase.infraestrutura.fabrica import FabricaInfraestruturaMemoria, RecursosInfraestrutura
from luftbase.integracoes.email import (
    CID_LOGO,
    ImagemEmbutida,
    ServicoEmail,
    TransporteMemoria,
    TransporteSmtp,
    gerar_texto_de_html,
    normalizar_enderecos_email,
)
from luftbase.integracoes.email import servico as modulo_servico
from luftbase.nucleo.excecoes import EmailNaoConfigurado, ErroCredencial, ErroEmail

# --------------------------------------------------------------------------- segredo


class ProvedorFalso:
    def __init__(self, dados: Mapping[str, object]) -> None:
        self.dados = dados

    def validar_acesso(self) -> None:
        return None

    def ler_segredo(self, caminho: str) -> Mapping[str, object]:
        return self.dados


def _segredo(**alteracoes: object) -> dict[str, object]:
    dados: dict[str, object] = {
        "host": "smtp.gmail.com",
        "porta": "587",
        "seguranca": "starttls",
        "usuario": "conta@luftlogistics.com",
        "senha": "senha-de-app",
        "remetente": "planejamento@luftlogistics.com",
        "nome_remetente": "Luft Logistics",
        "redirecionar_para": "",
    }
    dados.update(alteracoes)
    return dados


def _carregar(**alteracoes: object) -> CredencialEmail:
    return CarregadorCredenciais(ProvedorFalso(_segredo(**alteracoes))).carregar_email("x")


def test_caminho_do_segredo_segue_o_ambiente() -> None:
    caminhos = resolver_caminhos_vault(ambiente="prod", sistema_id=3)

    assert caminhos.email == "luft/producao/integracoes/email"


def test_carrega_segredo_valido_sem_expor_senha() -> None:
    credencial = _carregar()

    assert credencial.host == "smtp.gmail.com"
    assert credencial.porta == 587
    assert credencial.seguranca is SegurancaSmtp.STARTTLS
    assert credencial.remetente == "planejamento@luftlogistics.com"
    assert credencial.redirecionar_para == ()
    assert "senha-de-app" not in repr(credencial)


def test_remetente_ausente_usa_o_usuario() -> None:
    assert _carregar(remetente="").remetente == "conta@luftlogistics.com"


def test_redirecionamento_aceita_texto_ou_lista() -> None:
    texto = _carregar(redirecionar_para="a@luft.com; b@luft.com,A@luft.com")
    lista = _carregar(redirecionar_para=["a@luft.com", "b@luft.com"])

    assert texto.redirecionar_para == ("a@luft.com", "b@luft.com")
    assert lista.redirecionar_para == ("a@luft.com", "b@luft.com")


@pytest.mark.parametrize(
    ("campo", "valor", "trecho"),
    [
        ("seguranca", "nenhuma", "seguranca"),
        ("porta", "abc", "porta"),
        ("porta", "70000", "porta"),
        ("tipo", "sendgrid", "SMTP"),
        ("host", "", "host"),
        ("senha", "", "senha"),
        ("remetente", "sem-arroba", "invalido"),
        ("redirecionar_para", "ok@luft.com; quebrado", "invalido"),
        ("redirecionar_para", 42, "texto ou lista"),
    ],
)
def test_rejeita_segredo_invalido(campo: str, valor: object, trecho: str) -> None:
    with pytest.raises(ErroCredencial, match=trecho):
        _carregar(**{campo: valor})


def test_normaliza_enderecos_sem_repetir() -> None:
    assert normalizar_enderecos_email("a@x.com, b@x.com ;A@X.COM") == ("a@x.com", "b@x.com")
    with pytest.raises(ErroEmail):
        normalizar_enderecos_email(["a@x.com", "a@x"])


# --------------------------------------------------------------------------- servico


def _credencial(redirecionar_para: tuple[str, ...] = ()) -> CredencialEmail:
    return CredencialEmail(
        host="smtp.gmail.com",
        porta=587,
        seguranca=SegurancaSmtp.STARTTLS,
        usuario="conta@luftlogistics.com",
        senha=Segredo("senha-de-app"),
        remetente="planejamento@luftlogistics.com",
        nome_remetente="Luft Logistics",
        redirecionar_para=redirecionar_para,
    )


def _servico(
    transporte: TransporteMemoria | None = None,
    *,
    redirecionar_para: tuple[str, ...] = (),
    auditados: list[ResultadoEnvio] | None = None,
    nome_sistema: str | None = "Luft ConnectAir",
) -> ServicoEmail:
    return ServicoEmail(
        _credencial(redirecionar_para),
        ambiente=Ambiente.PRODUCAO,
        nome_sistema=nome_sistema,
        transporte=transporte or TransporteMemoria(),
        auditor=auditados.append if auditados is not None else None,
    )


def test_sem_segredo_o_servico_informa_e_recusa() -> None:
    servico = ServicoEmail(None, ambiente=Ambiente.DESENVOLVIMENTO)

    assert servico.configurado is False
    with pytest.raises(EmailNaoConfigurado, match="integracoes/email"):
        servico.enviar("a@luft.com", "Assunto", texto="corpo")


@pytest.mark.parametrize(
    ("argumentos", "trecho"),
    [
        ({"para": [], "assunto": "A", "texto": "t"}, "destinatario"),
        ({"para": "a@luft.com", "assunto": "  ", "texto": "t"}, "assunto"),
        ({"para": "a@luft.com", "assunto": "A\r\nBcc: x@y.com", "texto": "t"}, "quebras"),
        ({"para": "a@luft.com", "assunto": "A"}, "template"),
        ({"para": "a@luft.com", "assunto": "A", "html": "<p/>", "template": "x"}, "nunca"),
    ],
)
def test_rejeita_uso_invalido(argumentos: dict[str, object], trecho: str) -> None:
    with pytest.raises(ErroEmail, match=trecho):
        _servico().preparar(**argumentos)  # type: ignore[arg-type]


def test_envio_monta_cabecalhos_e_copia_oculta_fora_do_cabecalho() -> None:
    transporte = TransporteMemoria()
    auditados: list[ResultadoEnvio] = []

    resultado = _servico(transporte, auditados=auditados).enviar(
        "filial@luft.com",
        "Planejamento",
        html="<p>Olá <b>filial</b></p>",
        copia="gestor@luft.com",
        copia_oculta="arquivo@luft.com",
        anexos=[Anexo("plano.xlsx", b"conteudo", "application/vnd.ms-excel")],
    )

    mensagem, destinos = transporte.enviadas[0]
    assert resultado.sucesso is True
    assert destinos == ("filial@luft.com", "gestor@luft.com", "arquivo@luft.com")
    assert mensagem["To"] == "filial@luft.com"
    assert mensagem["Cc"] == "gestor@luft.com"
    assert mensagem["Bcc"] is None
    assert mensagem["From"] == "Luft ConnectAir <planejamento@luftlogistics.com>"
    assert mensagem["Message-ID"].endswith("@luftlogistics.com>")
    assert "Olá filial" in mensagem.get_body(("plain",)).get_content()  # type: ignore[union-attr]
    assert [parte.get_filename() for parte in mensagem.iter_attachments()] == ["plano.xlsx"]
    assert auditados == [resultado]


def test_nome_do_remetente_prioriza_parametro_depois_sistema_depois_vault() -> None:
    sem_sistema = _servico(nome_sistema=None).preparar("a@luft.com", "A", texto="t")
    com_parametro = _servico().preparar("a@luft.com", "A", texto="t", nome_remetente="Torre")

    assert sem_sistema.mensagem["From"].startswith("Luft Logistics <")
    assert com_parametro.mensagem["From"].startswith("Torre <")


def test_modo_teste_troca_destinos_e_marca_assunto() -> None:
    transporte = TransporteMemoria()
    servico = _servico(transporte, redirecionar_para=("qa@luft.com",))

    resultado = servico.enviar(
        "filial@luft.com", "Planejamento", texto="corpo", copia="gestor@luft.com"
    )

    mensagem, destinos = transporte.enviadas[0]
    assert servico.modo_teste is True
    assert destinos == ("qa@luft.com",)
    assert mensagem["To"] == "qa@luft.com"
    assert mensagem["Cc"] is None
    assert mensagem["Subject"] == "[TESTE] Planejamento"
    assert resultado.redirecionado is True
    assert resultado.destinatarios_originais == ("filial@luft.com", "gestor@luft.com")


def test_template_padrao_embute_logo_e_faixa_de_modo_teste() -> None:
    servico = _servico(redirecionar_para=("qa@luft.com",))

    envio = servico.preparar(
        "filial@luft.com",
        "Teste",
        template="luftbase/email/teste.html",
        contexto={"servidor": "smtp:587"},
    )

    html_parte = envio.mensagem.get_body(("html",))
    assert html_parte is not None
    html = html_parte.get_content()
    assert f"cid:{CID_LOGO}" in html
    assert "MODO TESTE" in html
    assert "filial@luft.com" in html
    assert "Luft ConnectAir" in html
    relacionados = [p for p in envio.mensagem.walk() if p.get("Content-ID") == f"<{CID_LOGO}>"]
    assert len(relacionados) == 1
    texto = envio.mensagem.get_body(("plain",))
    assert texto is not None and "MODO TESTE" in texto.get_content()


def test_imagem_propria_substitui_o_logo_padrao() -> None:
    envio = _servico().preparar(
        "a@luft.com",
        "A",
        html=f'<img src="cid:{CID_LOGO}">',
        imagens=[ImagemEmbutida(CID_LOGO, b"png-proprio")],
    )

    partes = [p for p in envio.mensagem.walk() if p.get("Content-ID") == f"<{CID_LOGO}>"]
    assert [p.get_content() for p in partes] == [b"png-proprio"]


def test_html_sem_logo_nao_anexa_imagem() -> None:
    envio = _servico().preparar("a@luft.com", "A", html="<p>simples</p>")

    assert not [p for p in envio.mensagem.walk() if p.get("Content-ID")]


def test_lote_usa_uma_unica_conexao_e_continua_apos_recusa() -> None:
    class ConexaoSeletiva(TransporteMemoria):
        pass

    transporte = ConexaoSeletiva(recusar=("parcial@luft.com",))
    servico = _servico(transporte)
    envios = [
        servico.preparar("a@luft.com", "1", texto="t"),
        servico.preparar(["b@luft.com", "parcial@luft.com"], "2", texto="t"),
    ]

    resultados = servico.enviar_lote(envios)

    assert transporte.conexoes == 1
    assert [r.sucesso for r in resultados] == [True, True]
    assert resultados[1].recusados == ("parcial@luft.com",)


def test_falha_de_autenticacao_marca_todo_o_lote_sem_excecao() -> None:
    auditados: list[ResultadoEnvio] = []
    transporte = TransporteMemoria(
        falha_conexao=smtplib.SMTPAuthenticationError(535, b"bad credentials")
    )
    servico = _servico(transporte, auditados=auditados)
    envios = [servico.preparar(f"{i}@luft.com", "A", texto="t") for i in range(3)]

    resultados = servico.enviar_lote(envios)

    assert [r.sucesso for r in resultados] == [False, False, False]
    assert resultados[0].erro == "Usuario ou senha do e-mail recusados pelo servidor SMTP."
    assert len(auditados) == 3


def test_destinatarios_recusados_nao_interrompem_o_lote() -> None:
    class ConexaoRecusaPrimeiro:
        def __init__(self) -> None:
            self.chamadas = 0

        def enviar(self, mensagem: EmailMessage, destinatarios: object) -> dict[str, object]:
            self.chamadas += 1
            if self.chamadas == 1:
                raise smtplib.SMTPRecipientsRefused({"a@luft.com": (550, b"x")})
            return {}

    class TransporteRecusa:
        def conectar(self):  # type: ignore[no-untyped-def]
            from contextlib import nullcontext

            return nullcontext(ConexaoRecusaPrimeiro())

    servico = ServicoEmail(_credencial(), ambiente=Ambiente.PRODUCAO, transporte=TransporteRecusa())
    envios = [servico.preparar(f"{c}@luft.com", "A", texto="t") for c in "ab"]

    resultados = servico.enviar_lote(envios)

    assert [r.sucesso for r in resultados] == [False, True]
    assert "recusados" in (resultados[0].erro or "")


def test_falha_do_auditor_nao_afeta_o_envio() -> None:
    def auditor_quebrado(_: ResultadoEnvio) -> None:
        raise RuntimeError("banco fora")

    servico = ServicoEmail(
        _credencial(),
        ambiente=Ambiente.PRODUCAO,
        transporte=TransporteMemoria(),
        auditor=auditor_quebrado,
    )

    assert servico.enviar("a@luft.com", "A", texto="t").sucesso is True


# --------------------------------------------------------------------------- transporte


class SmtpFalso:
    instancias: list[SmtpFalso] = []

    def __init__(self, host: str, porta: int, **opcoes: object) -> None:
        self.host, self.porta, self.opcoes = host, porta, opcoes
        self.chamadas: list[str] = []
        self.login_recebido: tuple[str, str] | None = None
        type(self).instancias.append(self)

    def __enter__(self) -> SmtpFalso:
        return self

    def __exit__(self, *_: object) -> None:
        self.chamadas.append("quit")

    def ehlo(self) -> None:
        self.chamadas.append("ehlo")

    def starttls(self, context: object) -> None:
        self.chamadas.append("starttls")

    def login(self, usuario: str, senha: str) -> None:
        self.login_recebido = (usuario, senha)

    def send_message(self, mensagem: EmailMessage, to_addrs: list[str]) -> dict[str, object]:
        self.chamadas.append(f"send:{','.join(to_addrs)}")
        return {}


def test_transporte_smtp_negocia_starttls_e_autentica() -> None:
    SmtpFalso.instancias = []
    transporte = TransporteSmtp(_credencial(), construtor_smtp=SmtpFalso)  # type: ignore[arg-type]

    with transporte.conectar() as conexao:
        conexao.enviar(EmailMessage(), ["a@luft.com"])

    servidor = SmtpFalso.instancias[0]
    assert (servidor.host, servidor.porta) == ("smtp.gmail.com", 587)
    assert servidor.chamadas == ["ehlo", "starttls", "ehlo", "send:a@luft.com", "quit"]
    assert servidor.login_recebido == ("conta@luftlogistics.com", "senha-de-app")


def test_transporte_smtp_usa_ssl_implicito_quando_configurado() -> None:
    SmtpFalso.instancias = []
    credencial = _credencial()
    credencial_ssl = CredencialEmail(
        host=credencial.host,
        porta=465,
        seguranca=SegurancaSmtp.SSL,
        usuario=credencial.usuario,
        senha=credencial.senha,
        remetente=credencial.remetente,
    )
    transporte = TransporteSmtp(credencial_ssl, construtor_smtp_ssl=SmtpFalso)  # type: ignore[arg-type]

    with transporte.conectar():
        pass

    servidor = SmtpFalso.instancias[0]
    assert "context" in servidor.opcoes
    assert "starttls" not in servidor.chamadas


# --------------------------------------------------------------------------- texto


def test_texto_alternativo_preserva_blocos_e_links() -> None:
    html = (
        "<html><head><style>p{color:red}</style><title>x</title></head><body>"
        "<h1>Título</h1><p>Linha&nbsp;um</p>"
        '<p><a href="https://luft.com/x">Abrir</a></p>'
        "<table><tr><td>CTCs</td><td>12</td></tr></table></body></html>"
    )

    texto = gerar_texto_de_html(html)

    assert texto.splitlines()[0] == "Título"
    assert "Linha um" in texto
    assert "Abrir (https://luft.com/x)" in texto
    assert "CTCs 12" in texto
    assert "color" not in texto


def test_texto_alternativo_ignora_quebras_do_codigo_fonte() -> None:
    html = "<table>\n  <tr>\n    <td>\n      Peso\n    </td>\n    <td>12 kg</td>\n  </tr>\n</table>"

    assert gerar_texto_de_html(html) == "Peso 12 kg"


# --------------------------------------------------------------------------- plataforma


def _app_com_email(
    monkeypatch: pytest.MonkeyPatch, credencial: CredencialEmail | None
) -> tuple[Flask, TransporteMemoria]:
    transporte = TransporteMemoria()
    monkeypatch.setattr(modulo_servico, "TransporteSmtp", lambda _credencial: transporte)

    class Fabrica:
        def criar(self, configuracao, caminhos):  # type: ignore[no-untyped-def]
            base = FabricaInfraestruturaMemoria().criar(configuracao, caminhos)
            return RecursosInfraestrutura(
                bancos=base.bancos,
                armazenamento_sessoes=base.armazenamento_sessoes,
                chave_assinatura_sessao=base.chave_assinatura_sessao,
                identificador_vault=base.identificador_vault,
                credencial_email=credencial,
            )

    app = Flask(__name__)
    app.config.update(
        LUFT_SISTEMA_ID=0,
        LUFT_AMBIENTE="desenvolvimento",
        LUFT_VAULT_ENDERECO="http://vault:8200",
        LUFT_LDAP_SERVIDOR="ad.luft",
        LUFT_LDAP_DOMINIO="luftfarma",
    )
    PlataformaLuft(Fabrica()).inicializar(app)  # type: ignore[arg-type]
    return app, transporte


def test_plataforma_libera_o_email_e_renderiza_pelo_jinja_da_aplicacao(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, transporte = _app_com_email(monkeypatch, _credencial(("qa@luft.com",)))

    with app.test_request_context("/"):
        resultado = enviar_email(
            "filial@luft.com",
            "Teste",
            template="luftbase/email/teste.html",
            contexto={"servidor": "smtp"},
        )

    assert resultado.sucesso is True
    mensagem, destinos = transporte.enviadas[0]
    assert destinos == ("qa@luft.com",)
    html = mensagem.get_body(("html",))
    assert html is not None and "Integração de e-mail funcionando" in html.get_content()


def test_plataforma_sobe_sem_o_segredo_de_email(monkeypatch: pytest.MonkeyPatch) -> None:
    app, _ = _app_com_email(monkeypatch, None)

    with app.app_context():
        from luftbase import obter_luftbase

        assert obter_luftbase().email.configurado is False
