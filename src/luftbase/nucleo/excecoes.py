"""Excecoes publicas e estaveis da plataforma."""


class ErroLuftBase(Exception):
    """Classe base para erros controlados do LuftBase."""


class ErroConfiguracao(ErroLuftBase, ValueError):
    """Indica configuracao ausente, invalida ou contraditoria."""


class ErroInicializacao(ErroLuftBase, RuntimeError):
    """Indica que a plataforma nao pode ser instalada na aplicacao."""


class ErroCofre(ErroLuftBase, RuntimeError):
    """Indica uma falha controlada de configuracao ou acesso ao Vault."""


class AutenticacaoCofreInvalida(ErroCofre):
    """Indica que o token nao autenticou ou nao possui acesso ao segredo."""


class SegredoNaoEncontrado(ErroCofre):
    """Indica que um caminho esperado nao existe no Vault."""


class ErroCredencial(ErroLuftBase, ValueError):
    """Indica que uma credencial externa esta ausente ou inconsistente."""


class ErroConexaoBanco(ErroLuftBase, RuntimeError):
    """Indica falha controlada no uso de uma conexao de banco."""


class ErroAutenticacao(ErroLuftBase, RuntimeError):
    """Indica indisponibilidade ou configuracao invalida da autenticacao."""


class ErroAutorizacao(ErroLuftBase, RuntimeError):
    """Indica que uma decisao de autorizacao nao pode ser comprovada com seguranca."""


class ErroAuditoria(ErroLuftBase, RuntimeError):
    """Indica falha controlada ao persistir um evento de auditoria."""


class ErroSessao(ErroLuftBase, RuntimeError):
    """Indica falha segura no armazenamento ou contrato de sessao."""


class ErroConteudo(ErroLuftBase, ValueError):
    """Indica entrada ou transicao invalida de notificacao ou publicacao."""


class ConteudoNaoEncontrado(ErroConteudo):
    """Indica que o conteudo nao existe ou nao pertence a audiencia atual."""


class ErroEmail(ErroLuftBase, RuntimeError):
    """Indica mensagem invalida ou uso indevido da integracao de e-mail."""


class EmailNaoConfigurado(ErroEmail):
    """Indica que o segredo de e-mail nao existe no Vault do ambiente."""
