"""Testes dos caches de autorizacao sem Redis real."""

from flask import Flask

from luftbase.autorizacao.cache import CacheAutorizacaoRedis, CacheRequisicaoAutorizacao


class ArmazenamentoMemoria:
    def __init__(self) -> None:
        self.dados: dict[str, bytes] = {}
        self.ttls: dict[str, int] = {}

    def obter(self, chave: str) -> bytes | None:
        return self.dados.get(chave)

    def salvar(self, chave: str, valor: bytes, ttl_segundos: int) -> None:
        self.dados[chave] = valor
        self.ttls[chave] = ttl_segundos

    def remover(self, chave: str) -> None:
        self.dados.pop(chave, None)


def _cache(armazenamento: ArmazenamentoMemoria) -> CacheAutorizacaoRedis:
    return CacheAutorizacaoRedis(
        armazenamento,
        ttl_resultado_segundos=300,
        ttl_revisao_segundos=5,
    )


def test_cache_salva_revisao_e_lote_com_ttls_distintos() -> None:
    armazenamento = ArmazenamentoMemoria()
    cache = _cache(armazenamento)

    cache.salvar_revisao(7)
    cache.salvar_resultados(
        id_sistema=2,
        id_usuario=2759,
        id_grupo=7,
        revisao=7,
        resultados={"RELATORIOS.VER": True, "RELATORIOS.EDITAR": False},
    )

    assert cache.obter_revisao() == 7
    assert sorted(armazenamento.ttls.values()) == [5, 300]
    assert cache.obter_resultados(
        id_sistema=2,
        id_usuario=2759,
        id_grupo=7,
        revisao=7,
        chaves=("RELATORIOS.EDITAR", "RELATORIOS.VER"),
    ) == {"RELATORIOS.EDITAR": False, "RELATORIOS.VER": True}


def test_payload_corrompido_e_tratado_como_cache_miss() -> None:
    armazenamento = ArmazenamentoMemoria()
    cache = _cache(armazenamento)
    cache.salvar_revisao(1)
    chave_revisao = next(iter(armazenamento.dados))
    armazenamento.dados[chave_revisao] = b"invalida"

    assert cache.obter_revisao() is None
    assert chave_revisao not in armazenamento.dados


def test_cache_de_requisicao_nao_vaza_entre_contextos_flask() -> None:
    app = Flask(__name__)
    cache = CacheRequisicaoAutorizacao()

    with app.test_request_context("/primeira"):
        cache.salvar("usuario:permissao", False)
        assert cache.obter("usuario:permissao") is False

    with app.test_request_context("/segunda"):
        assert cache.obter("usuario:permissao") is None


def test_revisao_em_memoria_expira_e_enxerga_mudanca_de_outro_processo() -> None:
    """Sem Redis, dois processos so concordam se o TTL da revisao for respeitado."""

    from flask import Flask

    from luftbase.autorizacao.cache import CacheAutorizacaoRedis
    from luftbase.autorizacao.servico import ServicoAutorizacao
    from luftbase.identidade.modelos import UsuarioAutenticado
    from luftbase.infraestrutura.fabrica import ArmazenamentoSessoesMemoria

    class RepositorioCompartilhado:
        """Representa o PostgreSQL: a revisao e as regras mudam fora deste processo."""

        def __init__(self) -> None:
            self.revisao = 1
            self.concedido = False

        def consultar(self, **_: object) -> dict[str, bool]:
            return {"APP.PAINEL.VISUALIZAR": self.concedido}

        def obter_revisao(self) -> int:
            return self.revisao

        def incrementar_revisao(self) -> int:
            self.revisao += 1
            return self.revisao

    tempo = [1000.0]
    repositorio = RepositorioCompartilhado()
    servico = ServicoAutorizacao(
        id_sistema=1,
        repositorio=repositorio,  # type: ignore[arg-type]
        cache_distribuido=CacheAutorizacaoRedis(
            ArmazenamentoSessoesMemoria(relogio=lambda: tempo[0]),
            ttl_resultado_segundos=300,
            ttl_revisao_segundos=5,
        ),
    )
    usuario = UsuarioAutenticado(
        id_usuario=1, login="u", nome_completo="U", email=None, id_grupo=6, nome_grupo="TI"
    )
    app = Flask(__name__)

    with app.test_request_context():
        assert servico.possui(usuario, "APP.PAINEL.VISUALIZAR") is False

    # Outro processo (Workspace) concede a permissao e sobe a revisao no banco.
    repositorio.concedido = True
    repositorio.incrementar_revisao()
    tempo[0] += 6  # passa o TTL da revisao (5s)

    with app.test_request_context():
        assert servico.possui(usuario, "APP.PAINEL.VISUALIZAR") is True
