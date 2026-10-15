"""Sessao do operador na CLI: token do Vault, usuario administrativo do PostgreSQL e destino do core.

Os segredos sao pedidos no terminal sem eco, usados so durante o comando e nunca gravados,
registrados nem aceitos por argumento.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import click

from luftbase.cli.vault import (
    _criar_cliente_hvac_operador,
    _solicitar_segredo,
    _usuario_administrativo,
)
from luftbase.configuracao.ambientes import Ambiente, normalizar_ambiente
from luftbase.infraestrutura.cadastro_sistema import (
    ErroCadastroSistema,
    descobrir_destino_core,
)
from luftbase.infraestrutura.cofre.credenciais import Segredo
from luftbase.infraestrutura.provisionamento_sistema import (
    CredenciaisOperador,
    DestinoProvisionamento,
    ErroProvisionamento,
    ProvisionadorSistema,
)
from luftbase.nucleo.excecoes import ErroConfiguracao

VAULT_URL_PADRAO = "http://172.16.200.80:8200"
AMBIENTES_DA_CLI = ("desenvolvimento", "homologacao")


@dataclass(frozen=True, slots=True)
class SessaoOperador:
    """Provisionador ja verificado e o destino do core onde ele atua."""

    provisionador: ProvisionadorSistema
    destino: DestinoProvisionamento
    alias_conexao: str
    usuario_banco: str = ""
    senha_banco: Segredo | None = field(default=None, repr=False)
    token_vault: Segredo | None = field(default=None, repr=False)


def _rotulo_senha(usuario: str, servidor: str, ambiente: str) -> str:
    """Fora do desenvolvimento o banco e remoto: a dica evita digitar a senha do PostgreSQL local."""

    dica = (
        "" if ambiente == "desenvolvimento" else " (do servidor acima, nao a do PostgreSQL local)"
    )
    return f"Senha de {usuario} em {servidor}{dica}"


def normalizar_ambiente_da_cli(valor: str) -> str:
    """Aceita so desenvolvimento e homologacao: producao se cadastra pelo Workspace."""

    try:
        ambiente = normalizar_ambiente(valor)
    except ErroConfiguracao as erro:
        raise click.UsageError(str(erro)) from erro
    if ambiente is Ambiente.PRODUCAO:
        raise click.UsageError(
            "Este comando nao opera em producao. Cadastre sistemas de producao pelo Luft-Workspace."
        )
    return ambiente.value


def abrir_sessao_operador(
    *,
    ambiente: str,
    vault_url: str,
    vault_mount: str,
    namespace: str,
    usuario_banco: str | None,
    banco_host: str | None = None,
    banco_porta: int | None = None,
    banco_nome: str | None = None,
    exigir_alias: bool = True,
) -> SessaoOperador:
    """Pede as credenciais, acha o core no Vault e confere token e usuario antes de qualquer escrita."""

    token = _solicitar_segredo(f"Token de operador do Vault ({vault_url})")
    cliente: Any = _criar_cliente_hvac_operador(vault_url, token, vault_mount)
    try:
        destino = descobrir_destino_core(
            cliente,
            ambiente=ambiente,
            namespace=namespace,
            vault_url=vault_url,
            mount=vault_mount,
        )
    except ErroCadastroSistema as falha:
        if not (banco_host and banco_porta and banco_nome):
            raise click.ClickException(falha.mensagem) from falha
        destino = DestinoProvisionamento(
            ambiente=ambiente,
            namespace=namespace,
            vault_url=vault_url,
            host=banco_host,
            porta=banco_porta,
            banco=banco_nome,
            sistema_referencia=0,
            mount=vault_mount,
        )
    if banco_host or banco_porta or banco_nome:
        destino = DestinoProvisionamento(
            ambiente=destino.ambiente,
            namespace=destino.namespace,
            vault_url=destino.vault_url,
            host=banco_host or destino.host,
            porta=banco_porta or destino.porta,
            banco=banco_nome or destino.banco,
            sistema_referencia=destino.sistema_referencia,
            mount=destino.mount,
        )

    # O servidor aparece antes do pedido: este e o banco do ambiente, nao o PostgreSQL local.
    servidor = f"{destino.host}:{destino.porta}/{destino.banco}"
    click.echo(f"Banco do ambiente {ambiente}: {servidor}")
    usuario = _usuario_administrativo(usuario_banco, rotulo=f"de {servidor}")
    senha = _solicitar_segredo(_rotulo_senha(usuario, servidor, ambiente))

    provisionador = ProvisionadorSistema(
        destino,
        CredenciaisOperador(usuario, Segredo(token), Segredo(senha)),
        criar_cliente_vault=lambda _url, _token: cliente,
    )
    try:
        provisionador.verificar()
        alias = provisionador.alias_conexao() if exigir_alias else ""
    except ErroProvisionamento as falha:
        provisionador.encerrar()
        raise click.ClickException(f"Nada foi gravado. {falha.mensagem}") from falha
    return SessaoOperador(provisionador, destino, alias, usuario, Segredo(senha), Segredo(token))


def engine_do_operador(destino: DestinoProvisionamento, usuario: str, senha: Segredo) -> Any:
    """Engine do core com o usuario administrativo informado; sem pool, para uso unico."""

    from sqlalchemy import URL, create_engine
    from sqlalchemy.pool import NullPool

    url = URL.create(
        "postgresql+psycopg",
        username=usuario,
        password=senha.revelar(),
        host=destino.host,
        port=destino.porta,
        database=destino.banco,
        query={"sslmode": "prefer", "connect_timeout": "10"},
    )
    return create_engine(url, poolclass=NullPool)


def abrir_cliente_vault(*, vault_url: str, vault_mount: str) -> Any:
    """Pede o token do operador e devolve o cliente do Vault; uma vez serve para varios ambientes."""

    token = _solicitar_segredo(f"Token de operador do Vault ({vault_url})")
    return _criar_cliente_hvac_operador(vault_url, token, vault_mount)


def pedir_banco_do_ambiente(
    cliente: Any,
    *,
    ambiente: str,
    vault_url: str,
    vault_mount: str,
    namespace: str,
    usuario: str | None,
) -> tuple[DestinoProvisionamento, str, Segredo]:
    """Acha o banco do ambiente no Vault e pede usuario e senha dele, dizendo de qual servidor sao."""

    try:
        destino = descobrir_destino_core(
            cliente,
            ambiente=ambiente,
            namespace=namespace,
            vault_url=vault_url,
            mount=vault_mount,
        )
    except ErroCadastroSistema as falha:
        raise click.ClickException(falha.mensagem) from falha
    servidor = f"{destino.host}:{destino.porta}/{destino.banco}"
    click.echo(f"Banco do ambiente {ambiente}: {servidor}")
    login = _usuario_administrativo(usuario, rotulo=f"de {servidor}")
    senha = _solicitar_segredo(_rotulo_senha(login, servidor, ambiente))
    return destino, login, Segredo(senha)
