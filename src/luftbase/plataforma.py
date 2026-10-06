"""Extensao principal que orquestra os recursos instalados em uma aplicacao Flask."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING, Any

from flask import current_app
from flask_login import LoginManager

from luftbase.autorizacao.cache import CacheAutorizacaoRedis
from luftbase.autorizacao.catalogo import PermissaoLuftBase
from luftbase.autorizacao.catalogo_aplicacao import (
    CatalogoAplicacao,
    ErroCatalogo,
    pendencias_catalogo,
    sincronizar_catalogo_aplicacao,
)
from luftbase.autorizacao.repositorio import RepositorioAutorizacao
from luftbase.autorizacao.servico import ServicoAutorizacao
from luftbase.autorizacao.web import registrar_contexto_jinja
from luftbase.configuracao.caminhos_vault import CaminhosVault, resolver_caminhos_vault
from luftbase.configuracao.modelos import ConfiguracaoLuftBase
from luftbase.conteudo.repositorios import RepositorioNotificacoes, RepositorioPublicacoes
from luftbase.conteudo.servicos import ServicoNotificacoes, ServicoPublicacoes
from luftbase.conteudo.sinalizacao import SinalizadorConteudoRedis
from luftbase.conteudo.web import registrar_rotas_conteudo
from luftbase.estrutura import CatalogoEstruturas, DefinicaoModelo
from luftbase.identidade import (
    AutenticadorLdap,
    ConfiguracaoLdap,
    InterfaceSessaoCompartilhada,
    RepositorioUsuariosDiretorio,
    RepositorioUsuariosPostgreSQL,
    ServicoAutenticacao,
    TransporteLdap,
    carregar_usuario_sessao,
    descartar_cookie_lembrar,
)
from luftbase.identidade.armazenamento_postgresql import ArmazenamentoSessoesPostgreSQL
from luftbase.infraestrutura.banco.catalogo import CatalogoBancos
from luftbase.infraestrutura.banco.saude import ResultadoSaude
from luftbase.infraestrutura.fabrica import (
    ArmazenamentoSessoesMemoria,
    FabricaInfraestrutura,
    FabricaInfraestruturaPadrao,
    RecursosInfraestrutura,
)
from luftbase.integracoes.diagnostico import IntegracaoAplicacao
from luftbase.integracoes.email import ResultadoEnvio, ServicoEmail
from luftbase.interface.busca import ProvedorBusca
from luftbase.interface.parametros import ParametroAplicacao
from luftbase.nucleo.tempo import aplicar_fuso_do_processo
from luftbase.interface.repositorio import RepositorioPreferenciasTema
from luftbase.interface.servico import ServicoTemas, criar_registro_padrao
from luftbase.interface.web import registrar_interface_web
from luftbase.nucleo.excecoes import ErroInicializacao
from luftbase.observabilidade.arquivo_fisico import LoggerFisicoAuditoria
from luftbase.observabilidade.buffer_temp import BufferLogsTemporarios
from luftbase.observabilidade.metricas import RegistroMetricas
from luftbase.observabilidade.modelos import EventoDominio, SeveridadeAuditoria
from luftbase.observabilidade.repositorio import RepositorioAuditoria
from luftbase.observabilidade.servico import ServicoAuditoria
from luftbase.observabilidade.tecnico import LoggerTecnico, resumir_excecao
from luftbase.observabilidade.web import (
    IntegracaoObservabilidadeFlask,
    contexto_observabilidade,
    registrar_evento_auditoria,
)
from luftbase.persistencia.core.sistemas import RepositorioSistemas

if TYPE_CHECKING:
    from flask import Flask


@dataclass(frozen=True, slots=True)
class EstadoPlataforma:
    """Estado isolado de uma instalacao do LuftBase em uma aplicacao Flask."""

    configuracao: ConfiguracaoLuftBase
    caminhos_vault: CaminhosVault
    infraestrutura: RecursosInfraestrutura
    autenticacao: ServicoAutenticacao
    autorizacao: ServicoAutorizacao
    notificacoes: ServicoNotificacoes
    publicacoes: ServicoPublicacoes
    temas: ServicoTemas
    auditoria: ServicoAuditoria
    metricas: RegistroMetricas
    observabilidade: IntegracaoObservabilidadeFlask
    gerenciador_login: LoginManager
    estruturas: CatalogoEstruturas
    email: ServicoEmail
    parametros: tuple[ParametroAplicacao, ...] = ()
    buscas: tuple[ProvedorBusca, ...] = ()
    integracoes: tuple[IntegracaoAplicacao, ...] = ()

    @property
    def bancos(self) -> CatalogoBancos:
        """Atalho para as fronteiras diretorio, core e aplicacao."""

        return self.infraestrutura.bancos

    @property
    def usuarios_core(self) -> RepositorioUsuariosPostgreSQL:
        """Repositorio de usuarios corporativos persistidos em core.tb_usuario."""

        if self.autenticacao.repositorio_core is not None:
            return self.autenticacao.repositorio_core
        return RepositorioUsuariosPostgreSQL(self.bancos.core)


class PlataformaLuft:
    """Ponto unico de inicializacao da plataforma corporativa."""

    chave_extensao = "luftbase"

    def __init__(
        self,
        fabrica_infraestrutura: FabricaInfraestrutura | None = None,
        *,
        modelos: Iterable[DefinicaoModelo] = (),
        catalogo: CatalogoAplicacao | None = None,
        parametros: Iterable[ParametroAplicacao] = (),
        buscas: Iterable[ProvedorBusca] = (),
        integracoes: Iterable[IntegracaoAplicacao] = (),
    ) -> None:
        self._fabrica = fabrica_infraestrutura or FabricaInfraestruturaPadrao()
        self._modelos = tuple(modelos)
        self._catalogo = catalogo
        self._parametros = tuple(parametros)
        self._buscas = tuple(buscas)
        self._integracoes = tuple(integracoes)

    def inicializar(
        self,
        app: Flask,
        configuracao: ConfiguracaoLuftBase | None = None,
    ) -> EstadoPlataforma:
        """Valida a configuracao e registra um estado exclusivo no Flask."""

        aplicar_fuso_do_processo()
        if self.chave_extensao in app.extensions:
            raise ErroInicializacao("O LuftBase ja foi inicializado nesta aplicacao.")

        configuracao_resolvida = configuracao or ConfiguracaoLuftBase.de_ambiente(app.config)
        caminhos = resolver_caminhos_vault(
            ambiente=configuracao_resolvida.aplicacao.ambiente,
            sistema_id=configuracao_resolvida.aplicacao.sistema_id,
            namespace=configuracao_resolvida.cofre.namespace,
            conexao_diretorio=configuracao_resolvida.cofre.conexao_diretorio,
        )
        infraestrutura = self._fabrica.criar(configuracao_resolvida, caminhos)

        if hasattr(infraestrutura.bancos.core, "leitura"):
            repositorio_sistemas = RepositorioSistemas(infraestrutura.bancos.core)
            metadados = repositorio_sistemas.consultar_por_id(
                configuracao_resolvida.aplicacao.sistema_id
            )
            configuracao_enriquecida = configuracao_resolvida.com_metadados_sistema(
                metadados,
                identificador=infraestrutura.identificador_vault,
            )
        else:
            configuracao_enriquecida = configuracao_resolvida

        autenticacao = self._criar_autenticacao(configuracao_enriquecida, infraestrutura.bancos)
        autorizacao = self._criar_autorizacao(configuracao_enriquecida, infraestrutura)
        cache_efemero = (
            infraestrutura.armazenamento_sessoes
            if not isinstance(
                infraestrutura.armazenamento_sessoes,
                ArmazenamentoSessoesPostgreSQL,
            )
            else ArmazenamentoSessoesMemoria()
        )
        sinalizador_conteudo = SinalizadorConteudoRedis(cache_efemero)
        notificacoes = ServicoNotificacoes(
            configuracao_enriquecida.aplicacao.sistema_id,
            RepositorioNotificacoes(infraestrutura.bancos.core),
            sinalizador_conteudo,
        )
        publicacoes = ServicoPublicacoes(
            configuracao_enriquecida.aplicacao.sistema_id,
            RepositorioPublicacoes(infraestrutura.bancos.core),
            sinalizador_conteudo,
        )
        temas = ServicoTemas(
            RepositorioPreferenciasTema(infraestrutura.bancos.core),
            criar_registro_padrao(),
        )
        dir_logs = str(app.config.get("LUFT_LOG_DIR", "Logs"))
        logger_fisico = LoggerFisicoAuditoria(diretorio_logs=dir_logs, nome_arquivo="luftbase.log")
        buffer_temp = BufferLogsTemporarios(
            capacidade_maxima=1000,
            diretorio_arquivos=Path(dir_logs) / "temp",
        )

        auditoria = ServicoAuditoria(
            configuracao_enriquecida.aplicacao.sistema_id,
            RepositorioAuditoria(infraestrutura.bancos.core),
            logger_fisico=logger_fisico,
            buffer_temp=buffer_temp,
        )
        metricas = RegistroMetricas()
        logger_tecnico = LoggerTecnico(
            app.logger,
            logger_fisico=logger_fisico,
            buffer_temp=buffer_temp,
        )
        observabilidade = IntegracaoObservabilidadeFlask(auditoria, metricas, logger_tecnico)
        gerenciador_login = self._instalar_identidade(
            app,
            configuracao_enriquecida,
            infraestrutura,
        )
        estruturas = CatalogoEstruturas(infraestrutura.bancos, self._modelos)
        if self._catalogo is not None:
            self._garantir_catalogo(configuracao_enriquecida, infraestrutura, self._catalogo)
        email = self._criar_email(configuracao_enriquecida, infraestrutura, auditoria)
        for modelo in estruturas.verificar():
            if not modelo.existe:
                logging.getLogger("luftbase").warning(
                    "Tabela ausente: modelo=%s tabela=%s politica=%s. "
                    "Use 'flask estrutura verificar' e uma migracao ou criacao explicita.",
                    modelo.nome,
                    modelo.tabela,
                    modelo.politica.value,
                )
        estado = EstadoPlataforma(
            configuracao=configuracao_enriquecida,
            caminhos_vault=caminhos,
            infraestrutura=infraestrutura,
            autenticacao=autenticacao,
            autorizacao=autorizacao,
            notificacoes=notificacoes,
            publicacoes=publicacoes,
            temas=temas,
            auditoria=auditoria,
            metricas=metricas,
            observabilidade=observabilidade,
            gerenciador_login=gerenciador_login,
            estruturas=estruturas,
            email=email,
            parametros=self._parametros,
            buscas=self._buscas,
            integracoes=self._integracoes,
        )

        # O objeto por aplicacao impede vazamento de estado entre factories e testes Flask.
        app.extensions[self.chave_extensao] = estado
        app.config["LUFT_APLICACAO_NOME"] = configuracao_enriquecida.aplicacao.nome
        app.config["LUFT_AMBIENTE"] = configuracao_enriquecida.aplicacao.ambiente.value
        app.config["LUFT_SISTEMA_ID"] = configuracao_enriquecida.aplicacao.sistema_id
        registrar_contexto_jinja(app)
        registrar_rotas_conteudo(app)
        registrar_interface_web(app)
        app.context_processor(contexto_observabilidade)
        observabilidade.instalar(app)
        from werkzeug.middleware.proxy_fix import ProxyFix

        from luftbase.web import registrar_rotas_plataforma
        from luftbase.web.manutencao import registrar_middleware_manutencao

        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)  # type: ignore[method-assign]
        registrar_middleware_manutencao(app)
        registrar_rotas_plataforma(app)

        gerenciador_login.login_view = "Autenticacao.login"

        @gerenciador_login.unauthorized_handler
        def _usuario_nao_autorizado():  # type: ignore[no-untyped-def]
            from urllib.parse import urlsplit

            from flask import redirect, request, url_for

            # Com prefixo (SCRIPT_NAME), o destino precisa incluir a raiz da aplicacao.
            destino = request.script_root + request.full_path.rstrip("?")
            partes = urlsplit(destino)
            destino_seguro = (
                destino
                if not partes.scheme and not partes.netloc and destino.startswith("/")
                else None
            )
            return redirect(url_for("Autenticacao.login", next=destino_seguro))

        @app.teardown_appcontext
        def remover_sessoes(_erro: BaseException | None) -> None:
            estado.bancos.remover_sessoes_contextuais()

        def verificar_saude() -> tuple[dict[str, object], int]:
            resultados_bancos = estado.bancos.verificar_saude()
            inicio = perf_counter()
            redis_disponivel = estado.infraestrutura.armazenamento_sessoes.verificar_saude()
            resultado_redis = ResultadoSaude(
                dependencia="sessoes_redis",
                disponivel=redis_disponivel,
                latencia_ms=round((perf_counter() - inicio) * 1000, 2),
                codigo="ok" if redis_disponivel else "indisponivel",
            )
            resultados = (*resultados_bancos, resultado_redis)
            disponivel = all(resultado.disponivel for resultado in resultados)
            return (
                {
                    "status": "ok" if disponivel else "indisponivel",
                    "dependencias": [resultado.como_dict() for resultado in resultados],
                },
                200 if disponivel else 503,
            )

        app.add_url_rule(
            "/_luftbase/saude",
            endpoint="luftbase.saude",
            view_func=verificar_saude,
            methods=["GET"],
        )
        app.add_url_rule(
            "/_luftbase/prontidao",
            endpoint="luftbase.prontidao",
            view_func=verificar_saude,
            methods=["GET"],
        )

        def consultar_metricas() -> tuple[dict[str, object], int]:
            return estado.metricas.snapshot(), 200

        app.add_url_rule(
            "/_luftbase/metricas",
            endpoint="luftbase.metricas",
            view_func=consultar_metricas,
            methods=["GET"],
        )

        @app.errorhandler(403)
        def _tratar_403(erro: Any) -> Any:
            from flask import jsonify, render_template, request

            # A recusa por CSRF e a recusa por permissão chegam como 403; sem distinguir,
            # o usuário acredita que lhe falta acesso quando a página só ficou desatualizada.
            if "CSRF" in str(getattr(erro, "description", "")):
                mensagem = (
                    "A página ficou desatualizada (token de segurança ausente ou inválido). "
                    "Recarregue com Ctrl+F5 e tente novamente."
                )
            else:
                mensagem = "Acesso não autorizado."
            if (
                request.is_json
                or request.path.startswith(("/api/", "/_luftbase/"))
                or request.headers.get("Accept") == "application/json"
            ):
                return jsonify({"status": "error", "message": mensagem}), 403
            return render_template("luftbase/errors/403.html", error=mensagem), 403

        @app.errorhandler(404)
        def _tratar_404(erro: Any) -> Any:
            from flask import jsonify, render_template, request

            if (
                request.is_json
                or request.path.startswith(("/api/", "/_luftbase/"))
                or request.headers.get("Accept") == "application/json"
            ):
                return jsonify({"status": "error", "message": "Recurso não encontrado."}), 404
            return render_template("luftbase/errors/404.html", error="Página não encontrada."), 404

        @app.errorhandler(500)
        def _tratar_500(erro: Any) -> Any:
            from flask import g, jsonify, render_template, request

            # Servico sem console (NSSM/systemd) perdia o motivo do 500: grava onde e de que tipo
            # foi o erro no log fisico, sem mensagem nem valores.
            original = getattr(erro, "original_exception", None) or erro
            try:
                logger_tecnico.erro(
                    "erro_500",
                    original,
                    id_correlacao=getattr(g, "luftbase_id_correlacao", None),
                    dados={
                        "metodo": request.method,
                        "rota": request.path,
                        **resumir_excecao(original),
                    },
                )
            except Exception:  # registrar o erro nunca pode causar outro erro
                logging.getLogger("luftbase").exception("Falha ao registrar o erro 500")
            if (
                request.is_json
                or request.path.startswith(("/api/", "/_luftbase/"))
                or request.headers.get("Accept") == "application/json"
            ):
                return jsonify({"status": "error", "message": "Erro interno do servidor."}), 500
            return (
                render_template("luftbase/errors/500.html", error="Erro interno do servidor."),
                500,
            )

        def consultar_usuarios_online():  # type: ignore[no-untyped-def]
            from flask import abort, jsonify, request
            from flask_login import current_user

            from luftbase.identidade.modelos import UsuarioAutenticado
            from luftbase.web.escopo import resolver_escopo_sistema

            usuario = current_user._get_current_object()
            if not isinstance(usuario, UsuarioAutenticado):
                abort(401)

            try:
                autorizado = bool(
                    estado.autorizacao.possui(usuario, PermissaoLuftBase.SESSOES_VISUALIZAR)
                )
            except Exception:
                abort(503, description="Falha ao verificar autorização.")
            if not autorizado:
                abort(403)

            sistema_alvo = resolver_escopo_sistema(request.args.get("sistema_id"))

            armazenamento = estado.infraestrutura.armazenamento_sessoes
            if hasattr(armazenamento, "listar_usuarios_online"):
                usuarios = armazenamento.listar_usuarios_online(sistema_alvo)
                return (
                    jsonify({"status": "success", "total": len(usuarios), "usuarios": usuarios}),
                    200,
                )
            return jsonify({"status": "success", "total": 0, "usuarios": []}), 200

        app.add_url_rule(
            "/_luftbase/sessoes/online",
            endpoint="luftbase.sessoes_online",
            view_func=consultar_usuarios_online,
            methods=["GET"],
        )

        def revogar_sessao_ativa():  # type: ignore[no-untyped-def]
            from flask import abort, jsonify, request
            from flask_login import current_user

            from luftbase.identidade.modelos import UsuarioAutenticado
            from luftbase.interface.web import validar_csrf_requisicao
            from luftbase.web.escopo import resolver_escopo_sistema

            usuario = current_user._get_current_object()
            if not isinstance(usuario, UsuarioAutenticado):
                abort(401)

            validar_csrf_requisicao()

            try:
                autorizado = bool(
                    estado.autorizacao.possui(usuario, PermissaoLuftBase.SESSOES_REVOGAR)
                )
            except Exception:
                abort(503, description="Falha ao verificar autorização.")
            if not autorizado:
                abort(403)

            dados = request.get_json() or {}
            id_sessao = str(dados.get("IdSessao") or dados.get("id_sessao") or "").strip()
            if not id_sessao:
                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": "Identificador da sessão é obrigatório.",
                        }
                    ),
                    400,
                )

            resolver_escopo_sistema(dados.get("sistema_id"))

            armazenamento = estado.infraestrutura.armazenamento_sessoes
            if hasattr(armazenamento, "revogar"):
                armazenamento.revogar(id_sessao)
            return jsonify({"status": "success", "message": "Sessão revogada com sucesso."}), 200

        app.add_url_rule(
            "/_luftbase/sessoes/revogar",
            endpoint="luftbase.sessoes_revogar",
            view_func=revogar_sessao_ativa,
            methods=["POST"],
        )

        # Importacao local evita ciclo: os comandos consultam o estado da plataforma.
        from luftbase.cli import registrar_comandos

        registrar_comandos(app)
        return estado

    @staticmethod
    def _criar_autorizacao(
        configuracao: ConfiguracaoLuftBase,
        infraestrutura: RecursosInfraestrutura,
    ) -> ServicoAutorizacao:
        """Compoe consulta e caches sem executar SQL ou Redis antecipadamente."""

        politica = configuracao.autorizacao
        id_sistema = configuracao.aplicacao.sistema_id
        if id_sistema is None:
            raise ErroInicializacao("O id_sistema ainda nao foi resolvido.")
        cache_distribuido = (
            infraestrutura.armazenamento_sessoes
            if not isinstance(
                infraestrutura.armazenamento_sessoes,
                ArmazenamentoSessoesPostgreSQL,
            )
            else ArmazenamentoSessoesMemoria()
        )
        return ServicoAutorizacao(
            id_sistema=id_sistema,
            repositorio=RepositorioAutorizacao(infraestrutura.bancos.core),
            cache_distribuido=CacheAutorizacaoRedis(
                cache_distribuido,
                ttl_resultado_segundos=politica.ttl_resultado_segundos,
                ttl_revisao_segundos=politica.ttl_revisao_segundos,
            ),
            maximo_chaves_consulta=politica.maximo_chaves_consulta,
        )

    @staticmethod
    def _garantir_catalogo(
        configuracao: ConfiguracaoLuftBase,
        infraestrutura: RecursosInfraestrutura,
        catalogo: CatalogoAplicacao,
    ) -> None:
        """Confere o catalogo da aplicacao no core e grava apenas o que falta ou divergiu.

        E escrita de dados (DML) na role da aplicacao, nunca DDL: o cadastro do sistema vem do
        Workspace e a estrutura do core, das migrations.
        """

        id_sistema = configuracao.aplicacao.sistema_id
        if id_sistema == 0:
            raise ErroInicializacao(
                "O sistema 0 (Luft-Workspace) usa o catalogo do proprio LuftBase; "
                "nao informe `catalogo` na PlataformaLuft."
            )
        banco = infraestrutura.bancos.core
        engine = getattr(banco, "engine", None)
        if engine is None or engine.dialect.name != "postgresql":
            logging.getLogger("luftbase").info(
                "Catalogo da aplicacao nao verificado: core sem PostgreSQL (teste ou memoria)."
            )
            return
        try:
            catalogo.validar()
            with engine.connect() as conexao:
                pendencias = pendencias_catalogo(conexao, id_sistema, catalogo)
            if not pendencias:
                return
            with engine.begin() as conexao:
                sincronizar_catalogo_aplicacao(conexao, id_sistema, catalogo)
        except ErroCatalogo as erro:
            raise ErroInicializacao(f"Catalogo da aplicacao invalido: {erro}") from erro
        except Exception as erro:
            detalhe = str(getattr(erro, "orig", erro)).splitlines()[0][:300]
            raise ErroInicializacao(
                f"Nao foi possivel sincronizar o catalogo do sistema {id_sistema}: {detalhe}. "
                "A role da aplicacao precisa de SELECT, INSERT e UPDATE em core.tb_modulo e "
                "core.tb_permissao."
            ) from erro
        logging.getLogger("luftbase").warning(
            "Catalogo do sistema %s sincronizado (%s pendencia(s)): %s",
            id_sistema,
            len(pendencias),
            "; ".join(pendencias[:10]) + (" ..." if len(pendencias) > 10 else ""),
        )

    @staticmethod
    def _criar_email(
        configuracao: ConfiguracaoLuftBase,
        infraestrutura: RecursosInfraestrutura,
        auditoria: ServicoAuditoria,
    ) -> ServicoEmail:
        """Libera o e-mail com o nome do sistema como remetente e auditoria de cada envio."""

        def auditar(resultado: ResultadoEnvio) -> None:
            from flask import has_app_context

            acao = "EMAIL_ENVIADO" if resultado.sucesso else "EMAIL_FALHA"
            descricao = (
                f"E-mail '{resultado.assunto}' para {len(resultado.destinatarios)} destinatario(s)"
                + (" em modo teste" if resultado.redirecionado else "")
                + ("." if resultado.sucesso else f": {resultado.erro}")
            )
            severidade = (
                SeveridadeAuditoria.BAIXA if resultado.sucesso else SeveridadeAuditoria.MEDIA
            )
            dados = resultado.como_dict()
            if has_app_context():
                registrar_evento_auditoria(
                    acao=acao,
                    recurso="EMAIL",
                    descricao=descricao,
                    dados_novos=dados,
                    severidade=severidade,
                )
                return
            # Tarefas sem contexto Flask ainda deixam rastro, apenas sem identidade de usuario.
            auditoria.registrar_evento(
                EventoDominio(
                    acao=acao,
                    recurso="EMAIL",
                    descricao=descricao,
                    dados_novos=dados,
                    severidade=severidade,
                )
            )

        return ServicoEmail(
            infraestrutura.credencial_email,
            ambiente=configuracao.aplicacao.ambiente,
            nome_sistema=configuracao.aplicacao.nome,
            auditor=auditar,
        )

    @staticmethod
    def _criar_autenticacao(
        configuracao: ConfiguracaoLuftBase,
        bancos: CatalogoBancos,
    ) -> ServicoAutenticacao:
        """Compoe LDAP e diretorio sem abrir conexoes antecipadamente."""

        diretorio = configuracao.diretorio
        autenticador = AutenticadorLdap(
            ConfiguracaoLdap(
                servidor=diretorio.servidor,
                dominio=diretorio.dominio,
                transporte=TransporteLdap(diretorio.transporte),
                porta=diretorio.porta,
                timeout_segundos=diretorio.timeout_segundos,
            )
        )
        repositorio = RepositorioUsuariosDiretorio(bancos.diretorio)
        repositorio_core = RepositorioUsuariosPostgreSQL(bancos.core)
        return ServicoAutenticacao(autenticador, repositorio, repositorio_core)

    @staticmethod
    def _instalar_identidade(
        app: Flask,
        configuracao: ConfiguracaoLuftBase,
        infraestrutura: RecursosInfraestrutura,
    ) -> LoginManager:
        """Instala cookie, sessao compartilhada e Flask-Login por aplicacao."""

        politica = configuracao.sessao
        if politica.cookie_inseguro_permitido:
            logging.getLogger(__name__).warning(
                "Cookie de sessao SEM a flag Secure em producao (LUFT_PERMITIR_COOKIE_INSEGURO). "
                "Use somente em rede interna sem TLS e remova ao habilitar HTTPS."
            )
        chave_assinatura = infraestrutura.chave_assinatura_sessao.revelar()
        app.config.update(
            SESSION_COOKIE_NAME=politica.nome_cookie,
            SESSION_COOKIE_DOMAIN=politica.dominio_cookie,
            SESSION_COOKIE_PATH=politica.caminho_cookie,
            SESSION_COOKIE_HTTPONLY=True,
            SESSION_COOKIE_SECURE=politica.cookie_seguro,
            SESSION_COOKIE_SAMESITE=politica.same_site,
            PERMANENT_SESSION_LIFETIME=timedelta(minutes=politica.ttl_minutos),
            SESSION_REFRESH_EACH_REQUEST=True,
        )
        if not app.secret_key:
            app.secret_key = chave_assinatura
        app.session_interface = InterfaceSessaoCompartilhada(
            infraestrutura.armazenamento_sessoes,
            chave_assinatura,
        )

        gerenciador = LoginManager()
        gerenciador.session_protection = "basic"
        gerenciador.init_app(app)
        gerenciador.user_loader(carregar_usuario_sessao)
        descartar_cookie_lembrar(app)
        return gerenciador


def obter_luftbase() -> EstadoPlataforma:
    """Retorna o estado da plataforma associado a aplicacao Flask atual."""

    estado = current_app.extensions.get(PlataformaLuft.chave_extensao)
    if not isinstance(estado, EstadoPlataforma):
        raise ErroInicializacao("O LuftBase nao foi inicializado na aplicacao atual.")
    return estado
