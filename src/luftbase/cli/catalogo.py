"""Sincronizacao do catalogo de modulos e permissoes declarado por uma aplicacao."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import click
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import insert

from luftbase.autorizacao.catalogo_aplicacao import (
    CatalogoAplicacao,
    ErroCatalogo,
    sincronizar_catalogo_aplicacao,
)
from luftbase.configuracao.caminhos_vault import resolver_caminhos_vault
from luftbase.configuracao.modelos import ConfiguracaoLuftBase
from luftbase.infraestrutura.fabrica import FabricaInfraestruturaPadrao
from luftbase.nucleo.excecoes import ErroLuftBase
from luftbase.persistencia.core.seguranca import Permissao, PermissaoGrupo


def _importar_catalogo(referencia: str) -> CatalogoAplicacao:
    modulo, _, atributo = referencia.partition(":")
    if not modulo or not atributo:
        raise click.ClickException("Use --catalogo no formato modulo:OBJETO.")
    # O comando roda na raiz do projeto consumidor, que nem sempre esta no sys.path.
    raiz = str(Path.cwd())
    if raiz not in sys.path:
        sys.path.insert(0, raiz)
    try:
        objeto = getattr(importlib.import_module(modulo), atributo)
    except (ImportError, AttributeError) as erro:
        raise click.ClickException(f"Catalogo {referencia!r} nao encontrado: {erro}") from erro
    if not isinstance(objeto, CatalogoAplicacao):
        raise click.ClickException(f"{referencia!r} nao e um CatalogoAplicacao.")
    return objeto


@click.group("catalogo")
def catalogo() -> None:
    """Catalogo de modulos e permissoes da aplicacao."""


@catalogo.command("sincronizar")
@click.option("--catalogo", "referencia", required=True, help="Referencia modulo:OBJETO.")
@click.option(
    "--grupo-administrador",
    type=int,
    default=None,
    help="Concede as permissoes raiz do catalogo ao codigo de grupo informado.",
)
@click.option(
    "--usuario-banco",
    default=None,
    help="Usuario de migracao do PostgreSQL; a role da aplicacao nao cadastra sistemas.",
)
@click.option("--sim", is_flag=True, help="Nao pede confirmacao.")
def catalogo_sincronizar(
    referencia: str,
    grupo_administrador: int | None,
    usuario_banco: str | None,
    sim: bool,
) -> None:
    """Grava sistema, modulos e permissoes no core do ambiente, de forma aditiva.

    O host e o banco sao os do core da aplicacao (Vault); com `--usuario-banco`, a escrita
    usa esse usuario e a senha e pedida no terminal, nunca por argumento.
    """

    catalogo_aplicacao = _importar_catalogo(referencia)
    try:
        catalogo_aplicacao.validar()
        configuracao = ConfiguracaoLuftBase.de_ambiente()
    except (ErroCatalogo, ErroLuftBase) as erro:
        raise click.ClickException(str(erro)) from erro

    sistema_id = configuracao.aplicacao.sistema_id
    click.echo(f"ambiente={configuracao.aplicacao.ambiente.value}")
    nome = (
        catalogo_aplicacao.sistema.nome if catalogo_aplicacao.sistema else "cadastro do Workspace"
    )
    click.echo(f"sistema_id={sistema_id} ({nome})")
    click.echo(f"modulos={len(catalogo_aplicacao.modulos)}")
    click.echo(f"permissoes={len(catalogo_aplicacao.permissoes)}")
    if not sim:
        click.confirm("Sincronizar este catalogo no core?", abort=True)

    caminhos = resolver_caminhos_vault(
        ambiente=configuracao.aplicacao.ambiente,
        sistema_id=sistema_id,
        namespace=configuracao.cofre.namespace,
        conexao_diretorio=configuracao.cofre.conexao_diretorio,
    )
    senha_banco = (
        click.prompt(f"Senha PostgreSQL de {usuario_banco}", hide_input=True)
        if usuario_banco
        else None
    )
    try:
        recursos = FabricaInfraestruturaPadrao().criar(configuracao, caminhos)
        engine = recursos.bancos.core.engine
        if usuario_banco:
            engine = create_engine(
                engine.url.set(username=usuario_banco, password=senha_banco),
                pool_pre_ping=True,
            )
        with engine.begin() as conexao:
            resultado = sincronizar_catalogo_aplicacao(conexao, sistema_id, catalogo_aplicacao)
            if grupo_administrador is not None:
                raizes = [p.chave for p in catalogo_aplicacao.permissoes if p.pai is None]
                ids = conexao.scalars(
                    select(Permissao.id_permissao).where(
                        Permissao.id_sistema == sistema_id,
                        Permissao.chave_permissao.in_(raizes),
                    )
                ).all()
                for id_permissao in ids:
                    conexao.execute(
                        insert(PermissaoGrupo)
                        .values(
                            codigo_usuariogrupo=grupo_administrador,
                            id_permissao=id_permissao,
                            conceder=True,
                        )
                        .on_conflict_do_nothing(constraint="uq_core_permissaogrupo")
                    )
    except ErroLuftBase as erro:
        raise click.ClickException(str(erro)) from erro
    except Exception as erro:
        detalhe = str(getattr(erro, "orig", erro)).splitlines()[0][:300]
        raise click.ClickException(f"Falha ao sincronizar o catalogo: {detalhe}") from erro
    finally:
        if usuario_banco and "engine" in locals():
            engine.dispose()

    click.echo("sincronizacao=concluida")
    click.echo(f"modulos_sincronizados={resultado.modulos}")
    click.echo(f"permissoes_sincronizadas={resultado.permissoes}")
    if grupo_administrador is not None:
        click.echo(f"grupo_administrador={grupo_administrador}")
