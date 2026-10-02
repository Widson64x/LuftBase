"""API publica do LuftBase."""

from luftbase._versao import __version__
from luftbase.autorizacao import (
    AcaoPermissao,
    PermissaoLuftBase,
    consultar_permissoes,
    exigir_alguma_permissao,
    exigir_permissao,
    tem_permissao,
)
from luftbase.autorizacao.catalogo import DefinicaoModulo
from luftbase.autorizacao.catalogo_aplicacao import (
    CatalogoAplicacao,
    PermissaoAplicacao,
    SistemaAplicacao,
)
from luftbase.conteudo import (
    CategoriaNotificacao,
    ItemNotaAtualizacao,
    NovaNotificacao,
    NovaPublicacao,
    PrioridadePublicacao,
    TipoAudiencia,
    TipoItemAtualizacao,
    TipoNotificacao,
    TipoPublicacao,
)
from luftbase.estrutura import DefinicaoModelo, OrigemDados, PoliticaEstrutura
from luftbase.integracoes.email import Anexo, ImagemEmbutida, ResultadoEnvio, enviar_email
from luftbase.interface import ManifestoTema, PreferenciaTema
from luftbase.interface.busca import ProvedorBusca, ResultadoBusca
from luftbase.interface.parametros import ParametroAplicacao
from luftbase.observabilidade import (
    SeveridadeAuditoria,
    ignorar_auditoria,
    ignorar_auditoria_requisicao,
    obter_id_correlacao,
    registrar_alteracao_auditoria,
    registrar_evento_auditoria,
    sem_log,
)
from luftbase.persistencia.core.preferencias import ModoTema
from luftbase.plataforma import EstadoPlataforma, PlataformaLuft, obter_luftbase
from luftbase.web.contexto import contexto_painel
from luftbase.web.respostas import (
    enfileirar_toast,
    exigir_ajax,
    mensagem_erro,
    mensagem_sucesso,
    resposta_api_erro,
    resposta_api_sucesso,
    resposta_json,
)

__all__ = [
    "AcaoPermissao",
    "Anexo",
    "CatalogoAplicacao",
    "EstadoPlataforma",
    "DefinicaoModelo",
    "DefinicaoModulo",
    "CategoriaNotificacao",
    "ImagemEmbutida",
    "ItemNotaAtualizacao",
    "ManifestoTema",
    "ModoTema",
    "NovaNotificacao",
    "NovaPublicacao",
    "OrigemDados",
    "ParametroAplicacao",
    "ProvedorBusca",
    "ResultadoBusca",
    "PlataformaLuft",
    "PermissaoAplicacao",
    "PermissaoLuftBase",
    "PrioridadePublicacao",
    "PreferenciaTema",
    "ResultadoEnvio",
    "PoliticaEstrutura",
    "SeveridadeAuditoria",
    "SistemaAplicacao",
    "TipoAudiencia",
    "TipoItemAtualizacao",
    "TipoNotificacao",
    "TipoPublicacao",
    "__version__",
    "consultar_permissoes",
    "contexto_painel",
    "enfileirar_toast",
    "enviar_email",
    "exigir_ajax",
    "exigir_alguma_permissao",
    "exigir_permissao",
    "ignorar_auditoria",
    "ignorar_auditoria_requisicao",
    "mensagem_erro",
    "mensagem_sucesso",
    "obter_id_correlacao",
    "obter_luftbase",
    "registrar_alteracao_auditoria",
    "registrar_evento_auditoria",
    "resposta_api_erro",
    "resposta_api_sucesso",
    "resposta_json",
    "sem_log",
    "tem_permissao",
]
