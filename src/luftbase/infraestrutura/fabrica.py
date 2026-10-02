"""Composicao padrao dos adaptadores externos do LuftBase."""

from __future__ import annotations

import hashlib
import logging
import sqlite3
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from luftbase.configuracao.caminhos_vault import CaminhosVault
from luftbase.configuracao.modelos import ConfiguracaoLuftBase
from luftbase.identidade.sessoes import ArmazenamentoSessoes
from luftbase.infraestrutura.banco.catalogo import CatalogoBancos, FabricaCatalogoBancos
from luftbase.infraestrutura.cofre.cliente_hvac import ClienteVaultHvac
from luftbase.infraestrutura.cofre.credenciais import (
    CredencialBanco,
    CredencialEmail,
    Segredo,
    TipoBanco,
)
from luftbase.infraestrutura.cofre.criptografia import DesprotetorFernet
from luftbase.infraestrutura.cofre.servico import CarregadorCredenciais
from luftbase.infraestrutura.redis import FabricaClienteRedis
from luftbase.nucleo.excecoes import SegredoNaoEncontrado


class ArmazenamentoSessoesMemoria:
    """Armazenamento em memoria de um unico processo, para testes e cache sem Redis.

    O TTL e respeitado: sem isso, a revisao de autorizacao guardada aqui nunca expiraria e um
    processo nao enxergaria concessoes feitas por outro (por exemplo, o Workspace concedendo
    acesso a um sistema que ja estava em execucao).
    """

    def __init__(self, relogio: Callable[[], float] = time.monotonic) -> None:
        self._dados: dict[str, tuple[bytes, float]] = {}
        self._relogio = relogio

    def obter(self, chave: str) -> bytes | None:
        item = self._dados.get(chave)
        if item is None:
            return None
        valor, expira_em = item
        if self._relogio() >= expira_em:
            self._dados.pop(chave, None)
            return None
        return valor

    def salvar(self, chave: str, valor: bytes, ttl_segundos: int) -> None:
        self._dados[chave] = (valor, self._relogio() + max(ttl_segundos, 1))

    def remover(self, chave: str) -> None:
        self._dados.pop(chave, None)

    def verificar_saude(self) -> bool:
        return True


class ArmazenamentoSessoesDevLocal:
    """Armazenamento persistente local (SQLite) para desenvolvimento sem Redis.

    Garante que as sessoes sobrevivam aos reloads automaticos do Flask durante o
    desenvolvimento, evitando deslogar o desenvolvedor a cada mudanca de codigo.
    """

    def __init__(self, caminho_banco: str | Path | None = None) -> None:
        if caminho_banco is None:
            caminho_banco = Path(tempfile.gettempdir()) / "luft_sessoes_dev.sqlite"
        self._caminho = str(caminho_banco)
        self._inicializar()

    def _inicializar(self) -> None:
        with sqlite3.connect(self._caminho, timeout=10.0) as con:
            con.execute(
                "CREATE TABLE IF NOT EXISTS sessoes ("
                "chave TEXT PRIMARY KEY, "
                "valor BLOB NOT NULL, "
                "expira_em REAL NOT NULL"
                ")"
            )
            con.commit()

    def obter(self, chave: str) -> bytes | None:
        try:
            with sqlite3.connect(self._caminho, timeout=10.0) as con:
                linha = con.execute(
                    "SELECT valor, expira_em FROM sessoes WHERE chave = ?",
                    (chave,),
                ).fetchone()
                if linha is None:
                    return None
                valor, expira_em = linha
                if float(expira_em) < time.time():
                    con.execute("DELETE FROM sessoes WHERE chave = ?", (chave,))
                    con.commit()
                    return None
                return bytes(valor)
        except Exception:
            return None

    def salvar(self, chave: str, valor: bytes, ttl_segundos: int) -> None:
        expira_em = time.time() + max(ttl_segundos, 1)
        try:
            with sqlite3.connect(self._caminho, timeout=10.0) as con:
                con.execute(
                    "INSERT INTO sessoes (chave, valor, expira_em) VALUES (?, ?, ?) "
                    "ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor, "
                    "expira_em=excluded.expira_em",
                    (chave, valor, expira_em),
                )
                con.commit()
        except Exception:
            pass

    def remover(self, chave: str) -> None:
        try:
            with sqlite3.connect(self._caminho, timeout=10.0) as con:
                con.execute("DELETE FROM sessoes WHERE chave = ?", (chave,))
                con.commit()
        except Exception:
            pass

    def verificar_saude(self) -> bool:
        return True


@dataclass(frozen=True, slots=True)
class RecursosInfraestrutura:
    """Recursos externos pertencentes exclusivamente a uma aplicacao Flask."""

    bancos: CatalogoBancos
    armazenamento_sessoes: ArmazenamentoSessoes
    chave_assinatura_sessao: Segredo
    identificador_vault: str | None = None
    credencial_email: CredencialEmail | None = None


class FabricaInfraestrutura(Protocol):
    """Contrato substituivel para compor recursos durante a inicializacao."""

    def criar(
        self,
        configuracao: ConfiguracaoLuftBase,
        caminhos: CaminhosVault,
    ) -> RecursosInfraestrutura:
        """Cria os recursos externos da aplicacao."""


class FabricaInfraestruturaPadrao:
    """Monta Vault, credenciais e bancos sem estado global compartilhado."""

    def __init__(
        self,
        fabrica_bancos: FabricaCatalogoBancos | None = None,
        fabrica_redis: FabricaClienteRedis | None = None,
    ) -> None:
        self._fabrica_bancos = fabrica_bancos or FabricaCatalogoBancos()
        self._fabrica_redis = fabrica_redis or FabricaClienteRedis()

    def criar(
        self,
        configuracao: ConfiguracaoLuftBase,
        caminhos: CaminhosVault,
    ) -> RecursosInfraestrutura:
        """Resolve os segredos apenas durante a inicializacao explicita."""

        configuracao.validar_para_inicializacao()
        token_protegido = configuracao.cofre.token_protegido
        token_acesso = configuracao.cofre.token_acesso
        assert token_protegido is not None  # Validado pelo contrato acima.
        assert token_acesso is not None

        token_vault = DesprotetorFernet(token_acesso).revelar(token_protegido)
        provedor = ClienteVaultHvac(
            configuracao.cofre.endereco,
            Segredo(token_vault),
        )
        credenciais = CarregadorCredenciais(provedor)
        credencial_diretorio = self._carregar_diretorio(credenciais, caminhos)
        credencial_aplicacao = credenciais.carregar_aplicacao_postgresql(
            caminhos.postgresql,
            caminhos.postgresql_conexoes,
            sistema_id_esperado=configuracao.aplicacao.sistema_id,
        )
        credencial_postgresql = credencial_aplicacao.banco
        armazenamento_sessoes: ArmazenamentoSessoes
        chave_assinatura_sessao: Segredo
        try:
            credencial_redis = credenciais.carregar_redis(caminhos.sessoes_redis)
            armazenamento_sessoes = self._fabrica_redis.criar(credencial_redis)
            chave_assinatura_sessao = credencial_redis.chave_assinatura_sessao
            bancos = self._fabrica_bancos.criar(
                credencial_diretorio,
                credencial_postgresql,
            )
        except SegredoNaoEncontrado:
            # Sessoes no PostgreSQL (core) sao o padrao; Redis e opcional.
            logging.getLogger("luftbase").info(
                "Sessoes no PostgreSQL (core); Redis nao configurado em %s.",
                caminhos.sessoes_redis,
            )
            bancos = self._fabrica_bancos.criar(
                credencial_diretorio,
                credencial_postgresql,
            )
            if hasattr(bancos, "core") and bancos.core is not None:
                from luftbase.identidade.armazenamento_postgresql import (
                    ArmazenamentoSessoesPostgreSQL,
                )

                armazenamento_sessoes = ArmazenamentoSessoesPostgreSQL(bancos.core)
            else:
                armazenamento_sessoes = ArmazenamentoSessoesDevLocal()
            semente = (
                configuracao.cofre.token_acesso
                or "luft_sessao_chave_assinatura_padrao_desenvolvimento_32chars"
            ).encode("utf-8")
            chave_assinatura_sessao = Segredo(hashlib.sha256(semente).hexdigest())

        return RecursosInfraestrutura(
            bancos=bancos,
            armazenamento_sessoes=armazenamento_sessoes,
            chave_assinatura_sessao=chave_assinatura_sessao,
            identificador_vault=credencial_aplicacao.identificador,
            credencial_email=self._carregar_email(credenciais, configuracao, caminhos),
        )

    @staticmethod
    def _carregar_diretorio(
        credenciais: CarregadorCredenciais,
        caminhos: CaminhosVault,
    ) -> CredencialBanco:
        """Conexao nomeada do diretorio; o caminho antigo so serve de reserva, com aviso."""

        try:
            return credenciais.carregar_banco(caminhos.sqlserver_diretorio, TipoBanco.SQLSERVER)
        except SegredoNaoEncontrado:
            if not caminhos.sqlserver_legado:
                raise
        try:
            credencial = credenciais.carregar_banco(caminhos.sqlserver_legado, TipoBanco.SQLSERVER)
        except SegredoNaoEncontrado as erro:
            raise SegredoNaoEncontrado(
                "A conexao do diretorio de usuarios nao existe no Vault. Crie "
                f"{caminhos.sqlserver_diretorio!r} (ou ajuste LUFT_VAULT_CONEXAO_DIRETORIO)."
            ) from erro
        logging.getLogger("luftbase").warning(
            "Diretorio lido do caminho antigo %s; migre para %s.",
            caminhos.sqlserver_legado,
            caminhos.sqlserver_diretorio,
        )
        return credencial

    @staticmethod
    def _carregar_email(
        credenciais: CarregadorCredenciais,
        configuracao: ConfiguracaoLuftBase,
        caminhos: CaminhosVault,
    ) -> CredencialEmail | None:
        """E-mail e opcional; um segredo presente porem invalido interrompe a inicializacao."""

        if not caminhos.email:
            return None
        try:
            return credenciais.carregar_email(caminhos.email)
        except SegredoNaoEncontrado:
            logging.getLogger("luftbase").info(
                "Segredo de e-mail ausente no Vault (%s) em ambiente %s. "
                "O envio de e-mail ficara indisponivel.",
                caminhos.email,
                configuracao.aplicacao.ambiente.value,
            )
            return None


class FabricaInfraestruturaMemoria:
    """Fabrica deterministica em memoria para testes sem conexoes externas."""

    def __init__(self, chave_assinatura: str = "s" * 64) -> None:
        self._chave_assinatura = chave_assinatura

    def criar(
        self,
        configuracao: ConfiguracaoLuftBase,
        caminhos: CaminhosVault,
    ) -> RecursosInfraestrutura:
        from typing import cast

        from sqlalchemy import Table, create_engine, insert
        from sqlalchemy.pool import StaticPool

        from luftbase.infraestrutura.banco.sessoes import BancoSQLAlchemy
        from luftbase.persistencia.core.seguranca import Sistema

        engine_memoria = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            execution_options={"schema_translate_map": {"core": None}},
        )
        tabela_sistema = cast(Table, Sistema.__table__)
        tabela_sistema.create(engine_memoria)
        with engine_memoria.begin() as conexao:
            conexao.execute(
                insert(Sistema).values(
                    id_sistema=configuracao.aplicacao.sistema_id,
                    nome_sistema=configuracao.aplicacao.nome
                    or f"Sistema {configuracao.aplicacao.sistema_id}",
                    descricao_sistema=configuracao.aplicacao.descricao,
                    ativo=True,
                    em_manutencao=False,
                )
            )

        banco_diretorio = BancoSQLAlchemy(
            "diretorio_sqlserver", engine_memoria, somente_leitura=True
        )
        banco_core = BancoSQLAlchemy("core_postgresql", engine_memoria)
        banco_app = BancoSQLAlchemy("aplicacao_postgresql", engine_memoria)
        catalogo = CatalogoBancos(banco_diretorio, banco_core, banco_app)

        return RecursosInfraestrutura(
            bancos=catalogo,
            armazenamento_sessoes=ArmazenamentoSessoesMemoria(),
            chave_assinatura_sessao=Segredo(self._chave_assinatura),
            identificador_vault=f"sistema-{configuracao.aplicacao.sistema_id}",
        )
