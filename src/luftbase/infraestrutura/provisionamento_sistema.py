"""Provisionamento de banco e Vault de um sistema novo, disparado pela tela do Workspace.

Faz o mesmo que `luftbase bootstrap` para um unico sistema: schema proprio, role com senha
SCRAM, privilegios no core e segredo `bancos/postgresql/sistemas/{id}` no Vault. Ambiente,
Vault, host e banco sao os do proprio Workspace; o operador informa apenas o token do Vault e
o usuario/senha administrativos, usados nesta operacao e nunca gravados.
"""

from __future__ import annotations

import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import URL, Engine, create_engine, text

from luftbase.configuracao.ambientes import Ambiente, normalizar_ambiente
from luftbase.configuracao.identificadores import validar_identificador_tecnico
from luftbase.infraestrutura.cofre.clonagem import sufixo_do_ambiente
from luftbase.infraestrutura.cofre.credenciais import Segredo
from luftbase.nucleo.excecoes import ErroConfiguracao

MOUNT_PADRAO = "secret"
_PADRAO_ROLE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


class ErroProvisionamento(Exception):
    """Falha controlada, com o campo do formulario que o operador precisa corrigir."""

    def __init__(self, mensagem: str, campo: str | None = None) -> None:
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.campo = campo


@dataclass(frozen=True, slots=True)
class CredenciaisOperador:
    """Credenciais informadas no modal; nunca aparecem em `repr` nem sao persistidas."""

    usuario_banco: str
    token_vault: Segredo = field(repr=False)
    senha_banco: Segredo = field(repr=False)


@dataclass(frozen=True, slots=True)
class DestinoProvisionamento:
    """Onde provisionar: os mesmos Vault, ambiente e banco que o Workspace usa."""

    ambiente: str
    namespace: str
    vault_url: str
    host: str
    porta: int
    banco: str
    sistema_referencia: int
    mount: str = MOUNT_PADRAO

    @property
    def raiz_sistemas(self) -> str:
        return f"{self.namespace}/{self.ambiente}/bancos/postgresql/sistemas"

    def como_dict(self) -> dict[str, object]:
        producao = normalizar_ambiente(self.ambiente) is Ambiente.PRODUCAO
        return {
            "ambiente": self.ambiente,
            # Sufixo das roles (vazio em producao): a tela mostra o nome real da role.
            "sufixo_role": "" if producao else sufixo_do_ambiente(self.ambiente),
            "vault": self.vault_url,
            "banco": f"{self.host}:{self.porta}/{self.banco}",
            "pasta_segredos": self.raiz_sistemas,
        }


@dataclass(frozen=True, slots=True)
class PlanoSistema:
    """Nomes derivados do cadastro, na mesma convencao do bootstrap."""

    sistema_id: int
    identificador: str
    esquema: str
    role: str
    ambiente: str = "producao"


def derivar_plano(
    sistema_id: int, nome: str, esquema: str, ambiente: str = "producao"
) -> PlanoSistema:
    """`Luft-ConnectAir` + `connectair` -> `luft-connectair` e `luft_connectair_app`.

    Roles pertencem ao cluster PostgreSQL inteiro, nao a um banco. Por isso fora da producao
    a role leva o sufixo do ambiente (`luft_connectair_hml_app`): sem ele, cadastrar o sistema
    em homologacao trocaria a senha da role de producao, que e a mesma.
    """

    slug = re.sub(r"[^a-z0-9]+", "-", nome.lower()).strip("-")
    if slug and not slug[0].isalpha():
        slug = f"sistema-{slug}"
    try:
        identificador = validar_identificador_tecnico(slug)
    except ErroConfiguracao as erro:
        raise ErroProvisionamento(
            f"Nao foi possivel derivar o identificador tecnico do nome: {erro}", "Nome"
        ) from erro
    ambiente_canonico = normalizar_ambiente(ambiente).value
    role = nome_da_role(esquema, ambiente_canonico)
    if not _PADRAO_ROLE.fullmatch(role):
        raise ErroProvisionamento(
            f"O schema gera a role '{role}', que passa de 63 caracteres. Use um schema menor.",
            "SchemaAplicacao",
        )
    return PlanoSistema(sistema_id, identificador, esquema, role, ambiente_canonico)


def nome_da_role(esquema: str, ambiente: str) -> str:
    """`connectair` em producao -> `luft_connectair_app`; em homologacao -> `..._hml_app`."""

    if normalizar_ambiente(ambiente) is Ambiente.PRODUCAO:
        return f"luft_{esquema}_app"
    return f"luft_{esquema}_{sufixo_do_ambiente(ambiente)}_app"


def destino_do_estado(estado: Any) -> DestinoProvisionamento:
    """Monta o destino a partir da configuracao e da engine do core do Workspace."""

    configuracao = estado.configuracao
    url = estado.bancos.core.engine.url
    return DestinoProvisionamento(
        ambiente=configuracao.aplicacao.ambiente.value,
        namespace=configuracao.cofre.namespace,
        vault_url=configuracao.cofre.endereco,
        host=str(url.host),
        porta=int(url.port or 5432),
        banco=str(url.database),
        sistema_referencia=configuracao.aplicacao.sistema_id,
    )


def _criar_cliente_vault(url: str, token: Segredo) -> Any:
    import hvac

    return hvac.Client(url=url, token=token.revelar(), timeout=10)


class ProvisionadorSistema:
    """Executa as etapas administrativas; cada metodo e seguro para repetir."""

    def __init__(
        self,
        destino: DestinoProvisionamento,
        credenciais: CredenciaisOperador,
        *,
        criar_cliente_vault: Callable[[str, Segredo], Any] | None = None,
        criar_engine: Callable[[URL], Engine] | None = None,
    ) -> None:
        self._destino = destino
        self._credenciais = credenciais
        self._criar_cliente_vault = criar_cliente_vault or _criar_cliente_vault
        self._criar_engine = criar_engine or (
            lambda url: create_engine(url, pool_pre_ping=True, poolclass=_pool_nulo())
        )
        self._vault: Any = None
        self._engine: Engine | None = None

    @property
    def ambiente(self) -> str:
        """Ambiente do destino; as roles levam o sufixo dele fora da producao."""

        return self._destino.ambiente

    # --- Verificacoes antes de qualquer escrita -------------------------------------------

    def verificar(self) -> None:
        """Confere token e usuario administrativo; nada e gravado."""

        try:
            autenticado = bool(self._cliente_vault().is_authenticated())
        except Exception as erro:
            raise ErroProvisionamento(
                f"Nao foi possivel contatar o Vault em {self._destino.vault_url}.",
                "TokenOperadorVault",
            ) from erro
        if not autenticado:
            raise ErroProvisionamento("O Vault recusou o token de operador.", "TokenOperadorVault")

        try:
            with self._engine_admin().connect() as conexao:
                pode_role, pode_schema = conexao.execute(
                    text(
                        "SELECT r.rolsuper OR r.rolcreaterole, "
                        "has_database_privilege(current_database(), 'CREATE') "
                        "FROM pg_roles r WHERE r.rolname = current_user"
                    )
                ).one()
        except ErroProvisionamento:
            raise
        except Exception as erro:
            raise ErroProvisionamento(
                "O PostgreSQL recusou o usuario ou a senha administrativa "
                f"({self._destino.host}:{self._destino.porta}/{self._destino.banco}).",
                "SenhaBanco",
            ) from erro
        if not pode_role or not pode_schema:
            raise ErroProvisionamento(
                f"O usuario '{self._credenciais.usuario_banco}' precisa poder criar roles e "
                f"schemas no banco '{self._destino.banco}' (superusuario ou CREATEROLE + CREATE).",
                "UsuarioBanco",
            )

    def alias_conexao(self) -> str:
        """Alias da conexao compartilhada, lido do segredo do proprio Workspace."""

        caminho = f"{self._destino.raiz_sistemas}/{self._destino.sistema_referencia}"
        try:
            dados = self._cliente_vault().secrets.kv.v2.read_secret_version(
                path=caminho, mount_point=self._destino.mount, raise_on_deleted_version=True
            )["data"]["data"]
        except Exception as erro:
            raise ErroProvisionamento(
                f"Nao foi possivel ler '{caminho}' com o token de operador.",
                "TokenOperadorVault",
            ) from erro
        alias = str(dados.get("conexao") or "").strip()
        if not alias:
            raise ErroProvisionamento(
                f"O segredo '{caminho}' nao informa a conexao compartilhada ('conexao')."
            )
        return alias

    def segredo_existe(self, sistema_id: int) -> bool:
        from hvac import exceptions as excecoes_vault

        try:
            self._cliente_vault().secrets.kv.v2.read_secret_metadata(
                path=f"{self._destino.raiz_sistemas}/{sistema_id}",
                mount_point=self._destino.mount,
            )
        except excecoes_vault.InvalidPath:
            return False
        return True

    # --- Escritas -------------------------------------------------------------------------

    def provisionar_banco(self, plano: PlanoSistema) -> tuple[Segredo, bool]:
        """Cria (ou reaproveita) schema e role, aplica senha nova e concede privilegios.

        Roda em autocommit, fora da transacao do core: as etapas sao idempotentes e nunca
        apagam nada, entao repetir o cadastro depois de uma falha e seguro.
        """

        from luftbase.cli.bootstrap import (
            _conceder_privilegios_aplicacao,
            provisionar_schema_sistema,
        )
        from luftbase.cli.manifesto import AplicacaoManifesto

        if plano.ambiente != self._destino.ambiente:
            raise ErroProvisionamento(
                f"O plano e do ambiente '{plano.ambiente}', mas o destino e "
                f"'{self._destino.ambiente}'."
            )
        if plano.role != nome_da_role(plano.esquema, plano.ambiente):
            # Fora da producao so se mexe em roles com o sufixo do ambiente; assim a senha de
            # uma role de producao nunca e trocada por engano.
            raise ErroProvisionamento(
                f"A role '{plano.role}' nao segue o nome do ambiente '{plano.ambiente}'."
            )
        senha = secrets.token_urlsafe(32)
        with self._engine_admin().connect() as conexao:
            conexao = conexao.execution_options(isolation_level="AUTOCOMMIT")
            existe_role = conexao.execute(
                text("SELECT 1 FROM pg_roles WHERE rolname = :nome"), {"nome": plano.role}
            ).first()
            citar = conexao.dialect.identifier_preparer.quote
            if existe_role is None:
                conexao.exec_driver_sql(f"CREATE ROLE {citar(plano.role)} WITH LOGIN")
            driver = conexao.connection.driver_connection
            verificador = driver.pgconn.encrypt_password(  # type: ignore[union-attr]
                senha.encode(), plano.role.encode(), b"scram-sha-256"
            ).decode()
            # O verificador SCRAM nao contem aspas; o escape so evita surpresas.
            literal = verificador.replace("'", "''")
            conexao.exec_driver_sql(
                f"ALTER ROLE {citar(plano.role)} WITH LOGIN PASSWORD '{literal}'"
            )
            criado = provisionar_schema_sistema(
                conexao,
                id_sistema=plano.sistema_id,
                schema_aplicacao=plano.esquema,
                usuario_role=plano.role,
            )
            _conceder_privilegios_aplicacao(
                conexao,
                AplicacaoManifesto(
                    sistema_id=plano.sistema_id,
                    identificador=plano.identificador,
                    esquema=plano.esquema,
                    usuario=plano.role,
                ),
            )
        return Segredo(senha), criado

    def gravar_segredo(
        self, plano: PlanoSistema, alias: str, senha: Segredo, *, substituir: bool = False
    ) -> str:
        """Grava `sistemas/{id}` com CAS 0: nunca sobrescreve um segredo existente.

        Com `substituir` cria uma nova versao (o KV v2 preserva as anteriores); so o comando
        de reprovisionamento usa isso, com confirmacao do operador.
        """

        caminho = f"{self._destino.raiz_sistemas}/{plano.sistema_id}"
        opcoes: dict[str, Any] = {} if substituir else {"cas": 0}
        self._cliente_vault().secrets.kv.v2.create_or_update_secret(
            path=caminho,
            mount_point=self._destino.mount,
            **opcoes,
            secret={
                "sistema_id": plano.sistema_id,
                "identificador": plano.identificador,
                "conexao": alias,
                "esquema": plano.esquema,
                "usuario": plano.role,
                "senha": senha.revelar(),
            },
        )
        return caminho

    def remover_segredo(self, sistema_id: int) -> None:
        """Compensacao quando o core nao confirma o cadastro depois do segredo gravado."""

        self._cliente_vault().secrets.kv.v2.delete_metadata_and_all_versions(
            path=f"{self._destino.raiz_sistemas}/{sistema_id}", mount_point=self._destino.mount
        )

    def encerrar(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None

    # --- Internos -------------------------------------------------------------------------

    def _cliente_vault(self) -> Any:
        if self._vault is None:
            self._vault = self._criar_cliente_vault(
                self._destino.vault_url, self._credenciais.token_vault
            )
        return self._vault

    def _engine_admin(self) -> Engine:
        if self._engine is None:
            self._engine = self._criar_engine(
                URL.create(
                    "postgresql+psycopg",
                    username=self._credenciais.usuario_banco,
                    password=self._credenciais.senha_banco.revelar(),
                    host=self._destino.host,
                    port=self._destino.porta,
                    database=self._destino.banco,
                    query={"sslmode": "prefer", "connect_timeout": "10"},
                )
            )
        return self._engine


def _pool_nulo() -> Any:
    # Conexao administrativa de uso unico: nada fica em pool depois da requisicao.
    from sqlalchemy.pool import NullPool

    return NullPool


__all__ = [
    "CredenciaisOperador",
    "DestinoProvisionamento",
    "ErroProvisionamento",
    "PlanoSistema",
    "ProvisionadorSistema",
    "derivar_plano",
    "destino_do_estado",
    "nome_da_role",
]
