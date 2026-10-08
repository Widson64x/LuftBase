"""Aviso de acesso liberado: e-mail e notificacao quando alguem passa a ter acesso a um sistema.

So conta a permissao **base** do sistema (marcada `eh_acesso_sistema` ou terminada em `.SISTEMA.ACESSAR`, ex.:
`PLATAFORMA.SISTEMA.ACESSAR`, `CONNECTAIR.SISTEMA.ACESSAR`) e so quando o acesso **efetivo** da pessoa
muda de "sem" para "com". Regravar a mesma regra, revogar ou conceder outra permissao nao avisa ninguem.
A concessao a um grupo avisa cada membro que ainda nao tinha acesso.

O aviso nunca desfaz a concessao: qualquer falha de e-mail ou notificacao vira log, e a regra ja gravada continua valendo.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sqlalchemy import select

from luftbase.autorizacao.resolucao import resolver_estados
from luftbase.conteudo.modelos import (
    CategoriaNotificacao,
    NovaNotificacao,
    TipoNotificacao,
)
from luftbase.conteudo.repositorios import RepositorioNotificacoes
from luftbase.persistencia.core.seguranca import (
    Permissao,
    PermissaoGrupo,
    PermissaoUsuario,
    Sistema,
)
from luftbase.persistencia.core.usuario import Usuario
from luftbase.persistencia.diretorio import UsuarioDiretorio

if TYPE_CHECKING:
    from luftbase.infraestrutura.banco.catalogo import CatalogoBancos
    from luftbase.integracoes.email import ServicoEmail

logger = logging.getLogger(__name__)

SUFIXO_ACESSO_BASE = ".SISTEMA.ACESSAR"
TEMPLATE_EMAIL = "luftbase/email/acesso_liberado.html"
# Notificacao global (sistema 0): aparece para a pessoa em qualquer aplicacao da plataforma.
ID_SISTEMA_GLOBAL = 0
# Protecao contra um clique que dispare milhares de e-mails (ex.: grupo enorme).
LIMITE_AVISOS_POR_OPERACAO = 300


@dataclass(frozen=True, slots=True)
class Pessoa:
    """Quem pode ser afetado por uma regra (dados do diretorio corporativo)."""

    id_usuario: int
    login: str
    nome: str
    email: str | None
    id_grupo: int | None


@dataclass(frozen=True, slots=True)
class CapturaAcesso:
    """Foto do acesso base antes da mudanca, para comparar com o depois."""

    id_sistema: int
    pessoas: tuple[Pessoa, ...] = ()
    tem_acesso: dict[int, bool] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ResultadoAviso:
    """O que foi feito; usado na auditoria e nos testes."""

    com_acesso_novo: int = 0
    notificacoes: int = 0
    emails_enviados: int = 0
    sem_email: int = 0
    falhas: int = 0
    ignoradas: int = 0
    email_nao_configurado: bool = False
    modo_teste: bool = False

    def como_dict(self) -> dict[str, int]:
        return {
            "com_acesso_novo": self.com_acesso_novo,
            "notificacoes": self.notificacoes,
            "emails_enviados": self.emails_enviados,
            "sem_email": self.sem_email,
            "falhas": self.falhas,
            "ignoradas": self.ignoradas,
            "email_nao_configurado": int(self.email_nao_configurado),
            "modo_teste": int(self.modo_teste),
        }

    def texto(self) -> str:
        """Resumo para o administrador ver na tela logo depois de liberar o acesso (vazio se ninguem ganhou acesso)."""

        if not self.com_acesso_novo:
            return ""
        partes = [
            f"Acesso liberado a {self.com_acesso_novo} pessoa(s): "
            f"{self.notificacoes} notificação(ões) e {self.emails_enviados} e-mail(s) enviado(s)."
        ]
        if self.sem_email:
            partes.append(f"{self.sem_email} sem e-mail cadastrado no diretório (só a notificação).")
        if self.email_nao_configurado:
            partes.append("O e-mail não está configurado neste ambiente.")
        if self.modo_teste and self.emails_enviados:
            partes.append("E-mail em modo teste: foi para os destinatários de teste, não para as pessoas.")
        if self.falhas:
            partes.append(f"{self.falhas} falha(s); veja o log do servidor.")
        if self.ignoradas:
            partes.append(f"{self.ignoradas} pessoa(s) acima do limite não foram avisadas.")
        return " ".join(partes)


def _pessoas_do_alvo(bancos: CatalogoBancos, tipo: str, id_alvo: int) -> tuple[Pessoa, ...]:
    """Usuario: ele mesmo. Grupo: todos os membros. O e-mail vem do PostgreSQL (`core.tb_usuario`), com o diretorio
    como reserva; quem ja entrou no sistema mas o diretorio nao listou tambem entra. Nunca levanta."""

    do_diretorio = _pessoas_do_diretorio(bancos, tipo, id_alvo)
    try:
        return _completar_com_core(bancos, do_diretorio, tipo, id_alvo)
    except Exception:
        logger.exception("Aviso de acesso: falha ao ler core.tb_usuario (tipo=%s, id=%s)", tipo, id_alvo)
        return do_diretorio


def _completar_com_core(
    bancos: CatalogoBancos, base: tuple[Pessoa, ...], tipo: str, id_alvo: int
) -> tuple[Pessoa, ...]:
    """Mescla com `core.tb_usuario`: o e-mail do PostgreSQL manda; membros so de la entram tambem."""

    with bancos.core.leitura() as sessao:
        consulta = select(
            Usuario.codigo_usuario,
            Usuario.login_usuario,
            Usuario.nome_usuario,
            Usuario.email_usuario,
            Usuario.codigo_usuariogrupo,
        )
        if tipo == "Usuario":
            consulta = consulta.where(Usuario.codigo_usuario == id_alvo)
        else:
            ids = [p.id_usuario for p in base]
            filtro = Usuario.codigo_usuariogrupo == id_alvo
            consulta = consulta.where(filtro | Usuario.codigo_usuario.in_(ids) if ids else filtro)
        linhas = {int(linha[0]): linha for linha in sessao.execute(consulta).all()}

    resultado: dict[int, Pessoa] = {p.id_usuario: p for p in base}
    for id_usuario, linha in linhas.items():
        _, login, nome, email, id_grupo = linha
        email_core = (email or "").strip() or None
        existente = resultado.get(id_usuario)
        if existente is not None:
            if email_core:
                resultado[id_usuario] = Pessoa(
                    id_usuario=existente.id_usuario,
                    login=existente.login,
                    nome=existente.nome,
                    email=email_core,
                    id_grupo=existente.id_grupo,
                )
        else:
            resultado[id_usuario] = Pessoa(
                id_usuario=id_usuario,
                login=(login or "").strip(),
                nome=(nome or login or "").strip(),
                email=email_core,
                id_grupo=id_grupo,
            )
    return tuple(resultado.values())


def _pessoas_do_diretorio(bancos: CatalogoBancos, tipo: str, id_alvo: int) -> tuple[Pessoa, ...]:
    """Pessoas segundo o diretorio corporativo. Falha no diretorio = ninguem (nao bloqueia)."""

    try:
        with bancos.diretorio.leitura() as sessao:
            if tipo == "Usuario":
                origem = [sessao.get(UsuarioDiretorio, id_alvo)]
            else:
                origem = list(
                    sessao.execute(
                        select(UsuarioDiretorio).where(UsuarioDiretorio.id_grupo == id_alvo)
                    )
                    .scalars()
                    .all()
                )
            return tuple(
                Pessoa(
                    id_usuario=u.id_usuario,
                    login=(u.login or "").strip(),
                    nome=(u.nome_completo or u.login or "").strip(),
                    email=(u.email or "").strip() or None,
                    id_grupo=u.id_grupo,
                )
                for u in origem
                if u is not None
            )
    except Exception:
        logger.exception("Aviso de acesso: falha ao ler o diretorio (tipo=%s, id=%s)", tipo, id_alvo)
        return ()


def _acesso_base(
    bancos: CatalogoBancos, pessoas: Iterable[Pessoa], id_sistema: int
) -> dict[int, bool]:
    lista = list(pessoas)
    if not lista:
        return {}
    ids_usuario = [p.id_usuario for p in lista]
    ids_grupo = sorted({p.id_grupo for p in lista if p.id_grupo is not None})
    with bancos.core.leitura() as sessao:
        permissoes = list(
            sessao.execute(select(Permissao).where(Permissao.id_sistema == id_sistema))
            .scalars()
            .all()
        )
        base = {
            p.id_permissao
            for p in permissoes
            if p.ativo
            and (p.eh_acesso_sistema or p.chave_permissao.upper().endswith(SUFIXO_ACESSO_BASE))
        }
        if not base:
            return {p.id_usuario: False for p in lista}
        regras_usuario: dict[int, dict[int, bool]] = {}
        for id_usuario, id_permissao, conceder in sessao.execute(
            select(
                PermissaoUsuario.codigo_usuario,
                PermissaoUsuario.id_permissao,
                PermissaoUsuario.conceder,
            )
            .join(Permissao, Permissao.id_permissao == PermissaoUsuario.id_permissao)
            .where(
                Permissao.id_sistema == id_sistema,
                PermissaoUsuario.codigo_usuario.in_(ids_usuario),
            )
        ).all():
            regras_usuario.setdefault(int(id_usuario), {})[int(id_permissao)] = bool(conceder)
        regras_grupo: dict[int, dict[int, bool]] = {}
        if ids_grupo:
            for id_grupo, id_permissao, conceder in sessao.execute(
                select(
                    PermissaoGrupo.codigo_usuariogrupo,
                    PermissaoGrupo.id_permissao,
                    PermissaoGrupo.conceder,
                )
                .join(Permissao, Permissao.id_permissao == PermissaoGrupo.id_permissao)
                .where(
                    Permissao.id_sistema == id_sistema,
                    PermissaoGrupo.codigo_usuariogrupo.in_(ids_grupo),
                )
            ).all():
                regras_grupo.setdefault(int(id_grupo), {})[int(id_permissao)] = bool(conceder)

    resultado: dict[int, bool] = {}
    for pessoa in lista:
        estados = resolver_estados(
            permissoes,
            regras_usuario.get(pessoa.id_usuario, {}),
            regras_grupo.get(pessoa.id_grupo, {}) if pessoa.id_grupo is not None else {},
            somente=base,
        )
        resultado[pessoa.id_usuario] = any(
            bool(estados[str(id_permissao)]["permitido"]) for id_permissao in base
        )
    return resultado


def capturar_acesso(
    bancos: CatalogoBancos, *, tipo: str, id_alvo: int, id_sistema: int
) -> CapturaAcesso:
    """Foto do acesso base das pessoas afetadas; chame ANTES de gravar a regra.

    Nunca levanta: se algo falhar devolve uma captura vazia e o aviso simplesmente nao acontece.
    """

    try:
        pessoas = _pessoas_do_alvo(bancos, tipo, id_alvo)
        return CapturaAcesso(id_sistema, pessoas, _acesso_base(bancos, pessoas, id_sistema))
    except Exception:
        logger.exception("Aviso de acesso: falha ao capturar o acesso anterior")
        return CapturaAcesso(id_sistema)


def url_absoluta(link: str | None, url_base: str | None) -> str | None:
    """Link do sistema pronto para e-mail: absoluto como esta; relativo, preso ao endereco da plataforma."""

    texto = (link or "").strip()
    if not texto:
        return None
    if texto.lower().startswith(("http://", "https://")):
        return texto
    base = (url_base or "").strip().rstrip("/")
    if not base:
        return None
    return f"{base}/{texto.lstrip('/')}"


def avisar_acessos_liberados(
    bancos: CatalogoBancos,
    email: ServicoEmail,
    antes: CapturaAcesso,
    *,
    url_base: str | None,
    liberado_por: str,
    garantir_usuario: Callable[[int], bool],
) -> ResultadoAviso:
    """Compara com a foto de antes e avisa (notificacao + e-mail) quem ganhou acesso. Nunca levanta."""

    try:
        return _avisar(
            bancos,
            email,
            antes,
            url_base=url_base,
            liberado_por=liberado_por,
            garantir_usuario=garantir_usuario,
        )
    except Exception:
        logger.exception("Aviso de acesso liberado falhou; a permissao foi gravada normalmente")
        return ResultadoAviso(falhas=1)


def _avisar(
    bancos: CatalogoBancos,
    email: ServicoEmail,
    antes: CapturaAcesso,
    *,
    url_base: str | None,
    liberado_por: str,
    garantir_usuario: Callable[[int], bool],
) -> ResultadoAviso:
    if not antes.pessoas:
        return ResultadoAviso()
    depois = _acesso_base(bancos, antes.pessoas, antes.id_sistema)
    novos = [
        p
        for p in antes.pessoas
        if depois.get(p.id_usuario) and not antes.tem_acesso.get(p.id_usuario)
    ]
    if not novos:
        return ResultadoAviso()

    ignoradas = max(len(novos) - LIMITE_AVISOS_POR_OPERACAO, 0)
    if ignoradas:
        logger.warning(
            "Aviso de acesso: %s pessoas ganharam acesso; avisando so as primeiras %s",
            len(novos),
            LIMITE_AVISOS_POR_OPERACAO,
        )
        novos = novos[:LIMITE_AVISOS_POR_OPERACAO]

    with bancos.core.leitura() as sessao:
        sistema = sessao.get(Sistema, antes.id_sistema)
        if sistema is None:
            return ResultadoAviso(com_acesso_novo=len(novos), ignoradas=ignoradas)
        nome_sistema = sistema.nome_sistema
        link_relativo = (sistema.link or "").strip() or None
        bloqueados = {
            int(linha[0])
            for linha in sessao.execute(
                select(Usuario.codigo_usuario).where(
                    Usuario.codigo_usuario.in_([p.id_usuario for p in novos]),
                    (Usuario.bloqueado.is_(True)) | (Usuario.ativo.is_(False)),
                )
            ).all()
        }
    url = url_absoluta(link_relativo, url_base)

    repositorio = RepositorioNotificacoes(bancos.core)
    notificacoes = sem_email = falhas = 0
    envios = []
    ids_com_envio: list[Pessoa] = []
    for pessoa in novos:
        if pessoa.id_usuario in bloqueados:
            continue
        try:
            if garantir_usuario(pessoa.id_usuario):
                metadados: dict[str, object] = {
                    "evento": "ACESSO_LIBERADO",
                    "id_sistema": antes.id_sistema,
                }
                if link_relativo:
                    metadados["acao_url"] = link_relativo
                    metadados["texto_link"] = f"Abrir {nome_sistema}"
                repositorio.criar(
                    ID_SISTEMA_GLOBAL,
                    NovaNotificacao(
                        titulo=f"Acesso liberado: {nome_sistema}",
                        mensagem=(
                            f"Seu acesso ao sistema {nome_sistema} foi liberado. "
                            "Você já pode entrar."
                        ),
                        tipo=TipoNotificacao.SUCESSO,
                        categoria=CategoriaNotificacao.SEGURANCA,
                        id_usuario_destino=pessoa.id_usuario,
                        icone="ph-bold ph-key",
                        criado_por=liberado_por or "SISTEMA",
                        metadados=metadados,
                    ),
                )
                notificacoes += 1
        except Exception:
            falhas += 1
            logger.exception("Aviso de acesso: notificacao falhou para %s", pessoa.login)

        if not pessoa.email:
            sem_email += 1
            continue
        if not email.configurado:
            continue
        try:
            envios.append(
                email.preparar(
                    pessoa.email,
                    f"Seu acesso ao {nome_sistema} foi liberado",
                    template=TEMPLATE_EMAIL,
                    contexto={
                        "nome": pessoa.nome.split(" ")[0] if pessoa.nome else "",
                        "nome_sistema": nome_sistema,
                        "url": url,
                        "liberado_por": liberado_por,
                    },
                )
            )
            ids_com_envio.append(pessoa)
        except Exception:
            falhas += 1
            logger.exception("Aviso de acesso: e-mail nao preparado para %s", pessoa.login)

    enviados = 0
    if envios:
        for resultado in email.enviar_lote(envios):
            if resultado.sucesso:
                enviados += 1
            else:
                falhas += 1
                logger.warning("Aviso de acesso: e-mail nao entregue (%s)", resultado.erro)

    return ResultadoAviso(
        com_acesso_novo=len(novos),
        notificacoes=notificacoes,
        emails_enviados=enviados,
        sem_email=sem_email,
        falhas=falhas,
        ignoradas=ignoradas,
        email_nao_configurado=not email.configurado,
        modo_teste=bool(email.modo_teste),
    )


__all__ = [
    "CapturaAcesso",
    "Pessoa",
    "ResultadoAviso",
    "SUFIXO_ACESSO_BASE",
    "avisar_acessos_liberados",
    "capturar_acesso",
    "url_absoluta",
]
