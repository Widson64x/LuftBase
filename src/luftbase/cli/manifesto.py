"""Modelo e carregador do manifesto nao sensivel de provisionamento."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from luftbase.configuracao.ambientes import normalizar_ambiente
from luftbase.configuracao.identificadores import (
    validar_esquema_aplicacao,
    validar_identificador_tecnico,
)
from luftbase.nucleo.excecoes import ErroConfiguracao


@dataclass(frozen=True, slots=True)
class AplicacaoManifesto:
    """Definicao de uma aplicacao no manifesto de provisionamento."""

    sistema_id: int
    identificador: str
    esquema: str
    usuario: str


@dataclass(frozen=True, slots=True)
class ConexaoManifesto:
    """Definicao da conexao compartilhada no manifesto."""

    alias: str
    host: str
    porta: int
    nome_banco: str
    tipo_banco: str = "postgresql"
    sslmode: str = "prefer"


@dataclass(frozen=True, slots=True)
class ManifestoProvisionamento:
    """Manifesto completo nao sensivel para provisionamento do banco e cofre."""

    ambiente: str
    conexao: ConexaoManifesto
    aplicacoes: tuple[AplicacaoManifesto, ...]

    @classmethod
    def de_arquivo(cls, caminho: str | Path) -> ManifestoProvisionamento:
        """Carrega manifesto a partir de arquivo JSON ou YAML."""

        caminho_path = Path(caminho)
        if not caminho_path.is_file():
            raise ErroConfiguracao(f"O arquivo de manifesto {caminho!r} nao foi encontrado.")

        conteudo = caminho_path.read_text(encoding="utf-8")
        dados: dict[str, Any]
        if caminho_path.suffix.lower() in {".yaml", ".yml"}:
            try:
                import yaml  # type: ignore[import-untyped,import-not-found,unused-ignore]

                dados = yaml.safe_load(conteudo) or {}
            except ImportError:
                # Se PyYAML nao estiver instalado, tenta carregar como JSON
                try:
                    dados = json.loads(conteudo)
                except json.JSONDecodeError as erro:
                    raise ErroConfiguracao(
                        "PyYAML nao esta instalado e o arquivo nao e um JSON valido."
                    ) from erro
        else:
            try:
                dados = json.loads(conteudo)
            except json.JSONDecodeError as erro:
                raise ErroConfiguracao(
                    f"O manifesto {caminho!r} nao e um JSON valido: {erro}"
                ) from erro

        ambiente = normalizar_ambiente(dados.get("ambiente") or "").value

        dados_conexao = dados.get("conexao") or {}
        alias = str(dados_conexao.get("alias") or "").strip()
        host = str(dados_conexao.get("host") or "").strip()
        nome_banco = str(dados_conexao.get("nome_banco") or "").strip()
        if not alias or not host or not nome_banco:
            raise ErroConfiguracao("O manifesto deve conter alias, host e nome_banco na conexao.")

        try:
            porta = int(dados_conexao.get("porta") or 5432)
        except ValueError as erro:
            raise ErroConfiguracao("A porta da conexao no manifesto deve ser numerica.") from erro

        conexao = ConexaoManifesto(
            alias=alias,
            host=host,
            porta=porta,
            nome_banco=nome_banco,
            tipo_banco=str(dados_conexao.get("tipo_banco") or "postgresql").strip().lower(),
            sslmode=str(dados_conexao.get("sslmode") or "prefer").strip(),
        )

        lista_apps: list[AplicacaoManifesto] = []
        for item in dados.get("aplicacoes") or []:
            try:
                sistema_id = int(item.get("sistema_id"))
            except (TypeError, ValueError) as erro:
                raise ErroConfiguracao("sistema_id deve ser numerico no manifesto.") from erro
            identificador = validar_identificador_tecnico(item.get("identificador"))
            esquema = validar_esquema_aplicacao(item.get("esquema"))
            usuario = str(item.get("usuario") or "").strip()
            if not usuario:
                raise ErroConfiguracao(
                    f"O usuario PostgreSQL da aplicacao {identificador} e obrigatorio."
                )
            lista_apps.append(
                AplicacaoManifesto(
                    sistema_id=sistema_id,
                    identificador=identificador,
                    esquema=esquema,
                    usuario=usuario,
                )
            )

        if not lista_apps:
            raise ErroConfiguracao("O manifesto deve conter ao menos uma aplicacao.")

        return cls(
            ambiente=ambiente,
            conexao=conexao,
            aplicacoes=tuple(lista_apps),
        )
