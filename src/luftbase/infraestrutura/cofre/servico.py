"""Conversao estrita de segredos do Vault em credenciais de banco e integracoes."""

from __future__ import annotations

from collections.abc import Mapping

from luftbase.configuracao.identificadores import (
    validar_esquema_aplicacao,
    validar_identificador_tecnico,
)
from luftbase.infraestrutura.cofre.contratos import ProvedorSegredos
from luftbase.infraestrutura.cofre.credenciais import (
    CredencialBanco,
    CredencialEmail,
    CredencialPostgresqlAplicacao,
    CredencialRedis,
    Segredo,
    SegurancaSmtp,
    TipoBanco,
)
from luftbase.integracoes.email.enderecos import (
    normalizar_enderecos_email,
    validar_endereco_email,
)
from luftbase.nucleo.excecoes import ErroCredencial, ErroEmail, SegredoNaoEncontrado

_USUARIOS_ADMINISTRATIVOS = frozenset({"admin", "postgres", "sa"})
_MODOS_SSL_POSTGRESQL = frozenset(
    {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"}
)


def _texto_obrigatorio(dados: Mapping[str, object], chave: str, caminho: str) -> str:
    valor_bruto = dados.get(chave)
    valor = "" if valor_bruto is None else str(valor_bruto).strip()
    if not valor:
        raise ErroCredencial(f"O segredo {caminho!r} nao possui o campo {chave!r}.")
    return valor


def _porta(dados: Mapping[str, object], caminho: str) -> int:
    valor = _texto_obrigatorio(dados, "porta", caminho)
    try:
        porta = int(valor)
    except ValueError as erro:
        raise ErroCredencial(f"A porta do segredo {caminho!r} deve ser numerica.") from erro
    if not 1 <= porta <= 65535:
        raise ErroCredencial(f"A porta do segredo {caminho!r} esta fora do intervalo valido.")
    return porta


def _inteiro(
    dados: Mapping[str, object],
    chave: str,
    caminho: str,
    *,
    minimo: int,
    maximo: int,
) -> int:
    valor = _texto_obrigatorio(dados, chave, caminho)
    try:
        resultado = int(valor)
    except ValueError as erro:
        raise ErroCredencial(
            f"O campo {chave!r} do segredo {caminho!r} deve ser numerico."
        ) from erro
    if not minimo <= resultado <= maximo:
        raise ErroCredencial(
            f"O campo {chave!r} do segredo {caminho!r} esta fora do intervalo valido."
        )
    return resultado


def _booleano(dados: Mapping[str, object], chave: str, caminho: str) -> bool:
    valor = dados.get(chave)
    if isinstance(valor, bool):
        return valor
    normalizado = str(valor or "").strip().casefold()
    if normalizado in {"true", "1"}:
        return True
    if normalizado in {"false", "0"}:
        return False
    raise ErroCredencial(f"O campo {chave!r} do segredo {caminho!r} deve ser true ou false.")


class CarregadorCredenciais:
    """Le e valida credenciais, mantendo o cliente Vault substituivel."""

    def __init__(self, provedor: ProvedorSegredos) -> None:
        self._provedor = provedor

    def carregar_banco(
        self,
        caminho: str,
        tipo_esperado: TipoBanco,
        *,
        exigir_esquema: bool = False,
        permitir_usuario_administrativo: bool = False,
    ) -> CredencialBanco:
        """Carrega uma credencial e rejeita inconsistencias antes da conexao."""

        dados = self._provedor.ler_segredo(caminho)
        tipo_informado = _texto_obrigatorio(dados, "tipo_banco", caminho).lower()
        aliases = {"mssql": TipoBanco.SQLSERVER, "sql_server": TipoBanco.SQLSERVER}
        try:
            tipo = (
                aliases[tipo_informado] if tipo_informado in aliases else TipoBanco(tipo_informado)
            )
        except ValueError as erro:
            raise ErroCredencial(
                f"O segredo {caminho!r} possui um tipo de banco desconhecido."
            ) from erro
        if tipo is not tipo_esperado:
            raise ErroCredencial(
                f"O segredo {caminho!r} nao corresponde ao tipo de banco esperado."
            )

        usuario = _texto_obrigatorio(dados, "usuario", caminho)
        if not permitir_usuario_administrativo and usuario.casefold() in _USUARIOS_ADMINISTRATIVOS:
            raise ErroCredencial(
                f"O segredo {caminho!r} usa uma conta administrativa proibida em runtime."
            )

        esquema_bruto = dados.get("esquema")
        esquema = None
        if exigir_esquema or esquema_bruto is not None and str(esquema_bruto).strip():
            esquema = validar_esquema_aplicacao(esquema_bruto)

        return CredencialBanco(
            tipo=tipo,
            host=_texto_obrigatorio(dados, "host", caminho),
            porta=_porta(dados, caminho),
            nome_banco=_texto_obrigatorio(dados, "nome_banco", caminho),
            usuario=usuario,
            senha=Segredo(_texto_obrigatorio(dados, "senha", caminho)),
            esquema=esquema,
            driver=str(dados.get("driver") or "").strip() or None,
        )

    def carregar_banco_composto(
        self,
        caminho_app: str,
        raiz_conexoes: str,
        tipo_esperado: TipoBanco = TipoBanco.POSTGRESQL,
        *,
        permitir_usuario_administrativo: bool = False,
    ) -> CredencialBanco:
        """Carrega segredo de aplicacao e combina com os dados de conexao compartilhada."""

        return self._carregar_postgresql_composto(
            caminho_app,
            raiz_conexoes,
            tipo_esperado,
            permitir_usuario_administrativo=permitir_usuario_administrativo,
        )[0]

    def carregar_aplicacao_postgresql(
        self,
        caminho_sistema: str,
        raiz_conexoes: str,
        *,
        sistema_id_esperado: int,
    ) -> CredencialPostgresqlAplicacao:
        """Carrega a credencial canonica e confere sua identidade de bootstrap."""

        credencial, dados_app = self._carregar_postgresql_composto(
            caminho_sistema,
            raiz_conexoes,
            TipoBanco.POSTGRESQL,
        )
        sistema_id = _inteiro(
            dados_app,
            "sistema_id",
            caminho_sistema,
            minimo=0,
            maximo=2_147_483_647,
        )
        if sistema_id != sistema_id_esperado:
            raise ErroCredencial(
                f"O segredo {caminho_sistema!r} pertence ao sistema {sistema_id}, "
                f"mas o bootstrap solicitou o sistema {sistema_id_esperado}."
            )
        identificador = validar_identificador_tecnico(
            _texto_obrigatorio(dados_app, "identificador", caminho_sistema)
        )
        return CredencialPostgresqlAplicacao(
            banco=credencial,
            identificador=identificador,
            sistema_id=sistema_id,
        )

    def _carregar_postgresql_composto(
        self,
        caminho_app: str,
        raiz_conexoes: str,
        tipo_esperado: TipoBanco,
        *,
        permitir_usuario_administrativo: bool = False,
    ) -> tuple[CredencialBanco, Mapping[str, object]]:
        """Le uma vez o segredo do sistema e o combina com a conexao indicada."""

        try:
            dados_app = self._provedor.ler_segredo(caminho_app)
        except SegredoNaoEncontrado:
            caminhos_alternativos: list[str] = []
            if "/aplicacoes/" in caminho_app and caminho_app.endswith("/postgresql"):
                caminhos_alternativos.append(
                    caminho_app.replace(
                        "/aplicacoes/", "/bancos/postgresql/aplicacoes/"
                    ).removesuffix("/postgresql")
                )
            if "/bancos/postgresql/sistemas/" in caminho_app:
                caminhos_alternativos.append(
                    caminho_app.replace("/bancos/postgresql/sistemas/", "/sistemas/")
                )
            elif "/sistemas/" in caminho_app and "/bancos/" not in caminho_app:
                caminhos_alternativos.append(
                    caminho_app.replace("/sistemas/", "/bancos/postgresql/sistemas/")
                )

            dados_app_encontrado: Mapping[str, object] | None = None
            for alt in caminhos_alternativos:
                try:
                    dados_app_encontrado = self._provedor.ler_segredo(alt)
                    caminho_app = alt
                    break
                except SegredoNaoEncontrado:
                    pass
            if dados_app_encontrado is None:
                raise
            dados_app = dados_app_encontrado

        alias_conexao = dados_app.get("conexao")
        driver: str | None
        if alias_conexao is not None and str(alias_conexao).strip():
            alias = str(alias_conexao).strip()
            caminho_conexao = f"{raiz_conexoes.rstrip('/')}/{alias}"
            try:
                dados_conexao = self._provedor.ler_segredo(caminho_conexao)
            except SegredoNaoEncontrado:
                alt_conexao: str | None = None
                if "/infraestrutura/postgresql/conexoes" in caminho_conexao:
                    alt_conexao = caminho_conexao.replace(
                        "/infraestrutura/postgresql/conexoes",
                        "/bancos/postgresql/conexoes",
                    )
                elif "/bancos/postgresql/conexoes" in caminho_conexao:
                    alt_conexao = caminho_conexao.replace(
                        "/bancos/postgresql/conexoes",
                        "/infraestrutura/postgresql/conexoes",
                    )
                if alt_conexao:
                    dados_conexao = self._provedor.ler_segredo(alt_conexao)
                    caminho_conexao = alt_conexao
                else:
                    raise
            tipo_informado = _texto_obrigatorio(
                dados_conexao, "tipo_banco", caminho_conexao
            ).lower()
            if tipo_informado != "postgresql":
                raise ErroCredencial(
                    f"O segredo de conexao {caminho_conexao!r} deve ser do tipo postgresql."
                )
            host = _texto_obrigatorio(dados_conexao, "host", caminho_conexao)
            porta = _porta(dados_conexao, caminho_conexao)
            nome_banco = _texto_obrigatorio(dados_conexao, "nome_banco", caminho_conexao)
            driver = str(dados_conexao.get("driver") or dados_app.get("driver") or "").strip()
            sslmode = str(dados_conexao.get("sslmode") or "prefer").strip().casefold()
        else:
            tipo_informado = _texto_obrigatorio(dados_app, "tipo_banco", caminho_app).lower()
            if tipo_informado != "postgresql":
                raise ErroCredencial(
                    f"O segredo {caminho_app!r} nao corresponde ao tipo de banco esperado."
                )
            host = _texto_obrigatorio(dados_app, "host", caminho_app)
            porta = _porta(dados_app, caminho_app)
            nome_banco = _texto_obrigatorio(dados_app, "nome_banco", caminho_app)
            driver = str(dados_app.get("driver") or "").strip() or None
            sslmode = str(dados_app.get("sslmode") or "prefer").strip().casefold()

        if sslmode not in _MODOS_SSL_POSTGRESQL:
            raise ErroCredencial(
                f"O segredo {caminho_app!r} possui um sslmode PostgreSQL invalido."
            )

        usuario = _texto_obrigatorio(dados_app, "usuario", caminho_app)
        if not permitir_usuario_administrativo and usuario.casefold() in _USUARIOS_ADMINISTRATIVOS:
            raise ErroCredencial(
                f"O segredo {caminho_app!r} usa uma conta administrativa proibida em runtime."
            )

        esquema_bruto = _texto_obrigatorio(dados_app, "esquema", caminho_app)
        esquema = validar_esquema_aplicacao(esquema_bruto)

        credencial = CredencialBanco(
            tipo=tipo_esperado,
            host=host,
            porta=porta,
            nome_banco=nome_banco,
            usuario=usuario,
            senha=Segredo(_texto_obrigatorio(dados_app, "senha", caminho_app)),
            esquema=esquema,
            driver=driver or None,
            sslmode=sslmode,
        )
        return credencial, dados_app

    def carregar_redis(self, caminho: str) -> CredencialRedis:
        """Carrega o Redis compartilhado e sua chave de assinatura."""

        dados = self._provedor.ler_segredo(caminho)
        tipo = str(dados.get("tipo_banco") or "redis").strip().casefold()
        if tipo != "redis":
            raise ErroCredencial(f"O segredo {caminho!r} nao corresponde ao tipo Redis esperado.")

        chave_assinatura = _texto_obrigatorio(
            dados,
            "chave_assinatura_sessao",
            caminho,
        )
        if len(chave_assinatura) < 32:
            raise ErroCredencial(
                "A chave de assinatura da sessao deve possuir ao menos 32 caracteres."
            )

        return CredencialRedis(
            host=_texto_obrigatorio(dados, "host", caminho),
            porta=_porta(dados, caminho),
            banco=_inteiro(dados, "banco", caminho, minimo=0, maximo=255),
            usuario=str(dados.get("usuario") or "").strip() or None,
            senha=Segredo(_texto_obrigatorio(dados, "senha", caminho)),
            tls=_booleano(dados, "tls", caminho),
            chave_assinatura_sessao=Segredo(chave_assinatura),
        )

    def carregar_email(self, caminho: str) -> CredencialEmail:
        """Carrega a conta SMTP do ambiente e valida cada campo antes do uso."""

        dados = self._provedor.ler_segredo(caminho)
        tipo = str(dados.get("tipo") or "smtp").strip().casefold()
        if tipo != "smtp":
            raise ErroCredencial(f"O segredo {caminho!r} nao corresponde ao tipo SMTP esperado.")

        seguranca_informada = _texto_obrigatorio(dados, "seguranca", caminho).casefold()
        try:
            seguranca = SegurancaSmtp(seguranca_informada)
        except ValueError as erro:
            aceitos = ", ".join(modo.value for modo in SegurancaSmtp)
            raise ErroCredencial(
                f"O campo 'seguranca' do segredo {caminho!r} deve ser um destes: {aceitos}."
            ) from erro

        usuario = _texto_obrigatorio(dados, "usuario", caminho)
        redirecionamento_bruto = dados.get("redirecionar_para")
        if redirecionamento_bruto is not None and not isinstance(
            redirecionamento_bruto, str | list | tuple
        ):
            raise ErroCredencial(
                f"O campo 'redirecionar_para' do segredo {caminho!r} deve ser texto ou lista."
            )
        try:
            remetente = validar_endereco_email(str(dados.get("remetente") or "").strip() or usuario)
            redirecionar_para = normalizar_enderecos_email(redirecionamento_bruto)
        except ErroEmail as erro:
            raise ErroCredencial(f"Segredo {caminho!r}: {erro}") from erro

        return CredencialEmail(
            host=_texto_obrigatorio(dados, "host", caminho),
            porta=_porta(dados, caminho),
            seguranca=seguranca,
            usuario=usuario,
            senha=Segredo(_texto_obrigatorio(dados, "senha", caminho)),
            remetente=remetente,
            nome_remetente=str(dados.get("nome_remetente") or "").strip() or None,
            redirecionar_para=redirecionar_para,
        )
