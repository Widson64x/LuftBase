"""Testes da auditoria HTTP e de dominio sem PostgreSQL real."""

from contextlib import contextmanager

import pytest

from luftbase.nucleo.excecoes import ErroAuditoria
from luftbase.observabilidade.modelos import (
    EventoAcessoHttp,
    EventoDominio,
    SeveridadeAuditoria,
)
from luftbase.observabilidade.repositorio import RepositorioAuditoria
from luftbase.observabilidade.servico import ServicoAuditoria


class ResultadoFalso:
    def __init__(self, identidade: int) -> None:
        self.identidade = identidade

    def scalar_one(self) -> int:
        return self.identidade


class SessaoFalsa:
    def __init__(self) -> None:
        self.declaracoes: list[object] = []

    def execute(self, declaracao: object) -> ResultadoFalso:
        self.declaracoes.append(declaracao)
        return ResultadoFalso(99)


class BancoFalso:
    def __init__(self) -> None:
        self.sessao = SessaoFalsa()

    @contextmanager
    def unidade_trabalho(self):  # type: ignore[no-untyped-def]
        yield self.sessao


def test_repositorio_separa_acesso_e_evento_e_redige_dados() -> None:
    banco = BancoFalso()
    repositorio = RepositorioAuditoria(banco)  # type: ignore[arg-type]

    id_acesso = repositorio.registrar_acesso(
        2,
        EventoAcessoHttp(
            rota="/budget",
            metodo="GET",
            status_http=200,
            duracao_ms=15,
            id_correlacao="correlacao-123",
        ),
    )
    id_evento = repositorio.registrar_evento(
        2,
        EventoDominio(
            acao="ATUALIZAR",
            recurso="BUDGET",
            descricao="Atualizou budget",
            dados_novos={"senha": "nao-vazar", "valor": 10},
            severidade=SeveridadeAuditoria.MEDIA,
        ),
    )

    assert id_acesso == id_evento == 99
    parametros_acesso = banco.sessao.declaracoes[0].compile().params  # type: ignore[attr-defined]
    parametros_vinculo = banco.sessao.declaracoes[1].compile().params  # type: ignore[attr-defined]
    parametros_detalhe = banco.sessao.declaracoes[3].compile().params  # type: ignore[attr-defined]
    parametros_alteracao = banco.sessao.declaracoes[4].compile().params  # type: ignore[attr-defined]
    assert parametros_acesso["status_http"] == 200
    assert parametros_vinculo["id_log"] == 99
    assert "dados_novos_json" not in parametros_detalhe
    assert "nao-vazar" not in str(parametros_alteracao)
    assert "[REDACTED]" in str(parametros_alteracao)


def test_evento_de_dominio_exige_sistema_valido() -> None:
    servico = ServicoAuditoria(-1, RepositorioAuditoria(BancoFalso()))  # type: ignore[arg-type]

    with pytest.raises(ErroAuditoria, match="sistema valido"):
        servico.registrar_evento(EventoDominio("CRIAR", "ITEM", "Criou item"))


def test_servico_auditoria_quatro_camadas_grava_em_todas(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from luftbase.observabilidade.arquivo_fisico import LoggerFisicoAuditoria
    from luftbase.observabilidade.buffer_temp import BufferLogsTemporarios

    banco = BancoFalso()
    repositorio = RepositorioAuditoria(banco)  # type: ignore[arg-type]
    logger_fisico = LoggerFisicoAuditoria(diretorio_logs=tmp_path, nome_arquivo="teste.log")
    buffer_temp = BufferLogsTemporarios(capacidade_maxima=50)

    servico = ServicoAuditoria(
        1,
        repositorio,
        logger_fisico=logger_fisico,
        buffer_temp=buffer_temp,
    )

    # 1. Teste de Acesso
    id_acesso = servico.registrar_acesso(
        EventoAcessoHttp(
            rota="/home",
            metodo="GET",
            status_http=200,
            duracao_ms=25,
            id_correlacao="corr-abc",
            codigo_usuario=2280,
            login_usuario="widson.araujo",
            codigo_grupo=6,
            nome_grupo="DBA",
            ip_origem="127.0.0.1",
            user_agent="Mozilla/5.0 Test",
        )
    )
    assert id_acesso == 99

    # 2. Teste de Evento
    id_evento = servico.registrar_evento(
        EventoDominio(
            acao="EDITAR",
            recurso="USUARIO",
            descricao="Alterou permissao do usuario",
            codigo_usuario=2280,
            login_usuario="widson.araujo",
            codigo_grupo=6,
            nome_grupo="DBA",
            severidade=SeveridadeAuditoria.MEDIA,
            id_correlacao="corr-abc",
        )
    )
    assert id_evento == 99

    # 3. Validar Buffer Temporario (Logs Temp)
    logs_temp = servico.obter_logs_temporarios()
    assert len(logs_temp) == 2
    assert logs_temp[0].acao == "EDITAR"
    assert logs_temp[0].login_usuario == "widson.araujo"
    assert logs_temp[0].codigo_grupo == 6
    assert logs_temp[0].nome_grupo == "DBA"
    assert logs_temp[1].acao == "HTTP_GET"
    assert servico.obter_logs_temporarios(codigo_usuario=2280) == logs_temp
    assert servico.obter_logs_temporarios(codigo_grupo=6) == logs_temp
    assert servico.obter_logs_temporarios(codigo_grupo=99) == []

    # 4. Validar Arquivo Fisico (.log)
    arquivo_log = tmp_path / "teste.log"
    assert arquivo_log.exists()
    conteudo_log = arquivo_log.read_text(encoding="utf-8")
    assert "/home" in conteudo_log
    assert "widson.araujo" in conteudo_log
    assert "Alterou permissao do usuario" in conteudo_log

    # 5. Métodos de conveniência
    servico.info("Mensagem info de teste", login_usuario="widson.araujo")
    servico.aviso("Mensagem aviso de teste")
    servico.erro("Mensagem de erro de teste", ValueError("falha simulada"))
    assert servico.buffer_temp.contagem() == 6  # type: ignore[union-attr]


def test_handler_rotativo_resiliente_tolera_bloqueio_windows(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import logging

    from luftbase.observabilidade.arquivo_fisico import HandlerRotativoResiliente

    arquivo = tmp_path / "rotativo.log"
    handler = HandlerRotativoResiliente(
        str(arquivo),
        when="midnight",
        interval=1,
        backupCount=5,
        encoding="utf-8",
        delay=True,
    )
    logger = logging.getLogger("teste.rotativo.resiliente")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    logger.info("Linha anterior ao rollover")
    assert arquivo.exists()
    assert "Linha anterior ao rollover" in arquivo.read_text(encoding="utf-8")

    # Simula falha de rename (WinError 32)
    def rotate_com_erro(origem: str, destino: str) -> None:
        raise PermissionError("[WinError 32] O arquivo ja esta sendo usado por outro processo")

    monkeypatch.setattr(handler, "rotate", rotate_com_erro)

    # Forca necessidade de rollover
    handler.rolloverAt = 0

    # Executa doRollover (nao deve lancar excecao e deve usar fallback copytruncate)
    handler.doRollover()

    # rolloverAt deve ter sido avancado para o futuro
    assert handler.rolloverAt > 0

    # Continua gravando normalmente
    logger.info("Linha posterior ao rollover")
    assert "Linha posterior ao rollover" in arquivo.read_text(encoding="utf-8")
    handler.close()


def test_raiz_temporaria_grava_arquivo_sanitizado_por_processo(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from luftbase.observabilidade.buffer_temp import BufferLogsTemporarios

    buffer = BufferLogsTemporarios(capacidade_maxima=50, diretorio_arquivos=tmp_path)
    buffer.adicionar(
        "INFO",
        "Alteracao recebida",
        detalhes={"senha": "segredo-que-nao-pode-vazar", "campo": "status"},
    )

    assert buffer.caminho_arquivo is not None
    assert buffer.caminho_arquivo.exists()
    conteudo = buffer.caminho_arquivo.read_text(encoding="utf-8")
    assert "segredo-que-nao-pode-vazar" not in conteudo
    assert "[REDACTED]" in conteudo


def test_leitura_de_log_fisico_e_limitada_a_arquivos_conhecidos(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from luftbase.observabilidade.arquivo_fisico import LoggerFisicoAuditoria

    logger = LoggerFisicoAuditoria(diretorio_logs=tmp_path, nome_arquivo="auditoria.log")
    logger.info("Linha segura", correlacao="corr-12345678", login="operador")

    arquivos = logger.listar_arquivos()
    registros = logger.ler_recentes(limite=10)

    assert arquivos[0]["nome"] == "auditoria.log"
    assert registros[0].mensagem == "Linha segura"
    assert registros[0].login_usuario == "operador"
    assert logger.ler_recentes(arquivo="../auditoria.log") == []
