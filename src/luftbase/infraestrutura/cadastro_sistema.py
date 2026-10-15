"""Cadastro de um sistema no core feito pela CLI, com ou sem provisionamento de banco e Vault.

E o mesmo cadastro da tela do Workspace (`api_sistema_criar`): sistema, modulo PLATAFORMA,
permissao base de acesso e concessao ao grupo; para sistema integrado acrescenta schema, role e
segredo no Vault. A diferenca e quem chama: aqui nao ha usuario autenticado nem requisicao, so um
operador com credencial administrativa no terminal.

Tudo ocorre na transacao do core. O segredo do Vault e gravado por ultimo e removido se o core nao
confirmar, para nunca sobrar credencial sem sistema.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, cast

from sqlalchemy import Engine, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from luftbase.infraestrutura.provisionamento_sistema import (
    DestinoProvisionamento,
    ErroProvisionamento,
    PlanoSistema,
    ProvisionadorSistema,
    derivar_plano,
)
from luftbase.persistencia.core.seguranca import Modulo, Permissao, PermissaoGrupo, Sistema

logger = logging.getLogger(__name__)

GRUPO_TI_PADRAO = 6


class ErroCadastroSistema(Exception):
    """Falha controlada do cadastro; `campos` aponta o que o operador deve corrigir."""

    def __init__(self, mensagem: str, campos: dict[str, str] | None = None) -> None:
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.campos = campos or {}


@dataclass(frozen=True, slots=True)
class ResultadoCadastro:
    """O que foi gravado, sem nenhum segredo."""

    id_sistema: int
    nome: str
    chave_permissao_base: str
    schema_aplicacao: str | None = None
    role: str | None = None
    caminho_segredo: str | None = None
    etapas: tuple[str, ...] = field(default_factory=tuple)


def descobrir_destino_core(
    vault: Any,
    *,
    ambiente: str,
    namespace: str,
    vault_url: str,
    mount: str = "secret",
    sistema_referencia: int = 0,
) -> DestinoProvisionamento:
    """Acha host, porta e banco do core lendo a conexao do sistema de referencia no Vault.

    Evita o operador digitar o endereco do PostgreSQL: o segredo `sistemas/0` (Workspace) aponta
    para a conexao compartilhada, e essa conexao diz onde fica o banco do ambiente escolhido.
    """

    raiz = f"{namespace}/{ambiente}/bancos/postgresql"
    kv = vault.secrets.kv.v2

    def ler(caminho: str) -> Any:
        return kv.read_secret_version(
            path=caminho, mount_point=mount, raise_on_deleted_version=True
        )["data"]["data"]

    def montar(conexao: Any, alias: str) -> DestinoProvisionamento:
        return DestinoProvisionamento(
            ambiente=ambiente,
            namespace=namespace,
            vault_url=vault_url,
            host=str(conexao["host"]),
            porta=int(conexao["porta"]),
            banco=str(conexao["nome_banco"]),
            sistema_referencia=sistema_referencia,
            mount=mount,
            alias_conexao=alias,
        )

    motivos: list[str] = []
    try:
        alias = str(ler(f"{raiz}/sistemas/{sistema_referencia}").get("conexao") or "").strip()
        return montar(ler(f"{raiz}/conexoes/{alias}"), alias)
    except Exception as erro:
        motivos.append(f"sistemas/{sistema_referencia}: {type(erro).__name__}")

    # Alternativa: se o ambiente tem uma unica conexao PostgreSQL, e ela.
    try:
        chaves = [
            c
            for c in kv.list_secrets(path=f"{raiz}/conexoes", mount_point=mount)["data"]["keys"]
            if not c.endswith("/")
        ]
        if len(chaves) == 1:
            return montar(ler(f"{raiz}/conexoes/{chaves[0]}"), chaves[0])
        motivos.append(
            f"conexoes/ tem {len(chaves)} segredos ({', '.join(chaves)}); nao ha como escolher"
        )
    except Exception as erro:
        motivos.append(f"conexoes/: {type(erro).__name__}")
    raise ErroCadastroSistema(
        f"Nao foi possivel descobrir o banco do ambiente '{ambiente}' no Vault ({'; '.join(motivos)}). "
        f"Caminho base: {raiz}. Confira o token (ele precisa ler esse caminho) ou informe "
        "--banco-host, --banco-porta e --banco-nome."
    )


def revisao_cabeca() -> str | None:
    """Ultima revisao das migrations empacotadas neste LuftBase."""

    from alembic.script import ScriptDirectory

    from luftbase.migracoes.configuracao import criar_configuracao_alembic

    return ScriptDirectory.from_config(criar_configuracao_alembic()).get_current_head()


def exigir_core_atualizado(engine_core: Engine, cabeca: str | None = None) -> None:
    """Recusa cadastrar se o core esta numa revisao diferente da deste LuftBase.

    Evita o erro cru de coluna inexistente: o banco copiado de outro ambiente costuma estar numa
    revisao mais antiga e precisa de `luftbase banco atualizar-core` antes.
    """

    from sqlalchemy import text

    esperada = cabeca or revisao_cabeca()
    try:
        with engine_core.connect() as conexao:
            atual = conexao.execute(text("SELECT version_num FROM core.alembic_version")).scalar()
    except SQLAlchemyError as erro:
        raise ErroCadastroSistema(
            "Nao foi possivel ler a revisao do core (core.alembic_version). O banco ja tem o "
            "schema core? Rode `luftbase banco atualizar-core` ou `banco bootstrap`."
        ) from erro
    if atual != esperada:
        raise ErroCadastroSistema(
            f"O core esta na revisao {atual} e este LuftBase espera {esperada}. "
            "Rode `luftbase banco atualizar-core --ambiente desenvolvimento` e tente de novo."
        )


def _conflitos(
    sessao: Session, id_sistema: int | None, nome: str, schema: str | None
) -> dict[str, str]:
    conflitos: dict[str, str] = {}
    if id_sistema is not None and sessao.get(Sistema, id_sistema) is not None:
        conflitos["IdSistema"] = f"Ja existe um sistema com o ID {id_sistema}."
    if sessao.execute(
        select(Sistema.id_sistema).where(func.lower(Sistema.nome_sistema) == nome.lower())
    ).first():
        conflitos["Nome"] = f"Ja existe um sistema cadastrado com o nome '{nome}'."
    if schema:
        dono = sessao.execute(
            select(Sistema.nome_sistema).where(Sistema.schema_aplicacao == schema)
        ).scalar()
        if dono:
            conflitos["SchemaAplicacao"] = f"O schema '{schema}' ja pertence ao sistema '{dono}'."
    return conflitos


def _gravar_catalogo(
    sessao: Session, valores: dict[str, Any], grupo_acesso: int
) -> tuple[Sistema, str]:
    """Sistema, modulo PLATAFORMA, permissao base e concessao ao grupo (passos 1, 3, 4 e 5)."""

    chave_base = str(valores["chave_permissao_base"])
    campos = {k: v for k, v in valores.items() if k not in ("id_sistema", "chave_permissao_base")}
    if valores.get("id_sistema") is not None:
        campos["id_sistema"] = valores["id_sistema"]
    sistema = Sistema(**campos)
    sessao.add(sistema)
    sessao.flush()
    nome = sistema.nome_sistema
    modulo = Modulo(
        id_sistema=sistema.id_sistema,
        codigo_modulo="PLATAFORMA",
        nome_modulo=f"Plataforma {nome}",
        descricao_modulo=f"Modulo estrutural e de controle de acesso do sistema {nome}.",
        ativo=True,
        ordem_exibicao=0,
        icone="ph-bold ph-shield-check",
    )
    sessao.add(modulo)
    sessao.flush()
    permissao = Permissao(
        id_sistema=sistema.id_sistema,
        id_modulo=modulo.id_modulo,
        chave_permissao=chave_base,
        recurso="SISTEMA",
        acao="ACESSAR",
        descricao_permissao=f"Permissao base de acesso ao sistema {nome}.",
        ativo=True,
        sensivel=False,
        eh_acesso_sistema=True,
        ordem_exibicao=0,
    )
    sessao.add(permissao)
    sessao.flush()
    sessao.add(
        PermissaoGrupo(
            id_permissao=permissao.id_permissao,
            codigo_usuariogrupo=grupo_acesso,
            conceder=True,
        )
    )
    sessao.flush()
    return sistema, chave_base


def cadastrar_sistema(
    engine_core: Engine,
    valores: dict[str, Any],
    *,
    provisionador: ProvisionadorSistema | None = None,
    alias_conexao: str = "",
    grupo_acesso: int = GRUPO_TI_PADRAO,
    ao_etapa: Callable[[str], None] | None = None,
) -> ResultadoCadastro:
    """Grava o sistema e, quando ha `provisionador`, schema, role e segredo no Vault.

    `valores` sai de `validar_payload_novo_sistema`, o mesmo validador da tela, entao as regras
    (nome unico, schema valido, externo sem schema) sao identicas nos dois caminhos.
    """

    etapas: list[str] = []

    def registrar(texto: str) -> None:
        etapas.append(texto)
        if ao_etapa is not None:
            ao_etapa(texto)

    schema = cast("str | None", valores.get("schema_aplicacao"))
    nome = str(valores["nome_sistema"])
    if provisionador is not None and not valores.get("integra_luftbase", True):
        raise ErroCadastroSistema(
            "Sistema que nao integra o LuftBase nao tem schema, role nem segredo no Vault."
        )
    if provisionador is not None and not schema:
        raise ErroCadastroSistema("O schema e obrigatorio para provisionar banco e Vault.")

    plano: PlanoSistema | None = None
    caminho: str | None = None
    segredo_gravado: int | None = None
    confirmado = False
    try:
        try:
            with Session(engine_core) as sessao, sessao.begin():
                conflitos = _conflitos(
                    sessao, cast("int | None", valores.get("id_sistema")), nome, schema
                )
                if conflitos:
                    raise ErroCadastroSistema(
                        "Ja existe um cadastro conflitante: " + "; ".join(conflitos.values()),
                        conflitos,
                    )
                sistema, chave_base = _gravar_catalogo(sessao, valores, grupo_acesso)
                id_sistema = sistema.id_sistema
                registrar(f"Sistema '{nome}' criado em core.tb_sistema (ID {id_sistema}).")
                registrar(f"Permissao base '{chave_base}' concedida ao grupo {grupo_acesso}.")

                if provisionador is not None:
                    if provisionador.segredo_existe(id_sistema):
                        raise ErroCadastroSistema(
                            f"O Vault ja tem 'sistemas/{id_sistema}'. Nada foi gravado; remova o "
                            "segredo antigo com 'luftbase vault postgresql remover-sistemas'.",
                            {"IdSistema": "segredo ja existente"},
                        )
                    try:
                        plano = derivar_plano(id_sistema, nome, str(schema), provisionador.ambiente)
                        senha, criado = provisionador.provisionar_banco(plano)
                    except ErroProvisionamento as falha:
                        raise ErroCadastroSistema(falha.mensagem) from falha
                    registrar(
                        f"Schema '{plano.esquema}' {'criado' if criado else 'reaproveitado'}; "
                        f"role '{plano.role}' com senha nova e privilegios no core."
                    )
                    try:
                        caminho = provisionador.gravar_segredo(plano, alias_conexao, senha)
                    except Exception as erro_vault:
                        raise ErroCadastroSistema(
                            "O Vault recusou a gravacao do segredo do sistema "
                            f"({type(erro_vault).__name__}). Confira se o token tem escrita em "
                            "bancos/postgresql/sistemas."
                        ) from erro_vault
                    segredo_gravado = id_sistema
                    registrar(f"Segredo '{caminho}' gravado no Vault.")
        except IntegrityError as erro:
            raise ErroCadastroSistema(
                "O banco recusou o cadastro por conflito de dados: "
                f"{str(getattr(erro, 'orig', erro)).splitlines()[0][:200]}"
            ) from erro
        except SQLAlchemyError as erro:
            raise ErroCadastroSistema(
                "Falha no banco ao cadastrar o sistema: "
                f"{str(getattr(erro, 'orig', erro)).splitlines()[0][:200]}"
            ) from erro
        confirmado = True
    finally:
        if provisionador is not None and segredo_gravado is not None and not confirmado:
            try:
                provisionador.remover_segredo(segredo_gravado)
                logger.warning(
                    "Segredo do sistema %s removido: o core nao confirmou.", segredo_gravado
                )
            except Exception:
                logger.exception(
                    "Segredo do sistema %s ficou no Vault sem cadastro no core; remova com "
                    "'luftbase vault postgresql remover-sistemas'.",
                    segredo_gravado,
                )

    return ResultadoCadastro(
        id_sistema=id_sistema,
        nome=nome,
        chave_permissao_base=chave_base,
        schema_aplicacao=schema,
        role=plano.role if plano else None,
        caminho_segredo=caminho,
        etapas=tuple(etapas),
    )


__all__ = [
    "GRUPO_TI_PADRAO",
    "ErroCadastroSistema",
    "ResultadoCadastro",
    "cadastrar_sistema",
    "descobrir_destino_core",
    "exigir_core_atualizado",
    "revisao_cabeca",
]
