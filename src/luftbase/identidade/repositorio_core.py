"""Repositorio de persistencia e sincronizacao da tabela core.tb_usuario."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import exists, func, literal_column, select, update
from sqlalchemy.dialects.postgresql import insert

from luftbase.infraestrutura.banco.sessoes import BancoSQLAlchemy
from luftbase.persistencia.core.sessoes import Sessao
from luftbase.persistencia.core.usuario import Usuario

logger = logging.getLogger("luftbase.identidade.core")


class RepositorioUsuariosPostgreSQL:
    """Gerencia a tabela interna de usuarios espelhados no banco corporativo core."""

    def __init__(self, banco: BancoSQLAlchemy) -> None:
        self._banco = banco

    def obter_por_codigo(self, codigo_usuario: int) -> Usuario | None:
        """Busca um usuario local pelo codigo corporativo."""

        with self._banco.leitura() as sessao:
            return sessao.get(Usuario, codigo_usuario)

    def obter_dados_perfil(self, codigo_usuario: int) -> dict[str, Any] | None:
        """Busca os dados cadastrais e operacionais do usuario para exibicao no perfil."""

        with self._banco.leitura() as sessao:
            reg = sessao.get(Usuario, codigo_usuario)
            if reg is None:
                return None
            return {
                "codigo_usuario": reg.codigo_usuario,
                "login_usuario": reg.login_usuario,
                "nome_usuario": reg.nome_usuario,
                "email_usuario": reg.email_usuario,
                "codigo_usuariogrupo": reg.codigo_usuariogrupo,
                "sigla_usuariogrupo": reg.sigla_usuariogrupo,
                "descricao_usuariogrupo": reg.descricao_usuariogrupo,
                "foto_perfil": reg.foto_perfil,
                "status_online": reg.status_online,
                "cargo_usuario": reg.cargo_usuario,
                "departamento_usuario": reg.departamento_usuario,
                "telefone_usuario": reg.telefone_usuario,
                "celular_usuario": reg.celular_usuario,
                "unidade_filial": reg.unidade_filial,
                "tema_preferido": reg.tema_preferido,
                "modo_tema": reg.modo_tema,
                "idioma": reg.idioma,
                "ultimo_acesso": reg.ultimo_acesso.isoformat() if reg.ultimo_acesso else None,
                "ultimo_ip": reg.ultimo_ip,
                "ultimo_user_agent": reg.ultimo_user_agent,
                "total_logins": reg.total_logins,
                "criado_em": reg.criado_em.isoformat() if reg.criado_em else None,
            }

    def obter_por_login(self, login_usuario: str) -> Usuario | None:
        """Busca um usuario local pelo login de rede (case-insensitive)."""

        login_limpo = login_usuario.strip().casefold()
        with self._banco.leitura() as sessao:
            return sessao.execute(
                select(Usuario).where(Usuario.login_usuario.ilike(login_limpo))
            ).scalar_one_or_none()

    def garantir_usuario_do_diretorio(
        self,
        *,
        codigo_usuario: int,
        login_usuario: str,
        nome_usuario: str,
        email_usuario: str | None = None,
        codigo_usuariogrupo: int | None = None,
        sigla_usuariogrupo: str | None = None,
        descricao_usuariogrupo: str | None = None,
    ) -> Usuario:
        """Insere ou sincroniza os dados cadastrais vindos do LuftInforma."""

        login_limpo = login_usuario.strip()
        nome_limpo = (nome_usuario or login_limpo).strip()
        email_limpo = email_usuario.strip() if email_usuario else None

        comando = insert(Usuario).values(
            codigo_usuario=codigo_usuario,
            login_usuario=login_limpo,
            nome_usuario=nome_limpo,
            email_usuario=email_limpo,
            codigo_usuariogrupo=codigo_usuariogrupo,
            sigla_usuariogrupo=sigla_usuariogrupo.strip() if sigla_usuariogrupo else None,
            descricao_usuariogrupo=descricao_usuariogrupo.strip()
            if descricao_usuariogrupo
            else None,
            ativo=True,
            bloqueado=False,
        )

        comando = comando.on_conflict_do_update(
            index_elements=[Usuario.codigo_usuario],
            set_={
                "login_usuario": comando.excluded.login_usuario,
                "nome_usuario": comando.excluded.nome_usuario,
                "email_usuario": comando.excluded.email_usuario,
                "codigo_usuariogrupo": comando.excluded.codigo_usuariogrupo,
                "sigla_usuariogrupo": comando.excluded.sigla_usuariogrupo,
                "descricao_usuariogrupo": comando.excluded.descricao_usuariogrupo,
                "atualizado_em": literal_column(
                    "(CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')"
                ),
            },
        ).returning(Usuario)

        with self._banco.unidade_trabalho() as sessao:
            self._liberar_login_de_outro_codigo(sessao, codigo_usuario, login_limpo)
            usuario = sessao.execute(comando).scalar_one()
            return usuario

    @staticmethod
    def _liberar_login_de_outro_codigo(sessao: Any, codigo_usuario: int, login: str) -> None:
        """Aposenta o cadastro antigo quando o diretorio passa a numerar o login de outra forma.

        O diretorio e a fonte da verdade: o mesmo login com outro `codigo_usuario` significa que
        o diretorio mudou (outro servidor/ambiente) e o cadastro espelhado ficou desatualizado.
        O login e unico, entao sem isso o novo cadastro nunca e gravado e a auditoria, que
        referencia o usuario por chave estrangeira, para de funcionar. O cadastro antigo nao e
        apagado: fica inativo, com o login marcado, e seus logs e vinculos continuam intactos.
        """

        antigos = (
            sessao.execute(
                select(Usuario).where(
                    func.lower(Usuario.login_usuario) == login.casefold(),
                    Usuario.codigo_usuario != codigo_usuario,
                )
            )
            .scalars()
            .all()
        )
        for antigo in antigos:
            sufixo = f"~{antigo.codigo_usuario}"
            antigo.login_usuario = f"{antigo.login_usuario[: 100 - len(sufixo)]}{sufixo}"
            antigo.ativo = False
            antigo.motivo_bloqueio = (
                f"Substituido pelo codigo {codigo_usuario} do diretorio corporativo."
            )
            logger.warning(
                "Login %s mudou de codigo no diretorio (%s -> %s); cadastro antigo aposentado.",
                login,
                antigo.codigo_usuario,
                codigo_usuario,
            )
        if antigos:
            sessao.flush()

    def registrar_inicio_sessao(
        self,
        *,
        codigo_usuario: int,
        id_sessao: str,
        ip_origem: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        """Marca o usuario como online e atualiza rastreabilidade de acesso."""

        comando = (
            update(Usuario)
            .where(Usuario.codigo_usuario == codigo_usuario)
            .values(
                status_online=True,
                id_sessao_atual=id_sessao,
                ultimo_acesso=literal_column(
                    "(CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')"
                ),
                ultimo_ip=ip_origem[:50] if ip_origem else None,
                ultimo_user_agent=user_agent[:500] if user_agent else None,
                total_logins=Usuario.total_logins + 1,
                atualizado_em=literal_column(
                    "(CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')"
                ),
            )
        )
        try:
            with self._banco.unidade_trabalho() as sessao:
                sessao.execute(comando)
        except Exception as erro:
            logger.error(
                "Falha ao registrar inicio de sessao para usuario %s: %s", codigo_usuario, erro
            )

    def registrar_fim_sessao(
        self,
        *,
        codigo_usuario: int,
        id_sessao: str,
        remover_status_online: bool = True,
    ) -> None:
        """Desassocia a sessao atual e, se solicitado, define o usuario como offline."""

        valores: dict[str, Any] = {
            "atualizado_em": literal_column("(CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')"),
        }
        if remover_status_online:
            valores["status_online"] = False
            valores["id_sessao_atual"] = None

        condicoes = [Usuario.codigo_usuario == codigo_usuario]
        if not remover_status_online and id_sessao:
            condicoes.append(Usuario.id_sessao_atual == id_sessao)

        comando = update(Usuario).where(*condicoes).values(**valores)
        try:
            with self._banco.unidade_trabalho() as sessao:
                sessao.execute(comando)
        except Exception as erro:
            logger.error(
                "Falha ao registrar fim de sessao para usuario %s: %s", codigo_usuario, erro
            )

    def atualizar_foto_perfil(self, codigo_usuario: int, foto_perfil: str | None) -> None:
        """Atualiza a foto de perfil do usuario."""

        comando = (
            update(Usuario)
            .where(Usuario.codigo_usuario == codigo_usuario)
            .values(
                foto_perfil=foto_perfil,
                atualizado_em=literal_column(
                    "(CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')"
                ),
            )
        )
        with self._banco.unidade_trabalho() as sessao:
            sessao.execute(comando)

    def atualizar_perfil(
        self,
        codigo_usuario: int,
        *,
        nome_usuario: str | None = None,
        telefone_usuario: str | None = None,
        celular_usuario: str | None = None,
        cargo_usuario: str | None = None,
        departamento_usuario: str | None = None,
        unidade_filial: str | None = None,
        tema_preferido: str | None = None,
        modo_tema: str | None = None,
        idioma: str | None = None,
    ) -> Usuario | None:
        """Atualiza dados de perfil e preferencias (codigo_usuario e login_usuario sao estritamente imutaveis)."""

        valores: dict[str, Any] = {
            "atualizado_em": literal_column("(CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')"),
        }
        if nome_usuario is not None:
            valores["nome_usuario"] = nome_usuario.strip()
        if telefone_usuario is not None:
            valores["telefone_usuario"] = telefone_usuario.strip() or None
        if celular_usuario is not None:
            valores["celular_usuario"] = celular_usuario.strip() or None
        if cargo_usuario is not None:
            valores["cargo_usuario"] = cargo_usuario.strip() or None
        if departamento_usuario is not None:
            valores["departamento_usuario"] = departamento_usuario.strip() or None
        if unidade_filial is not None:
            valores["unidade_filial"] = unidade_filial.strip() or None
        if tema_preferido is not None:
            valores["tema_preferido"] = tema_preferido.strip()
        if modo_tema is not None:
            valores["modo_tema"] = modo_tema.strip().upper()
        if idioma is not None:
            valores["idioma"] = idioma.strip()

        comando = (
            update(Usuario)
            .where(Usuario.codigo_usuario == codigo_usuario)
            .values(**valores)
            .returning(Usuario)
        )
        with self._banco.unidade_trabalho() as sessao:
            res = sessao.execute(comando).scalar_one_or_none()
            if res is None:
                return None
            return {
                "codigo_usuario": res.codigo_usuario,
                "login_usuario": res.login_usuario,
                "nome_usuario": res.nome_usuario,
                "foto_perfil": res.foto_perfil,
                "status_online": res.status_online,
                "cargo_usuario": res.cargo_usuario,
                "departamento_usuario": res.departamento_usuario,
                "telefone_usuario": res.telefone_usuario,
                "celular_usuario": res.celular_usuario,
                "unidade_filial": res.unidade_filial,
                "tema_preferido": res.tema_preferido,
                "modo_tema": res.modo_tema,
                "idioma": res.idioma,
            }

    def atualizar_presenca(self, codigo_usuario: int, id_sessao: str | None = None) -> None:
        """Renova a presenca online do usuario e registra ultimo acesso em tempo real."""

        valores: dict[str, Any] = {
            "status_online": True,
            "ultimo_acesso": literal_column("(CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')"),
            "atualizado_em": literal_column("(CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')"),
        }
        if not id_sessao:
            return  # sem a sessao nao ha como saber se ela ainda esta ativa
        condicoes = [Usuario.codigo_usuario == codigo_usuario]
        if id_sessao:
            # Presenca so vale para uma sessao ATIVA: um poll que termina depois do logout (ou de
            # a sessao ser revogada) nao pode marcar o usuario como online de novo.
            condicoes.append(
                exists().where(
                    Sessao.id_sessao == id_sessao,
                    Sessao.codigo_usuario == codigo_usuario,
                    Sessao.status == "ATIVA",
                )
            )
            valores["id_sessao_atual"] = id_sessao

        comando = update(Usuario).where(*condicoes).values(**valores)
        try:
            with self._banco.unidade_trabalho() as sessao:
                sessao.execute(comando)
        except Exception as erro:
            logger.debug("Falha ao renovar presenca do usuario %s: %s", codigo_usuario, erro)

    def listar_sessoes_usuario(self, codigo_usuario: int) -> list[dict[str, Any]]:
        """Lista as sessoes ativas do usuario corporativo."""

        comando = (
            select(Sessao)
            .where(
                Sessao.codigo_usuario == codigo_usuario,
                Sessao.status == "ATIVA",
            )
            .order_by(Sessao.ultima_atividade.desc())
        )
        with self._banco.leitura() as sessao:
            linhas = sessao.execute(comando).scalars().all()
            return [
                {
                    "id_sessao": s.id_sessao,
                    "ip_origem": s.ip_origem,
                    "user_agent": s.user_agent,
                    "status": s.status,
                    "criada_em": s.criada_em.isoformat() if s.criada_em else None,
                    "ultima_atividade": s.ultima_atividade.isoformat()
                    if s.ultima_atividade
                    else None,
                    "expira_em": s.expira_em.isoformat() if s.expira_em else None,
                }
                for s in linhas
            ]

    def listar_historico_sessoes(self, codigo_usuario: int, limite: int = 30) -> list[dict[str, Any]]:
        """Historico de acessos do usuario: sessoes ativas e encerradas, da mais recente a mais antiga."""

        comando = (
            select(Sessao)
            .where(Sessao.codigo_usuario == codigo_usuario)
            .order_by(Sessao.criada_em.desc())
            .limit(max(1, min(limite, 100)))
        )
        with self._banco.leitura() as sessao:
            return [
                {
                    "id_sessao": s.id_sessao,
                    "ip_origem": s.ip_origem,
                    "user_agent": s.user_agent,
                    "status": s.status,
                    "criada_em": s.criada_em.isoformat() if s.criada_em else None,
                    "ultima_atividade": s.ultima_atividade.isoformat()
                    if s.ultima_atividade
                    else None,
                    "encerrada_em": s.encerrada_em.isoformat() if s.encerrada_em else None,
                    "motivo_encerramento": s.motivo_encerramento,
                }
                for s in sessao.execute(comando).scalars().all()
            ]

    def revogar_outras_sessoes(self, codigo_usuario: int, id_sessao_atual: str) -> int:
        """Revoga todas as outras sessoes ativas do usuario."""

        comando = (
            update(Sessao)
            .where(
                Sessao.codigo_usuario == codigo_usuario,
                Sessao.id_sessao != id_sessao_atual,
                Sessao.status == "ATIVA",
            )
            .values(
                status="REVOGADA",
            )
        )
        with self._banco.unidade_trabalho() as sessao:
            resultado = sessao.execute(comando)
            return int(resultado.rowcount or 0)


__all__ = ["RepositorioUsuariosPostgreSQL"]
