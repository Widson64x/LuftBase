"""Logs fisicos: o diario de mensagens do LuftBase (luftbase.log) e a leitura dele e do log da aplicacao."""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Flask

from luftbase import PlataformaLuft
from luftbase.autorizacao import PermissaoLuftBase
from luftbase.configuracao import ConfiguracaoLuftBase
from luftbase.identidade import UsuarioAutenticado
from luftbase.infraestrutura.fabrica import FabricaInfraestruturaMemoria
from luftbase.integracoes.email.enderecos import mascarar_endereco, resumir_enderecos
from luftbase.observabilidade import arquivo_fisico
from luftbase.observabilidade.arquivo_fisico import (
    LoggerFisicoAuditoria,
    ler_log,
    listar_arquivos_log,
    rotulo_de_origem,
)
from luftbase.observabilidade.sanitizacao import mascarar_texto
from luftbase.observabilidade.servico import ServicoAuditoria


def _fisico(tmp_path: Path, nome: str = "luftbase.log") -> LoggerFisicoAuditoria:
    logger = LoggerFisicoAuditoria(tmp_path, nome)
    logger.capturar_plataforma()
    return logger


def _linhas(tmp_path: Path, nome: str = "luftbase.log") -> list[str]:
    return (tmp_path / nome).read_text(encoding="utf-8").splitlines()


# ---------------------------------------------------------------- captura dos modulos


def test_mensagens_dos_modulos_caem_no_arquivo_com_a_area_de_origem(tmp_path: Path) -> None:
    _fisico(tmp_path)

    logging.getLogger("luftbase.integracoes.email.servico").info("E-mail de teste enviado")
    logging.getLogger("luftbase.autorizacao.aviso_acesso").warning("Aviso de acesso incompleto")

    linhas = _linhas(tmp_path)
    assert any("[INFO]" in x and "[EMAIL] - E-mail de teste enviado" in x for x in linhas)
    assert any("[WARNING]" in x and "[ACESSO] - Aviso de acesso incompleto" in x for x in linhas)


def test_usuario_e_correlacao_da_requisicao_entram_na_linha(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fisico(tmp_path)
    monkeypatch.setattr(arquivo_fisico, "_contexto_da_requisicao", lambda: ("corr-123", "maria.souza"))

    logging.getLogger("luftbase.conteudo.servicos").info("Publicacao #5 publicada")

    assert any("[corr-123] [maria.souza] [COMUNICADOS] - Publicacao #5 publicada" in x for x in _linhas(tmp_path))


def test_fora_de_requisicao_o_login_e_sistema() -> None:
    assert arquivo_fisico._contexto_da_requisicao() == (None, None)  # noqa: SLF001


def test_rotulos_de_origem() -> None:
    assert rotulo_de_origem("luftbase.integracoes.email.servico") == "EMAIL"
    assert rotulo_de_origem("luftbase.email") == "EMAIL"
    assert rotulo_de_origem("luftbase.identidade.servico") == "IDENTIDADE"
    assert rotulo_de_origem("luftbase.observabilidade.alertas") == "ALERTAS"
    assert rotulo_de_origem("luftbase.coisa.nova") == "COISA"
    assert rotulo_de_origem("outra.biblioteca") == "LUFTBASE"


def test_recriar_a_plataforma_nao_duplica_as_linhas(tmp_path: Path) -> None:
    _fisico(tmp_path)
    _fisico(tmp_path)  # o mesmo processo cria outra plataforma (ex.: reload)

    logging.getLogger("luftbase.teste").info("Uma vez so")

    assert sum("Uma vez so" in linha for linha in _linhas(tmp_path)) == 1


# ---------------------------------------------------------------- seguranca


def test_excecao_vira_resumo_sem_a_mensagem_bruta(tmp_path: Path) -> None:
    _fisico(tmp_path)
    log = logging.getLogger("luftbase.infraestrutura.teste")

    try:
        try:
            raise ConnectionError("senha=SEGREDO123 host=interno")
        except ConnectionError as causa:
            raise ValueError("dados do cliente: 123.456.789-00") from causa
    except ValueError:
        log.exception("Falha ao gravar")

    texto = "\n".join(_linhas(tmp_path))
    assert "Falha ao gravar | erro: ValueError (causa: ConnectionError)" in texto
    assert "SEGREDO123" not in texto and "123.456.789-00" not in texto
    assert "Traceback" not in texto  # a pilha inteira nao vai para o arquivo
    assert len(_linhas(tmp_path)) == 1  # uma mensagem, uma linha


@pytest.mark.parametrize(
    "texto",
    [
        "login com senha=abc123 falhou",
        "token: eyJhbGciOi.sdkjfh e mais",
        "conectando em postgresql://usuario:senha-forte@host/banco",
        "vault hvs.CAESIabcdefghijkl",
        "Authorization: Bearer abc.def.ghi",
    ],
)
def test_segredos_em_texto_livre_sao_mascarados(tmp_path: Path, texto: str) -> None:
    _fisico(tmp_path)

    logging.getLogger("luftbase.teste").warning(texto)

    conteudo = "\n".join(_linhas(tmp_path))
    for segredo in ("abc123", "eyJhbGciOi", "senha-forte", "CAESIabcdefghijkl", "abc.def.ghi"):
        assert segredo not in conteudo
    assert "[REDACTED]" in conteudo


def test_mascarar_texto_junta_linhas_e_limita_o_tamanho() -> None:
    assert mascarar_texto("primeira\n\nsegunda") == "primeira ↵ segunda"
    assert mascarar_texto("x" * 50, maximo=10).endswith("...[TRUNCADO]")


def test_enderecos_de_email_sao_mascarados_no_log() -> None:
    assert mascarar_endereco("fulano@luftlogistics.com") == "f***@luftlogistics.com"
    assert resumir_enderecos(["a@x.com", "b@x.com", "c@x.com"], limite=2) == "a***@x.com, b***@x.com +1"


# ---------------------------------------------------------------- eventos e erros tecnicos


def test_evento_de_dominio_vira_uma_frase_e_o_erro_mostra_so_o_tipo(tmp_path: Path) -> None:
    from luftbase.observabilidade import EventoDominio, SeveridadeAuditoria

    fisico = _fisico(tmp_path)
    fisico.registrar_evento(
        EventoDominio("PUBLICAR", "PUBLICACAO", "Publicação #12 publicada.", id_recurso="12", login_usuario="widson")
    )
    fisico.registrar_evento(
        EventoDominio(
            "ERRO",
            "SISTEMA",
            "Falha ao importar",
            severidade=SeveridadeAuditoria.ALTA,
            traceback="Traceback (most recent call last):\n  ...\nValueError: dados sensiveis aqui",
        )
    )

    linhas = _linhas(tmp_path)
    assert "[widson] [PUBLICAR/PUBLICACAO] - Publicação #12 publicada." in linhas[0]
    assert "(id 12)" not in linhas[0]  # o id ja esta na frase
    assert "[ERROR]" in linhas[1] and linhas[1].endswith("Falha ao importar | erro: ValueError")
    assert "dados sensiveis" not in linhas[1]


def test_evento_tecnico_e_legivel(tmp_path: Path) -> None:
    fisico = _fisico(tmp_path)

    fisico.registrar_tecnico(
        "ERROR",
        "erro_500",
        id_correlacao="abc",
        tipo_erro="ProgrammingError",
        dados={
            "metodo": "GET",
            "rota": "/publicacoes/painel",
            "cadeia": ["sqlalchemy.exc.ProgrammingError", "psycopg.errors.UndefinedColumn"],
            "origem": ["cursor.py:117 execute"],
            "pilha": ["web.py:1 a", "repositorios.py:1098 listar"],
        },
    )

    linha = _linhas(tmp_path)[0]
    assert "[abc]" in linha
    assert "Erro interno do servidor em GET /publicacoes/painel: ProgrammingError" in linha
    assert "causa: UndefinedColumn" in linha
    assert "origem: cursor.py:117 execute" in linha
    assert "{" not in linha  # nada de JSON cru


# ---------------------------------------------------------------- leitura


def test_leitor_entende_os_dois_formatos_e_junta_as_pilhas(tmp_path: Path) -> None:
    (tmp_path / "application.log").write_text(
        "2026-10-21 15:49:37 | INFO     | Luft-Workspace.App | Aplicação iniciada no ambiente homologacao.\n"
        "2026-10-21 15:50:15 | ERROR    | App                | Exception on /painel [GET]\n"
        "Traceback (most recent call last):\n"
        '  File "x.py", line 1, in f\n'
        "ValueError: falhou\n"
        "2026-10-21 15:51:00 | WARNING  | Luft-Workspace.Svc | Atencao\n",
        encoding="utf-8",
    )
    (tmp_path / "luftbase.log").write_text(
        "[2026-10-21 16:00:00] [INFO] [abc] [maria] [EMAIL] - E-mail enviado\n", encoding="utf-8"
    )

    aplicacao = ler_log(tmp_path, "application.log", limite=10)
    plataforma = ler_log(tmp_path, "luftbase.log", limite=10)

    assert [r.nivel for r in aplicacao] == ["WARNING", "ERROR", "INFO"]  # mais novo primeiro
    erro = aplicacao[1]
    assert erro.acao == "App" and erro.data_hora == "2026-10-21 15:50:15"
    assert erro.mensagem.splitlines()[0] == "Exception on /painel [GET]"
    assert "ValueError: falhou" in erro.mensagem  # a pilha ficou junto, em uma entrada so
    assert (plataforma[0].login_usuario, plataforma[0].id_correlacao, plataforma[0].acao) == ("maria", "abc", "EMAIL")


def test_filtros_de_nivel_e_termo(tmp_path: Path) -> None:
    (tmp_path / "luftbase.log").write_text(
        "[2026-10-21 16:00:00] [INFO] [-] [maria] [EMAIL] - enviado para a***@x.com\n"
        "[2026-10-21 16:01:00] [ERROR] [-] [SISTEMA] [EMAIL] - falha no envio\n",
        encoding="utf-8",
    )

    assert [r.nivel for r in ler_log(tmp_path, "luftbase.log", nivel="error")] == ["ERROR"]
    assert [r.login_usuario for r in ler_log(tmp_path, "luftbase.log", termo="MARIA")] == ["maria"]


def test_leitor_so_abre_arquivos_do_proprio_log(tmp_path: Path) -> None:
    (tmp_path / "luftbase.log").write_text("[2026-10-21 16:00:00] [INFO] [-] [-] [X] - a\n", encoding="utf-8")
    (tmp_path / "luftbase.log.2026-10-20").write_text("[2026-10-20 10:00:00] [INFO] [-] [-] [X] - antigo\n", encoding="utf-8")
    (tmp_path / "segredo.txt").write_text("nao pode\n", encoding="utf-8")

    assert {a["nome"] for a in listar_arquivos_log(tmp_path, "luftbase.log")} == {"luftbase.log", "luftbase.log.2026-10-20"}
    assert ler_log(tmp_path, "luftbase.log", arquivo="luftbase.log.2026-10-20")[0].mensagem == "antigo"
    assert ler_log(tmp_path, "luftbase.log", arquivo="segredo.txt") == []
    assert ler_log(tmp_path, "luftbase.log", arquivo="../luftbase.log") == []


def test_servico_expoe_as_duas_fontes(tmp_path: Path) -> None:
    fisico = LoggerFisicoAuditoria(tmp_path, "luftbase.log")
    fisico.info("do luftbase")
    servico = ServicoAuditoria(1, SimpleNamespace(), logger_fisico=fisico)  # type: ignore[arg-type]

    fontes = {f["id"]: f for f in servico.listar_fontes_logs()}
    assert fontes["luftbase"]["disponivel"] is True
    assert fontes["aplicacao"]["disponivel"] is False  # ainda nao ha application.log

    (tmp_path / "application.log").write_text("2026-10-21 10:00:00 | INFO     | App | da aplicacao\n", encoding="utf-8")
    assert servico.listar_fontes_logs()[1]["disponivel"] is True
    assert servico.obter_logs_fisicos(fonte="aplicacao")[0]["mensagem"] == "da aplicacao"
    assert servico.obter_logs_fisicos(fonte="luftbase")[0]["mensagem"] == "do luftbase"
    assert servico.obter_logs_fisicos(fonte="inexistente") == []


# ---------------------------------------------------------------- plataforma e rota


def _app_com_logs(tmp_path: Path) -> tuple[Flask, object]:
    app = Flask(__name__)
    app.config["LUFT_LOG_DIR"] = str(tmp_path)
    configuracao = ConfiguracaoLuftBase.de_mapeamento(
        {
            "LUFT_SISTEMA_ID": 0,
            "LUFT_AMBIENTE": "desenvolvimento",
            "LUFT_VAULT_ENDERECO": "http://vault.invalid:8200",
            "LUFT_LDAP_SERVIDOR": "ldap.invalid",
            "LUFT_LDAP_DOMINIO": "luft",
        }
    )
    estado = PlataformaLuft(FabricaInfraestruturaMemoria()).inicializar(app, configuracao)
    app.testing = True
    return app, estado


def test_a_subida_da_plataforma_fica_registrada(tmp_path: Path) -> None:
    from luftbase._versao import __version__

    _app_com_logs(tmp_path)

    subida = next(x for x in _linhas(tmp_path) if "iniciado para" in x)
    assert f"LuftBase {__version__} iniciado para" in subida
    assert "[PLATAFORMA]" in subida and "ambiente desenvolvimento" in subida
    assert "E-mail: nao configurado" in subida


def test_acesso_http_nao_vai_para_o_arquivo(tmp_path: Path) -> None:
    app, _estado = _app_com_logs(tmp_path)

    @app.route("/rota-qualquer")
    def rota() -> str:
        return "ok"

    app.test_client().get("/rota-qualquer")

    assert "/rota-qualquer" not in (tmp_path / "luftbase.log").read_text(encoding="utf-8")


def test_rota_de_logs_fisicos_lista_as_fontes_e_as_mensagens(tmp_path: Path) -> None:
    app, estado = _app_com_logs(tmp_path)
    cliente = app.test_client()
    usuario = UsuarioAutenticado(10, "operador", "Operador", "o@luft.com.br", 1, "Ops")
    with cliente.session_transaction() as sessao:
        sessao["_user_id"] = usuario.get_id()
        sessao["_fresh"] = True
        sessao["luftbase_usuario"] = usuario.como_dict()
        sessao["luftbase_preferencia_tema"] = {"tema": "luft", "modo": "SISTEMA"}
    estado.autorizacao.possui = lambda _u, chave, *_: chave in {  # type: ignore[attr-defined]
        PermissaoLuftBase.AUDITORIA_VISUALIZAR,
        PermissaoLuftBase.AUDITORIA_DADOS_SENSIVEIS_VISUALIZAR,
    }
    (tmp_path / "application.log").write_text("2026-10-21 10:00:00 | INFO     | App | Aplicação no ar\n", encoding="utf-8")

    luftbase = cliente.get("/configuracoes/api/auditoria/fisicos").get_json()["data"]
    aplicacao = cliente.get("/configuracoes/api/auditoria/fisicos?fonte=aplicacao").get_json()["data"]

    assert luftbase["fonte"] == "luftbase"
    assert any("iniciado para" in item["mensagem"] for item in luftbase["itens"])
    assert [f["id"] for f in luftbase["fontes"]] == ["luftbase", "aplicacao"]
    assert aplicacao["itens"][0]["mensagem"] == "Aplicação no ar"
    assert aplicacao["arquivos"][0]["nome"] == "application.log"
    assert cliente.get("/configuracoes/api/auditoria/fisicos?arquivo=../x").get_json()["data"]["itens"] == []


# ---------------------------------------------------------------- e-mails


def _servico_de_email_da_plataforma(eventos: list[object]):  # type: ignore[no-untyped-def]
    """O ServicoEmail que a plataforma monta (com o auditor real), mas com transporte em memoria."""

    from luftbase.configuracao import Ambiente
    from luftbase.infraestrutura.cofre.credenciais import CredencialEmail, Segredo, SegurancaSmtp
    from luftbase.integracoes.email import TransporteMemoria

    credencial = CredencialEmail(
        host="smtp.invalid",
        porta=587,
        seguranca=SegurancaSmtp.STARTTLS,
        usuario="conta@luftlogistics.com",
        senha=Segredo("senha-de-app"),
        remetente="planejamento@luftlogistics.com",
        nome_remetente="Luft Logistics",
        redirecionar_para=(),
    )
    configuracao = SimpleNamespace(
        aplicacao=SimpleNamespace(ambiente=Ambiente.PRODUCAO, nome="Luft-Workspace", versao="1", link=None)
    )
    auditoria = SimpleNamespace(registrar_evento=eventos.append)
    servico = PlataformaLuft._criar_email(  # noqa: SLF001
        configuracao,  # type: ignore[arg-type]
        SimpleNamespace(credencial_email=credencial),  # type: ignore[arg-type]
        auditoria,  # type: ignore[arg-type]
    )
    servico._transporte = TransporteMemoria()  # noqa: SLF001
    return servico


def test_email_enviado_diz_para_quantas_pessoas_sem_expor_o_endereco_inteiro() -> None:
    eventos: list[object] = []
    servico = _servico_de_email_da_plataforma(eventos)

    servico.enviar(["ana.lima@luftlogistics.com", "bruno@luftlogistics.com"], "Seu acesso foi liberado", html="<p>oi</p>")

    (evento,) = eventos
    assert evento.acao == "EMAIL_ENVIADO"  # type: ignore[attr-defined]
    assert evento.descricao == (  # type: ignore[attr-defined]
        "E-mail 'Seu acesso foi liberado' enviado para 2 destinatario(s): "
        "a***@luftlogistics.com, b***@luftlogistics.com."
    )
    assert "ana.lima" not in evento.descricao  # type: ignore[attr-defined]


def test_email_recusado_vira_aviso_com_o_motivo() -> None:
    from luftbase.integracoes.email import TransporteMemoria

    eventos: list[object] = []
    servico = _servico_de_email_da_plataforma(eventos)

    class Recusa(TransporteMemoria):
        def conectar(self):  # type: ignore[no-untyped-def]
            raise OSError("sem rede")

    servico._transporte = Recusa()  # noqa: SLF001
    servico.enviar("ana@luftlogistics.com", "Alerta", html="<p>x</p>")

    (evento,) = eventos
    assert evento.acao == "EMAIL_FALHA"  # type: ignore[attr-defined]
    assert "NAO enviado para 1 destinatario(s): a***@luftlogistics.com" in evento.descricao  # type: ignore[attr-defined]
    assert "Motivo:" in evento.descricao  # type: ignore[attr-defined]
