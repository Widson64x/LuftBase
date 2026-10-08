"""Aviso de acesso liberado: e-mail e notificacao so na transicao sem acesso -> com acesso."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pytest
from core_sqlite import motor_sqlite as _motor
from sqlalchemy import (
    insert,
    select,
    text,
)

from luftbase.autorizacao.aviso_acesso import (
    LIMITE_AVISOS_POR_OPERACAO,
    avisar_acessos_liberados,
    capturar_acesso,
    url_absoluta,
)
from luftbase.infraestrutura.banco.sessoes import BancoSQLAlchemy
from luftbase.persistencia.base import BaseLuft
from luftbase.persistencia.core.notificacoes import Notificacao
from luftbase.persistencia.core.seguranca import (
    Modulo,
    Permissao,
    PermissaoGrupo,
    PermissaoUsuario,
    Sistema,
)
from luftbase.persistencia.core.usuario import Usuario
from luftbase.persistencia.diretorio import ESQUEMA_DIRETORIO, BaseDiretorio, UsuarioDiretorio


@dataclass
class EmailFalso:
    """Substitui o ServicoEmail: guarda o que seria enviado."""

    configurado: bool = True
    modo_teste: bool = False
    falhar_envio: bool = False
    preparados: list[dict[str, Any]] = field(default_factory=list)

    def preparar(self, para: str, assunto: str, **opcoes: Any) -> dict[str, Any]:
        item = {"para": para, "assunto": assunto, **opcoes}
        self.preparados.append(item)
        return item

    def enviar_lote(self, envios: list[dict[str, Any]]) -> list[Any]:
        return [
            type("R", (), {"sucesso": not self.falhar_envio, "erro": "smtp fora"})()
            for _ in envios
        ]


class Bancos:
    def __init__(self) -> None:
        self.core = BancoSQLAlchemy("core", _motor(BaseLuft, "core"))
        self.diretorio = BancoSQLAlchemy("diretorio", _motor(BaseDiretorio, ESQUEMA_DIRETORIO))


@pytest.fixture
def ambiente():  # type: ignore[no-untyped-def]
    bancos = Bancos()
    with bancos.core.unidade_trabalho() as s:
        s.execute(
            insert(Sistema).values(id_sistema=3, nome_sistema="Luft-Workspace", link="/Luft-Workspace")
        )
        s.execute(insert(Sistema).values(id_sistema=0, nome_sistema="Plataforma"))
        s.execute(
            insert(Modulo).values(id_modulo=1, id_sistema=3, codigo_modulo="SISTEMA", nome_modulo="Sistema")
        )
        s.execute(
            insert(Permissao).values(
                id_permissao=10,
                id_sistema=3,
                id_modulo=1,
                chave_permissao="WORKSPACE.SISTEMA.ACESSAR",
                recurso="SISTEMA",
                acao="ACESSAR",
                descricao_permissao="Acessar",
                ativo=True,
            )
        )
        s.execute(
            insert(Permissao).values(
                id_permissao=11,
                id_sistema=3,
                id_modulo=1,
                chave_permissao="WORKSPACE.RELATORIO.VER",
                recurso="RELATORIO",
                acao="VISUALIZAR",
                descricao_permissao="Ver relatorio",
                ativo=True,
            )
        )
        for uid, login, nome in ((1, "ana", "Ana Silva"), (2, "bia", "Bia Souza"), (3, "caio", "Caio Lima")):
            s.execute(
                insert(Usuario).values(
                    codigo_usuario=uid,
                    login_usuario=login,
                    nome_usuario=nome,
                    email_usuario=f"{login}@luft.com" if uid != 3 else None,
                    ativo=True,
                    bloqueado=False,
                    status_online=False,
                )
            )
    with bancos.diretorio.unidade_trabalho() as s:
        for uid, login, nome, grupo in (
            (1, "ana", "Ana Silva", 7),
            (2, "bia", "Bia Souza", 7),
            (3, "caio", "Caio Lima", 7),
        ):
            s.add(
                UsuarioDiretorio(
                    id_usuario=uid,
                    login=login,
                    nome_completo=nome,
                    email=f"{login}@luft.com" if uid != 3 else None,
                    id_grupo=grupo,
                )
            )
    return bancos


def _regra_usuario(bancos: Bancos, uid: int, pid: int, conceder: bool = True) -> None:
    with bancos.core.unidade_trabalho() as s:
        existente = s.execute(
            select(PermissaoUsuario).where(
                PermissaoUsuario.codigo_usuario == uid, PermissaoUsuario.id_permissao == pid
            )
        ).scalar_one_or_none()
        if existente is None:
            s.add(PermissaoUsuario(codigo_usuario=uid, id_permissao=pid, conceder=conceder))
        else:
            existente.conceder = conceder


def _regra_grupo(bancos: Bancos, gid: int, pid: int, conceder: bool = True) -> None:
    with bancos.core.unidade_trabalho() as s:
        s.add(PermissaoGrupo(codigo_usuariogrupo=gid, id_permissao=pid, conceder=conceder))


def _avisar(bancos: Bancos, email: EmailFalso, antes: Any, **extra: Any):  # type: ignore[no-untyped-def]
    return avisar_acessos_liberados(
        bancos,  # type: ignore[arg-type]
        email,  # type: ignore[arg-type]
        antes,
        url_base="https://luft.exemplo/",
        liberado_por="widson.araujo",
        garantir_usuario=extra.get("garantir", lambda _id: True),
    )


def _notificacoes(bancos: Bancos) -> list[Notificacao]:
    with bancos.core.leitura() as s:
        return list(s.execute(select(Notificacao)).scalars().all())


def test_conceder_a_permissao_base_envia_email_e_notificacao(ambiente: Bancos) -> None:
    email = EmailFalso()
    antes = capturar_acesso(ambiente, tipo="Usuario", id_alvo=1, id_sistema=3)  # type: ignore[arg-type]

    _regra_usuario(ambiente, 1, 10)
    resultado = _avisar(ambiente, email, antes)

    assert resultado.com_acesso_novo == 1
    assert resultado.notificacoes == 1
    assert resultado.emails_enviados == 1
    assert email.preparados[0]["para"] == "ana@luft.com"
    assert email.preparados[0]["assunto"] == "Seu acesso ao Luft-Workspace foi liberado"
    assert email.preparados[0]["contexto"]["url"] == "https://luft.exemplo/Luft-Workspace"
    (notificacao,) = _notificacoes(ambiente)
    assert notificacao.id_sistema == 0  # global
    assert notificacao.id_usuario_destino == 1
    metadados = notificacao.metadados_json
    if isinstance(metadados, str):  # SQLite devolve o JSON como texto
        metadados = json.loads(metadados)
    assert metadados["acao_url"] == "/Luft-Workspace"


def test_outra_permissao_nao_avisa(ambiente: Bancos) -> None:
    email = EmailFalso()
    antes = capturar_acesso(ambiente, tipo="Usuario", id_alvo=1, id_sistema=3)  # type: ignore[arg-type]

    _regra_usuario(ambiente, 1, 11)  # RELATORIO.VER, nao e a base
    resultado = _avisar(ambiente, email, antes)

    assert resultado.com_acesso_novo == 0
    assert email.preparados == []
    assert _notificacoes(ambiente) == []


def test_regravar_regra_que_ja_dava_acesso_nao_repete_o_aviso(ambiente: Bancos) -> None:
    _regra_usuario(ambiente, 1, 10)
    email = EmailFalso()
    antes = capturar_acesso(ambiente, tipo="Usuario", id_alvo=1, id_sistema=3)  # type: ignore[arg-type]

    _regra_usuario(ambiente, 1, 10, True)
    resultado = _avisar(ambiente, email, antes)

    assert resultado.com_acesso_novo == 0
    assert email.preparados == []


def test_bloquear_nao_avisa_e_desbloquear_avisa(ambiente: Bancos) -> None:
    _regra_usuario(ambiente, 1, 10, False)
    email = EmailFalso()
    antes = capturar_acesso(ambiente, tipo="Usuario", id_alvo=1, id_sistema=3)  # type: ignore[arg-type]
    assert antes.tem_acesso[1] is False

    _regra_usuario(ambiente, 1, 10, True)  # troca bloqueio por permissao
    resultado = _avisar(ambiente, email, antes)

    assert resultado.com_acesso_novo == 1


def test_grupo_avisa_so_quem_ainda_nao_tinha_acesso(ambiente: Bancos) -> None:
    _regra_usuario(ambiente, 2, 10)  # Bia ja tinha acesso direto
    email = EmailFalso()
    antes = capturar_acesso(ambiente, tipo="Grupo", id_alvo=7, id_sistema=3)  # type: ignore[arg-type]

    _regra_grupo(ambiente, 7, 10)
    resultado = _avisar(ambiente, email, antes)

    assert resultado.com_acesso_novo == 2  # Ana e Caio
    assert sorted(n.id_usuario_destino for n in _notificacoes(ambiente)) == [1, 3]
    assert [p["para"] for p in email.preparados] == ["ana@luft.com"]
    assert resultado.sem_email == 1  # Caio nao tem e-mail: fica so a notificacao


def test_usuario_bloqueado_nao_e_avisado(ambiente: Bancos) -> None:
    with ambiente.core.unidade_trabalho() as s:
        s.execute(text("UPDATE tb_usuario SET bloqueado = 1 WHERE codigo_usuario = 1"))
    email = EmailFalso()
    antes = capturar_acesso(ambiente, tipo="Usuario", id_alvo=1, id_sistema=3)  # type: ignore[arg-type]

    _regra_usuario(ambiente, 1, 10)
    resultado = _avisar(ambiente, email, antes)

    assert resultado.notificacoes == 0
    assert email.preparados == []


def test_falha_do_email_nao_levanta_e_e_contada(ambiente: Bancos) -> None:
    email = EmailFalso(falhar_envio=True)
    antes = capturar_acesso(ambiente, tipo="Usuario", id_alvo=1, id_sistema=3)  # type: ignore[arg-type]

    _regra_usuario(ambiente, 1, 10)
    resultado = _avisar(ambiente, email, antes)

    assert resultado.emails_enviados == 0
    assert resultado.falhas == 1
    assert resultado.notificacoes == 1  # a notificacao nao depende do e-mail


def test_email_nao_configurado_ainda_notifica(ambiente: Bancos) -> None:
    email = EmailFalso(configurado=False)
    antes = capturar_acesso(ambiente, tipo="Usuario", id_alvo=1, id_sistema=3)  # type: ignore[arg-type]

    _regra_usuario(ambiente, 1, 10)
    resultado = _avisar(ambiente, email, antes)

    assert resultado.notificacoes == 1
    assert email.preparados == []


def test_erro_inesperado_nunca_desfaz_a_concessao(ambiente: Bancos) -> None:
    antes = capturar_acesso(ambiente, tipo="Usuario", id_alvo=1, id_sistema=3)  # type: ignore[arg-type]
    _regra_usuario(ambiente, 1, 10)

    def quebra(_id: int) -> bool:
        raise RuntimeError("banco caiu")

    resultado = _avisar(ambiente, EmailFalso(), antes, garantir=quebra)

    assert resultado.falhas >= 1  # registrou, mas nao levantou
    with ambiente.core.leitura() as s:
        assert s.execute(select(PermissaoUsuario)).scalars().first() is not None


def test_limite_de_avisos_por_operacao(ambiente: Bancos) -> None:
    from luftbase.autorizacao import aviso_acesso as modulo

    mp = pytest.MonkeyPatch()
    mp.setattr(modulo, "LIMITE_AVISOS_POR_OPERACAO", 1)
    try:
        antes = capturar_acesso(ambiente, tipo="Grupo", id_alvo=7, id_sistema=3)  # type: ignore[arg-type]
        _regra_grupo(ambiente, 7, 10)
        resultado = _avisar(ambiente, EmailFalso(), antes)
    finally:
        mp.undo()

    assert resultado.com_acesso_novo == 1
    assert resultado.ignoradas == 2
    assert LIMITE_AVISOS_POR_OPERACAO == 300


def test_sem_permissao_base_no_sistema_nao_avisa(ambiente: Bancos) -> None:
    antes = capturar_acesso(ambiente, tipo="Usuario", id_alvo=1, id_sistema=99)  # type: ignore[arg-type]

    assert antes.tem_acesso == {1: False}
    assert _avisar(ambiente, EmailFalso(), antes).com_acesso_novo == 0


def test_url_absoluta() -> None:
    assert url_absoluta("/Luft-Workspace", "https://luft/") == "https://luft/Luft-Workspace"
    assert url_absoluta("https://outro/app", "https://luft/") == "https://outro/app"
    assert url_absoluta("/x", None) is None
    assert url_absoluta(None, "https://luft/") is None


def _servico_email_real():  # type: ignore[no-untyped-def]
    from luftbase.configuracao import Ambiente
    from luftbase.infraestrutura.cofre.credenciais import (
        CredencialEmail,
        Segredo,
        SegurancaSmtp,
    )
    from luftbase.integracoes.email import ServicoEmail

    credencial = CredencialEmail(
        host="smtp.exemplo",
        porta=587,
        seguranca=SegurancaSmtp.STARTTLS,
        usuario="conta@luft.com",
        senha=Segredo("x"),
        remetente="portal@luft.com",
        nome_remetente="Luft",
    )
    return ServicoEmail(credencial, ambiente=Ambiente.PRODUCAO, nome_sistema="Luft Workspace")


def test_template_do_email_renderiza_com_o_botao_e_o_nome() -> None:
    envio = _servico_email_real().preparar(
        "ana@luft.com",
        "Seu acesso ao Luft-Workspace foi liberado",
        template="luftbase/email/acesso_liberado.html",
        contexto={
            "nome": "Ana",
            "nome_sistema": "Luft-Workspace",
            "url": "https://luft.exemplo/Luft-Workspace",
            "liberado_por": "widson.araujo",
        },
    )

    html = envio.mensagem.get_body(("html",)).get_content()  # type: ignore[union-attr]
    assert "Acesso liberado" in html and "Tudo pronto, Ana!" in html
    assert 'href="https://luft.exemplo/Luft-Workspace"' in html
    assert "widson.araujo" in html


def test_template_do_email_sem_link_nao_quebra() -> None:
    envio = _servico_email_real().preparar(
        "ana@luft.com",
        "Acesso",
        template="luftbase/email/acesso_liberado.html",
        contexto={"nome": "", "nome_sistema": "Luft-Workspace", "url": None, "liberado_por": ""},
    )

    html = envio.mensagem.get_body(("html",)).get_content()  # type: ignore[union-attr]
    assert "Entre pelo portal da Luft" in html
    assert "Tudo pronto!" in html
    assert "href=\"None\"" not in html


def test_rotas_capturam_antes_e_avisam_depois_de_gravar() -> None:
    from pathlib import Path

    from luftbase.web import seguranca

    codigo = Path(seguranca.__file__).read_text(encoding="utf-8")
    salvar = codigo[codigo.index("def salvar_vinculo") : codigo.index("def resumo_regras_origem")]
    espelhar = codigo[codigo.index("def espelhar_permissoes") : codigo.index("def limpar_todas")]

    for rota in (salvar, espelhar):
        assert (
            rota.index("capturar_acesso(")
            < rota.index("estado.bancos.core.escrita()")
            < rota.index("_avisar_acesso_liberado(")
        )


def test_resumo_para_o_administrador() -> None:
    from luftbase.autorizacao.aviso_acesso import ResultadoAviso

    assert ResultadoAviso().texto() == ""  # ninguem ganhou acesso: nada a dizer

    completo = ResultadoAviso(
        com_acesso_novo=3, notificacoes=3, emails_enviados=2, sem_email=1
    ).texto()
    assert "3 pessoa(s)" in completo and "2 e-mail(s) enviado(s)" in completo
    assert "1 sem e-mail cadastrado" in completo

    assert "não está configurado" in ResultadoAviso(
        com_acesso_novo=1, notificacoes=1, email_nao_configurado=True
    ).texto()
    assert "modo teste" in ResultadoAviso(
        com_acesso_novo=1, notificacoes=1, emails_enviados=1, modo_teste=True
    ).texto()
    assert "1 falha(s)" in ResultadoAviso(com_acesso_novo=1, falhas=1).texto()


def test_aviso_informa_sem_email_e_modo_teste(ambiente: Bancos) -> None:
    email = EmailFalso(modo_teste=True)
    antes = capturar_acesso(ambiente, tipo="Usuario", id_alvo=1, id_sistema=3)  # type: ignore[arg-type]
    _regra_usuario(ambiente, 1, 10)

    resultado = _avisar(ambiente, email, antes)

    assert resultado.modo_teste is True
    assert "modo teste" in resultado.texto()


def test_rotas_devolvem_o_resumo_do_aviso_para_a_tela() -> None:
    from pathlib import Path

    from luftbase.web import seguranca

    codigo = Path(seguranca.__file__).read_text(encoding="utf-8")
    assert codigo.count("aviso=aviso") == 2  # salvar regra e espelhar permissoes
