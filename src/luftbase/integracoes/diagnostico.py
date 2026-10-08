"""Radiografia das integracoes da aplicacao para a aba Integracoes do painel de controle.

Mostra de onde cada dependencia busca a configuracao (caminho no Vault), o estado de saude e as
versoes. Nunca devolve senha, token ou chave: so os NOMES dos campos de cada segredo e os valores
de uma lista fixa de campos nao sensiveis (host, porta, banco, usuario...).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from luftbase._versao import __version__
from luftbase.integracoes.versoes import listar_componentes
from luftbase.nucleo.excecoes import AutenticacaoCofreInvalida, ErroCofre, SegredoNaoEncontrado

# Unicos campos cujo valor pode aparecer na tela. Qualquer outro e exibido apenas como "oculto".
CAMPOS_VISIVEIS = frozenset(
    {
        "host",
        "porta",
        "nome_banco",
        "banco",
        "usuario",
        "esquema",
        "schema",
        "sslmode",
        "tipo_banco",
        "identificador",
        "sistema_id",
        "conexao",
        "seguranca",
        "remetente",
        "nome_remetente",
        "tls",
        "servico",
        "service_name",
    }
)


class LeitorVault(Protocol):
    """O que o diagnostico precisa do cliente do Vault."""

    def ler_segredo(self, caminho: str) -> Mapping[str, object]: ...

    def ler_metadados(self, caminho: str) -> Mapping[str, object]: ...


@dataclass(frozen=True, slots=True)
class IntegracaoAplicacao:
    """Integracao propria de uma aplicacao (ex.: banco de negocio), exibida na aba Integracoes."""

    id: str
    nome: str
    descricao: str
    caminho_vault: str
    icone: str = "ph-bold ph-plugs-connected"
    categoria: str = "Banco de dados"
    cor: str = "#64748b"


def inspecionar_segredo(vault: LeitorVault, caminho: str) -> dict[str, Any]:
    """Resume um segredo: existencia, versao e campos, sem revelar valores sensiveis."""

    base: dict[str, Any] = {
        "caminho": caminho,
        "existe": False,
        "versao": None,
        "atualizado_em": None,
        "campos": [],
        "erro": None,
    }
    try:
        dados = vault.ler_segredo(caminho)
    except SegredoNaoEncontrado:
        return base
    except AutenticacaoCofreInvalida:
        return {**base, "erro": "O token da aplicacao nao tem acesso a este caminho."}
    except ErroCofre:
        return {**base, "erro": "Nao foi possivel ler o Vault."}
    base["existe"] = True
    base["campos"] = [
        {
            "nome": str(nome),
            "visivel": str(nome) in CAMPOS_VISIVEIS,
            "valor": str(valor) if str(nome) in CAMPOS_VISIVEIS else None,
        }
        for nome, valor in sorted(dados.items(), key=lambda par: str(par[0]))
    ]
    try:
        meta = vault.ler_metadados(caminho)
        base["versao"] = meta.get("current_version")
        base["atualizado_em"] = meta.get("updated_time")
    except ErroCofre:
        pass
    return base


def _valor(segredo: Mapping[str, Any], campo: str) -> str | None:
    for item in segredo["campos"]:
        if item["nome"] == campo and item["visivel"]:
            return str(item["valor"])
    return None


def _cartao(
    identificador: str,
    nome: str,
    categoria: str,
    icone: str,
    cor: str,
    status: str,
    resumo: str,
    fatos: list[tuple[str, str]],
    segredos: list[dict[str, Any]],
    descricao: str = "",
    *,
    logo: str | None = None,
    imagem: str | None = None,
) -> dict[str, Any]:
    """`logo` = nome de um SVG monocromatico em `static/img/integracoes/` (pintado com `cor`); `imagem` = arquivo colorido."""

    return {
        "id": identificador,
        "nome": nome,
        "categoria": categoria,
        "icone": icone,
        "logo": logo,
        "imagem": imagem,
        "cor": cor,
        "status": status,  # ok | alerta | falha | inativo
        "resumo": resumo,
        "descricao": descricao,
        "fatos": [{"rotulo": r, "valor": v} for r, v in fatos],
        "segredos": segredos,
    }


def _status_segredos(segredos: list[dict[str, Any]]) -> tuple[str, str]:
    if any(s["erro"] for s in segredos):
        return "falha", "Sem acesso ao segredo no Vault"
    if any(not s["existe"] for s in segredos):
        return "falha", "Segredo ausente no Vault"
    return "ok", "Configuracao encontrada no Vault"


def _saude_por_nome(estado: Any) -> dict[str, Any]:
    try:
        return {r.dependencia: r for r in estado.bancos.verificar_saude()}
    except Exception:
        return {}


def _texto_saude(resultado: Any) -> tuple[str, str]:
    if resultado is None:
        return "alerta", "Saude nao verificada"
    if resultado.disponivel:
        return "ok", f"Respondendo em {resultado.latencia_ms:.0f} ms"
    return "falha", "Nao respondeu ao teste de saude"


def montar_painel(
    estado: Any,
    vault: LeitorVault,
    *,
    versao_vault: Callable[[], str | None] = lambda: None,
    integracoes_aplicacao: tuple[IntegracaoAplicacao, ...] = (),
) -> dict[str, Any]:
    """Monta os cartoes da aba Integracoes a partir do estado da plataforma."""

    cfg = estado.configuracao
    caminhos = estado.caminhos_vault
    ambiente = cfg.aplicacao.ambiente.value
    saude = _saude_por_nome(estado)
    cartoes: list[dict[str, Any]] = []

    # --- PostgreSQL (core + schema da aplicacao) ---
    seg_sistema = inspecionar_segredo(vault, caminhos.postgresql)
    alias = _valor(seg_sistema, "conexao")
    segs_pg = [seg_sistema]
    if alias:
        segs_pg.append(inspecionar_segredo(vault, f"{caminhos.postgresql_conexoes}/{alias}"))
    status_pg, resumo_pg = _texto_saude(saude.get("core_postgresql"))
    cartoes.append(
        _cartao(
            "postgresql",
            "PostgreSQL",
            "Banco de dados",
            "ph-bold ph-database",
            "#336791",
            status_pg,
            resumo_pg,
            [
                ("Schema da aplicação", _valor(seg_sistema, "esquema") or "—"),
                ("Usuário do sistema", _valor(seg_sistema, "usuario") or "—"),
                ("Servidor", _valor(segs_pg[-1], "host") or "—"),
                ("Banco", _valor(segs_pg[-1], "nome_banco") or "—"),
            ],
            segs_pg,
            "Core da plataforma (usuários, permissões, auditoria) e o schema próprio da aplicação.",
            logo="postgresql",
        )
    )

    # --- SQL Server (diretorio de usuarios) ---
    seg_dir = inspecionar_segredo(vault, caminhos.sqlserver_diretorio)
    status_dir, resumo_dir = _texto_saude(saude.get("diretorio_sqlserver"))
    cartoes.append(
        _cartao(
            "sqlserver",
            "SQL Server",
            "Banco de dados",
            "ph-bold ph-hard-drives",
            "#cc2927",
            status_dir,
            resumo_dir,
            [
                ("Servidor", _valor(seg_dir, "host") or "—"),
                ("Banco", _valor(seg_dir, "nome_banco") or "—"),
                ("Usuário", _valor(seg_dir, "usuario") or "—"),
                ("Acesso", "Somente leitura"),
            ],
            [seg_dir],
            "Diretório corporativo de usuários, lido para o login.",
            logo="microsoftsqlserver",
        )
    )

    # --- Sessoes (Redis ou PostgreSQL) ---
    seg_redis = inspecionar_segredo(vault, caminhos.sessoes_redis)
    usa_redis = "Redis" in type(estado.infraestrutura.armazenamento_sessoes).__name__
    cartoes.append(
        _cartao(
            "sessoes",
            "Sessões",
            "Cache e sessão",
            "ph-bold ph-lightning",
            "#dc382d",
            "ok",
            "Redis ativo" if usa_redis else "Sessões gravadas no PostgreSQL (core)",
            [
                ("Armazenamento", "Redis" if usa_redis else "PostgreSQL (core)"),
                ("Validade", f"{cfg.sessao.ttl_minutos} min"),
                ("Cookie", cfg.sessao.nome_cookie),
                ("Cookie seguro", "Sim" if cfg.sessao.cookie_seguro else "Não"),
            ],
            [seg_redis] if seg_redis["existe"] or usa_redis else [],
            "Onde a sessão compartilhada entre os sistemas Luft fica guardada.",
            logo="redis" if usa_redis else "postgresql",
        )
    )

    # --- E-mail ---
    seg_email = inspecionar_segredo(vault, caminhos.email) if caminhos.email else None
    credencial = estado.infraestrutura.credencial_email
    if credencial is not None:
        gmail = str(credencial.host).lower().endswith("gmail.com")
        cartoes.append(
            _cartao(
                "email",
                "Gmail" if gmail else "E-mail (SMTP)",
                "Comunicação",
                "ph-bold ph-envelope-simple",
                "#ea4335",
                "ok",
                "Envio de e-mail configurado",
                [
                    ("Servidor SMTP", f"{credencial.host}:{credencial.porta}"),
                    ("Segurança", str(credencial.seguranca.value).upper()),
                    ("Remetente", str(credencial.remetente)),
                    ("Redirecionamento", ", ".join(credencial.redirecionar_para) or "Desligado"),
                ],
                [seg_email] if seg_email else [],
                "Conta compartilhada do ambiente usada em notificações e comunicados.",
                logo="gmail" if gmail else None,
            )
        )
    else:
        cartoes.append(
            _cartao(
                "email",
                "E-mail (SMTP)",
                "Comunicação",
                "ph-bold ph-envelope-simple",
                "#ea4335",
                "inativo",
                "Não configurado neste ambiente",
                [("Caminho esperado", caminhos.email or "—")],
                [],
                "Crie o segredo no caminho esperado para habilitar o envio de e-mail.",
            )
        )

    # --- Login corporativo (LDAP) ---
    dirc = cfg.diretorio
    cartoes.append(
        _cartao(
            "ldap",
            "Login corporativo",
            "Identidade",
            "ph-bold ph-identification-badge",
            "#0078d4",
            "ok",
            "Configurado",
            [
                ("Servidor", dirc.servidor),
                ("Domínio", dirc.dominio),
                ("Transporte", dirc.transporte.upper()),
                ("Porta", str(dirc.porta) if dirc.porta else "Padrão do transporte"),
            ],
            [],
            "Autenticação dos usuários no Active Directory da empresa.",
            logo="microsoft",
        )
    )

    # --- Integracoes proprias da aplicacao ---
    for item in integracoes_aplicacao:
        seg = inspecionar_segredo(vault, item.caminho_vault)
        status, resumo = _status_segredos([seg])
        cartoes.append(
            _cartao(
                item.id,
                item.nome,
                item.categoria,
                item.icone,
                item.cor,
                status,
                resumo,
                [
                    ("Servidor", _valor(seg, "host") or "—"),
                    ("Banco", _valor(seg, "nome_banco") or _valor(seg, "service_name") or "—"),
                    ("Usuário", _valor(seg, "usuario") or "—"),
                ],
                [seg],
                item.descricao,
            )
        )

    # --- Vault (agrega todos os segredos usados) ---
    todos: dict[str, dict[str, Any]] = {}
    for cartao in cartoes:
        for seg in cartao["segredos"]:
            todos.setdefault(seg["caminho"], {**seg, "usado_por": []})["usado_por"].append(
                cartao["nome"]
            )
    lista_segredos = list(todos.values())
    status_v, resumo_v = _status_segredos(lista_segredos)
    cartoes.insert(
        0,
        _cartao(
            "vault",
            "Vault",
            "Cofre de segredos",
            "ph-bold ph-vault",
            "#ffc400",
            status_v,
            resumo_v,
            [
                ("Endereço", cfg.cofre.endereco),
                ("Namespace", cfg.cofre.namespace),
                ("Ambiente", ambiente),
                ("Versão do servidor", versao_vault() or "—"),
                ("Segredos em uso", str(len(lista_segredos))),
            ],
            lista_segredos,
            "Cofre de onde a aplicação lê todas as credenciais. "
            "Aqui aparecem só caminhos e nomes de campos.",
            logo="vault",
        ),
    )

    # --- LuftBase / componentes / aplicacao ---
    cartoes.append(
        _cartao(
            "luftbase",
            "LuftBase",
            "Plataforma",
            "ph-bold ph-cube",
            "#2563eb",
            "ok",
            f"Versão {__version__}",
            [("Versão instalada", __version__)],
            [],
            "Framework Luft compartilhado por todos os sistemas.",
            imagem="luftbase.png",
        )
    )
    componentes = listar_componentes()
    cartoes.append(
        _cartao(
            "componentes",
            "Componentes",
            "Plataforma",
            "ph-bold ph-package",
            "#7c3aed",
            "ok",
            f"{sum(1 for c in componentes if c['instalado'])} instalados",
            [(str(c["nome"]), str(c["versao"])) for c in componentes],
            [],
            "Versões das bibliotecas que rodam esta aplicação.",
            logo="python",
        )
    )
    cartoes.append(
        _cartao(
            "aplicacao",
            cfg.aplicacao.nome,
            "Plataforma",
            "ph-bold ph-app-window",
            "#0f766e",
            "ok",
            f"Ambiente {ambiente}",
            [
                ("Identificador", cfg.aplicacao.identificador),
                ("Sistema (id)", str(cfg.aplicacao.sistema_id)),
                ("Ambiente", ambiente),
                ("Versão", cfg.aplicacao.versao or "—"),
            ],
            [],
            "Esta aplicação, como a plataforma a enxerga.",
        )
    )
    return {"ambiente": ambiente, "luftbase_versao": __version__, "cartoes": cartoes}


__all__ = ["CAMPOS_VISIVEIS", "IntegracaoAplicacao", "inspecionar_segredo", "montar_painel"]
