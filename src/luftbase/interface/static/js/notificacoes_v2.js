/**
 * LuftNotificacoes — painel de notificações do LuftBase.
 *
 * Lista a mais recente primeiro, agrupada por dia, com filtro por tipo, botão de ação em destaque
 * e "Limpar" com "Desfazer". Limpar some só para quem limpou: a notificação continua no sistema.
 */
const LuftNotificacoes = {

    /** Endpoint base da API de notificações. */
    _endpoint: (window.LUFT_RAIZ || '') + '/_luftbase/notificacoes',

    _pollingIntervalMs: 30000,
    _pollingTimer: 0,

    /** 'todas' | 'nao_lidas' */
    _filtroAtivo: 'todas',
    /** 'todas' ou uma categoria (ex.: 'SEGURANCA'); filtra o que já foi carregado. */
    _categoria: 'todas',

    _tamanhoPagina: 20,
    _limite: 20,
    _carregando: false,
    _temMaisPaginas: false,

    /** Notificações carregadas, da mais recente para a mais antiga. */
    _itens: [],
    /** Última limpeza, para o "Desfazer": { ids: number[] }. */
    _ultimaLimpeza: null,
    _timerAviso: 0,

    _rotulosCategoria: {
        SEGURANCA: 'Segurança',
        COMUNICADO: 'Comunicado',
        ATUALIZACAO: 'Atualização',
        INTEGRACAO: 'Integração',
        CONFIGURACAO: 'Configuração',
        USUARIO: 'Usuário',
        BANCO: 'Banco de dados',
        SERVICO: 'Serviço',
        ETL: 'ETL',
        GERAL: 'Geral',
    },

    _iconesPadrao: {
        INFO: 'ph-info',
        SUCESSO: 'ph-check-circle',
        ALERTA: 'ph-warning',
        ERRO: 'ph-x-circle',
        SISTEMA: 'ph-gear',
    },

    // ==========================================
    // CICLO DE VIDA
    // ==========================================

    init: function() {
        if (!document.getElementById('luft-notif-drawer')) return;

        const configNode = document.getElementById('luftbase-notif-config');
        if (configNode) {
            try {
                const cfg = JSON.parse(configNode.textContent || '{}');
                this._endpoint = cfg.endpoint || this._endpoint;
                this._pollingIntervalMs = Math.max(cfg.polling_ms || 30000, 5000);
            } catch (_e) { /* mantém os padrões */ }
        }

        this._registrarListeners();
        this.atualizarBadge();
        this._iniciarPolling();
    },

    _registrarListeners: function() {
        const porId = (id) => document.getElementById(id);

        porId('luft-notif-backdrop')?.addEventListener('click', () => this.fecharDrawer());
        porId('luft-notif-close-btn')?.addEventListener('click', () => this.fecharDrawer());
        porId('luft-notif-mark-all-btn')?.addEventListener('click', () => this.marcarTodasComoLidas());
        porId('luft-notif-load-more-btn')?.addEventListener('click', () => this.carregarMais());
        porId('luft-notif-snackbar-desfazer')?.addEventListener('click', () => this.desfazer());

        document.querySelectorAll('.luft-notif-tab').forEach(tab => {
            tab.addEventListener('click', (e) => this.trocarTab(e.currentTarget.dataset.filtro || 'todas'));
        });

        // Menu "Limpar": as lidas ou todas.
        const botaoLimpar = porId('luft-notif-clear-btn');
        const menu = porId('luft-notif-clear-menu');
        if (botaoLimpar && menu) {
            botaoLimpar.addEventListener('click', (e) => {
                e.stopPropagation();
                this._alternarMenuLimpar(menu.hidden);
            });
            menu.addEventListener('click', (e) => {
                const opcao = e.target.closest('[data-limpar]');
                if (!opcao) return;
                this._alternarMenuLimpar(false);
                this.ocultarTodas(opcao.dataset.limpar === 'lidas');
            });
            document.addEventListener('click', (e) => {
                if (!menu.hidden && !e.target.closest('.luft-notif-menu-wrap')) this._alternarMenuLimpar(false);
            });
        }

        // Cliques dentro da lista (delegação): ações do item e o próprio cartão.
        porId('luft-notif-list')?.addEventListener('click', (e) => this._aoClicarNaLista(e));
        porId('luft-notif-filtros')?.addEventListener('click', (e) => {
            const chip = e.target.closest('[data-categoria]');
            if (chip) this.filtrarCategoria(chip.dataset.categoria);
        });

        document.addEventListener('keydown', (e) => {
            if (e.key !== 'Escape') return;
            const menu = document.getElementById('luft-notif-clear-menu');
            if (menu && !menu.hidden) { this._alternarMenuLimpar(false); return; }
            this.fecharDrawer();
        });
    },

    abrirDrawer: function() {
        document.getElementById('luft-notif-drawer')?.classList.add('open');
        document.getElementById('luft-notif-backdrop')?.classList.add('open');
        document.body.style.overflow = 'hidden';

        this._limite = this._tamanhoPagina;
        this._categoria = 'todas';
        this._itens = [];
        this.carregarNotificacoes(true);
        document.getElementById('luft-notif-drawer')?.focus({ preventScroll: true });
    },

    fecharDrawer: function() {
        document.getElementById('luft-notif-drawer')?.classList.remove('open');
        document.getElementById('luft-notif-backdrop')?.classList.remove('open');
        document.body.style.overflow = '';
        this._alternarMenuLimpar(false);
        this._esconderAviso();
    },

    // ==========================================
    // CARREGAMENTO
    // ==========================================

    trocarTab: function(filtro) {
        this._filtroAtivo = filtro;
        this._limite = this._tamanhoPagina;
        this._categoria = 'todas';
        document.querySelectorAll('.luft-notif-tab').forEach(tab => {
            tab.classList.toggle('ativo', tab.dataset.filtro === filtro);
        });
        this.carregarNotificacoes(true);
    },

    filtrarCategoria: function(categoria) {
        this._categoria = categoria || 'todas';
        this._renderizarLista();
    },

    /**
     * @param {boolean} mostrarCarregando - mostra o esqueleto (use false para recarregar sem "piscar").
     */
    carregarNotificacoes: function(mostrarCarregando) {
        if (this._carregando) return;
        this._carregando = true;

        const lista = document.getElementById('luft-notif-list');
        if (!lista) { this._carregando = false; return; }
        if (mostrarCarregando) lista.innerHTML = this._renderizarEsqueleto(4);

        const params = new URLSearchParams({ limite: String(this._limite) });
        if (this._filtroAtivo === 'nao_lidas') params.set('apenas_nao_lidas', 'true');

        fetch(`${this._endpoint}?${params.toString()}`)
            .then(res => {
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                return res.json();
            })
            .then(data => {
                const brutos = data.itens || data.dados || [];
                // Mais recente primeiro: pela data de criação (o id só desempata).
                this._itens = brutos
                    .map(n => this._normalizar(n))
                    .sort((a, b) => (new Date(b.criada) - new Date(a.criada)) || (b.id - a.id));
                this._temMaisPaginas = brutos.length >= this._limite && this._limite < 100;
                this._renderizarLista();
            })
            .catch(err => {
                console.error('[LuftNotificacoes] Erro ao carregar:', err);
                lista.innerHTML = this._renderizarVazio('erro');
                this._temMaisPaginas = false;
                this._atualizarBotaoCarregarMais();
            })
            .finally(() => { this._carregando = false; });
    },

    carregarMais: function() {
        if (!this._temMaisPaginas || this._carregando) return;
        this._limite = Math.min(this._limite + this._tamanhoPagina, 100);
        this.carregarNotificacoes(false);
    },

    atualizarBadge: function() {
        fetch(`${this._endpoint}/contagem`, { headers: { 'X-Background-Request': '1' } })
            .then(res => res.json())
            .then(data => this._setBadgeCount(data.contagem || 0))
            .catch(() => { /* silencioso */ });
    },

    // ==========================================
    // AÇÕES
    // ==========================================

    marcarComoLida: function(id, event) {
        if (event) event.stopPropagation();
        const item = this._itens.find(i => i.id === id);
        if (item) item.lida = true;
        this._renderizarLista();

        this._requisitar(`${id}/leitura`, 'PUT')
            .then(data => {
                if (data && data.contagem !== undefined) this._setBadgeCount(data.contagem);
                else this.atualizarBadge();
            })
            .catch(err => {
                console.error('[LuftNotificacoes] Erro ao marcar como lida:', err);
                this.carregarNotificacoes(false);
            });
    },

    marcarTodasComoLidas: function() {
        this._itens.forEach(i => { i.lida = true; });
        this._renderizarLista();
        this._requisitar('leitura-todas', 'PUT')
            .then(() => {
                this._setBadgeCount(0);
                if (this._filtroAtivo === 'nao_lidas') this.carregarNotificacoes(false);
            })
            .catch(err => {
                console.error('[LuftNotificacoes] Erro ao marcar todas:', err);
                this.carregarNotificacoes(false);
            });
    },

    /** Limpa UMA notificação da lista de quem clicou (continua no sistema e para as outras pessoas). */
    ocultar: function(id, event) {
        if (event) event.stopPropagation();
        const cartao = document.querySelector(`#luft-notif-list .luft-notif-item[data-id="${id}"]`);
        if (cartao) cartao.classList.add('saindo');

        this._requisitar(`${id}/ocultar`, 'POST')
            .catch(err => {
                // 404 = já não aparece para esta pessoa; some da tela do mesmo jeito.
                if (!(err && err.status === 404)) throw err;
                return null;
            })
            .then(data => {
                setTimeout(() => {
                    this._itens = this._itens.filter(i => i.id !== id);
                    this._renderizarLista();
                }, 180);
                if (data && data.contagem !== undefined) this._setBadgeCount(data.contagem);
                this._ultimaLimpeza = { ids: [id] };
                this._mostrarAviso('Notificação removida da sua lista.', true);
            })
            .catch(err => {
                console.error('[LuftNotificacoes] Erro ao limpar notificação:', err);
                if (cartao) cartao.classList.remove('saindo');
            });
    },

    /** Limpa a lista inteira (ou só as lidas) de quem clicou. Dá para desfazer por alguns segundos. */
    ocultarTodas: function(apenasLidas) {
        if (!this._itens.length) return;
        const sufixo = apenasLidas ? '?apenas_lidas=1' : '';

        this._requisitar(`ocultar-todas${sufixo}`, 'POST')
            .then(data => {
                const total = data.total_ocultadas || 0;
                this._ultimaLimpeza = { ids: data.ids || [] };
                if (data.contagem !== undefined) this._setBadgeCount(data.contagem);
                this.carregarNotificacoes(false);
                this._mostrarAviso(
                    total === 0
                        ? (apenasLidas ? 'Não há notificações lidas para limpar.' : 'Nada para limpar.')
                        : (total === 1 ? '1 notificação removida da sua lista.' : `${total} notificações removidas da sua lista.`),
                    total > 0
                );
            })
            .catch(err => console.error('[LuftNotificacoes] Erro ao limpar a lista:', err));
    },

    desfazer: function() {
        const ids = this._ultimaLimpeza && this._ultimaLimpeza.ids;
        if (!ids || !ids.length) { this._esconderAviso(); return; }
        this._esconderAviso();
        this._requisitar('restaurar', 'POST', { ids })
            .then(data => {
                this._ultimaLimpeza = null;
                if (data && data.contagem !== undefined) this._setBadgeCount(data.contagem);
                this.carregarNotificacoes(false);
            })
            .catch(err => console.error('[LuftNotificacoes] Erro ao desfazer:', err));
    },

    _aoClicarNaLista: function(e) {
        const botao = e.target.closest('[data-acao]');
        const cartao = e.target.closest('.luft-notif-item');
        if (!cartao) return;
        const id = Number(cartao.dataset.id);

        if (botao) {
            e.stopPropagation();
            if (botao.dataset.acao === 'ler') this.marcarComoLida(id);
            else if (botao.dataset.acao === 'ocultar') this.ocultar(id);
            return;
        }

        const cta = e.target.closest('a.luft-notif-cta');
        const item = this._itens.find(i => i.id === id);
        if (cta) {
            // O navegador segue o link; a leitura vai junto (keepalive evita perder o pedido na troca de página).
            if (item && !item.lida) this._requisitar(`${id}/leitura`, 'PUT', null, true).catch(() => {});
            return;
        }
        if (e.target.closest('a, button')) return;

        // Clique no cartão: abre o destino (se houver) e marca como lida.
        const link = cartao.querySelector('a.luft-notif-cta');
        if (item && !item.lida) {
            if (link) this._requisitar(`${id}/leitura`, 'PUT', null, true).catch(() => {});
            else this.marcarComoLida(id);
        }
        if (link) window.location.href = link.href;
    },

    // ==========================================
    // RENDERIZAÇÃO
    // ==========================================

    _normalizar: function(n) {
        const meta = n.metadados || {};
        let url = '';
        let textoLink = '';
        if (meta.acao_url) {
            url = String(meta.acao_url).replace('/_luftcore/publicacoes/', '/publicacoes/');
            textoLink = meta.texto_link || 'Abrir';
        } else if (meta.id_publicacao) {
            url = `/publicacoes/${meta.id_publicacao}`;
            textoLink = 'Ler publicação';
        }
        return {
            id: Number(n.id_notificacao || n.id),
            titulo: n.titulo || '',
            mensagem: n.mensagem || '',
            tipo: n.tipo || 'INFO',
            categoria: n.categoria || 'GERAL',
            icone: n.icone || '',
            lida: !!n.lida,
            criada: n.data_criacao,
            url: this._urlSegura(url),
            textoLink: textoLink,
        };
    },

    /** Só caminhos do próprio site ou http(s); nunca `javascript:` e afins. */
    _urlSegura: function(url) {
        if (!url) return '';
        if (url.startsWith('/') && !url.startsWith('//')) return url;
        if (/^https?:\/\//i.test(url)) return url;
        return '';
    },

    _renderizarLista: function() {
        const lista = document.getElementById('luft-notif-list');
        if (!lista) return;

        this._renderizarFiltros();
        let itens = this._itens;
        if (this._categoria !== 'todas') itens = itens.filter(i => i.categoria === this._categoria);

        if (!itens.length) {
            lista.innerHTML = this._renderizarVazio(this._categoria !== 'todas' ? 'filtro' : '');
        } else {
            let html = '';
            let grupoAtual = null;
            itens.forEach(item => {
                const grupo = this._grupoDoDia(item.criada);
                if (grupo !== grupoAtual) {
                    grupoAtual = grupo;
                    html += `<div class="luft-notif-grupo">${grupo}</div>`;
                }
                html += this._renderizarItem(item);
            });
            lista.innerHTML = html;
        }
        this._atualizarBotaoCarregarMais();
    },

    _renderizarFiltros: function() {
        const area = document.getElementById('luft-notif-filtros');
        if (!area) return;
        const categorias = [...new Set(this._itens.map(i => i.categoria))];
        if (categorias.length < 2) {
            area.hidden = true;
            area.innerHTML = '';
            if (this._categoria !== 'todas' && !categorias.includes(this._categoria)) this._categoria = 'todas';
            return;
        }
        const chip = (valor, rotulo) =>
            `<button type="button" class="luft-notif-chip ${this._categoria === valor ? 'ativo' : ''}" data-categoria="${this._attr(valor)}">${this._escape(rotulo)}</button>`;
        area.innerHTML = chip('todas', 'Todos os tipos') +
            categorias.map(c => chip(c, this._rotuloCategoria(c))).join('');
        area.hidden = false;
    },

    _renderizarItem: function(n) {
        const classeIcone = n.icone
            ? (n.icone.includes(' ') ? n.icone : `ph-fill ${n.icone}`)
            : `ph-fill ${this._iconesPadrao[n.tipo] || 'ph-bell'}`;
        const cta = n.url
            ? `<a class="luft-notif-cta" href="${this._attr(n.url)}">${this._escape(n.textoLink)} <i class="ph-bold ph-arrow-right"></i></a>`
            : '';
        const botaoLer = n.lida ? '' : `
            <button type="button" class="luft-notif-icon-btn" data-acao="ler" title="Marcar como lida" aria-label="Marcar como lida">
                <i class="ph-bold ph-check"></i>
            </button>`;

        return `
            <article class="luft-notif-item ${n.lida ? '' : 'nao-lida'}" data-id="${n.id}">
                <div class="luft-notif-icon tipo-${this._attr(n.tipo)}"><i class="${this._attr(classeIcone)}"></i></div>
                <div class="luft-notif-content">
                    <div class="luft-notif-topline">
                        <p class="luft-notif-title">${this._escape(n.titulo)}</p>
                        <time class="luft-notif-time" title="${this._attr(this._dataCompleta(n.criada))}">${this._escape(this._formatarTempoRelativo(n.criada))}</time>
                    </div>
                    <p class="luft-notif-message">${this._escape(n.mensagem)}</p>
                    <div class="luft-notif-foot">
                        <span class="luft-notif-meta-tag">${this._escape(this._rotuloCategoria(n.categoria))}</span>
                        ${cta}
                        <span class="luft-notif-acoes">
                            ${botaoLer}
                            <button type="button" class="luft-notif-icon-btn perigo" data-acao="ocultar" title="Limpar da minha lista" aria-label="Limpar da minha lista">
                                <i class="ph-bold ph-x"></i>
                            </button>
                        </span>
                    </div>
                </div>
            </article>`;
    },

    _renderizarEsqueleto: function(quantidade) {
        let html = '';
        for (let i = 0; i < quantidade; i++) {
            html += `
                <div class="luft-notif-skeleton">
                    <div class="luft-notif-skeleton-icon"></div>
                    <div class="luft-notif-skeleton-body">
                        <div class="luft-notif-skeleton-line w-60"></div>
                        <div class="luft-notif-skeleton-line w-90"></div>
                        <div class="luft-notif-skeleton-line w-40"></div>
                    </div>
                </div>`;
        }
        return html;
    },

    _renderizarVazio: function(motivo) {
        let icone = 'ph-bell-slash';
        let titulo = 'Nenhuma notificação';
        let texto = 'Quando houver atividade no sistema, as notificações aparecerão aqui.';
        if (motivo === 'erro') {
            icone = 'ph-wifi-slash';
            titulo = 'Não deu para carregar';
            texto = 'Verifique a conexão e abra o painel de novo.';
        } else if (motivo === 'filtro') {
            icone = 'ph-funnel';
            titulo = 'Nada neste tipo';
            texto = 'Escolha outro tipo ou volte para "Todos os tipos".';
        } else if (this._filtroAtivo === 'nao_lidas') {
            icone = 'ph-checks';
            titulo = 'Tudo lido!';
            texto = 'Você está em dia com as notificações.';
        }
        return `
            <div class="luft-notif-empty">
                <div class="luft-notif-empty-icon"><i class="ph-thin ${icone}"></i></div>
                <h4 class="luft-notif-empty-title">${titulo}</h4>
                <p class="luft-notif-empty-text">${texto}</p>
            </div>`;
    },

    _atualizarBotaoCarregarMais: function() {
        const rodape = document.getElementById('luft-notif-load-more');
        if (rodape) rodape.style.display = this._temMaisPaginas ? '' : 'none';
    },

    _setBadgeCount: function(count) {
        const texto = count > 99 ? '99+' : String(count);
        document.querySelectorAll(
            '.luft-notif-badge-topbar, .luft-notif-header-badge, .luft-badge-notif, #luft-notif-badge'
        ).forEach(badge => {
            badge.textContent = texto;
            badge.dataset.count = String(count);
            badge.style.display = count > 0 ? 'inline-flex' : 'none';
        });

        const contagemAba = document.querySelector('.luft-notif-tab[data-filtro="nao_lidas"] .luft-notif-tab-count');
        if (contagemAba) contagemAba.textContent = texto;

        const resumo = document.getElementById('luft-notif-resumo');
        if (resumo) {
            resumo.textContent = count > 0
                ? (count === 1 ? '1 não lida' : `${count} não lidas`)
                : 'Tudo em dia';
            resumo.classList.toggle('em-dia', count === 0);
        }
    },

    // ==========================================
    // AVISO COM "DESFAZER"
    // ==========================================

    _mostrarAviso: function(texto, comDesfazer) {
        const aviso = document.getElementById('luft-notif-snackbar');
        if (!aviso) return;
        document.getElementById('luft-notif-snackbar-texto').textContent = texto;
        document.getElementById('luft-notif-snackbar-desfazer').style.display = comDesfazer ? '' : 'none';
        aviso.hidden = false;
        clearTimeout(this._timerAviso);
        this._timerAviso = setTimeout(() => this._esconderAviso(), 8000);
    },

    _esconderAviso: function() {
        clearTimeout(this._timerAviso);
        const aviso = document.getElementById('luft-notif-snackbar');
        if (aviso) aviso.hidden = true;
    },

    _alternarMenuLimpar: function(abrir) {
        const menu = document.getElementById('luft-notif-clear-menu');
        const botao = document.getElementById('luft-notif-clear-btn');
        if (!menu || !botao) return;
        menu.hidden = !abrir;
        botao.setAttribute('aria-expanded', abrir ? 'true' : 'false');
    },

    // ==========================================
    // UTILITÁRIOS
    // ==========================================

    _iniciarPolling: function() {
        if (this._pollingTimer) clearInterval(this._pollingTimer);
        this._pollingTimer = setInterval(() => this.atualizarBadge(), this._pollingIntervalMs);
    },

    /** Chamada à API com CSRF. Rejeita com { status } quando o servidor não responde 2xx. */
    _requisitar: function(caminho, metodo, corpo, keepalive) {
        const token = document.querySelector('meta[name="luft-csrf-token"]')?.content || '';
        return fetch(`${this._endpoint}/${caminho}`, {
            method: metodo,
            keepalive: !!keepalive,
            headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': token },
            body: corpo ? JSON.stringify(corpo) : undefined,
        }).then(res => {
            if (!res.ok) return Promise.reject({ status: res.status });
            return res.json().catch(() => ({}));
        });
    },

    _rotuloCategoria: function(categoria) {
        return this._rotulosCategoria[categoria] || (categoria ? categoria.charAt(0) + categoria.slice(1).toLowerCase() : 'Geral');
    },

    /** 'Hoje', 'Ontem', 'Esta semana' ou 'Anteriores', pelo dia local do navegador. */
    _grupoDoDia: function(dataIso) {
        const data = new Date(dataIso);
        if (Number.isNaN(data.getTime())) return 'Anteriores';
        const hoje = new Date();
        hoje.setHours(0, 0, 0, 0);
        const dia = new Date(data);
        dia.setHours(0, 0, 0, 0);
        const dias = Math.round((hoje - dia) / 86400000);
        if (dias <= 0) return 'Hoje';
        if (dias === 1) return 'Ontem';
        if (dias < 7) return 'Esta semana';
        return 'Anteriores';
    },

    _dataCompleta: function(dataIso) {
        const data = new Date(dataIso);
        return Number.isNaN(data.getTime())
            ? ''
            : data.toLocaleString('pt-BR', { dateStyle: 'long', timeStyle: 'short' });
    },

    _formatarTempoRelativo: function(dataIso) {
        if (!dataIso) return '';
        const data = new Date(dataIso).getTime();
        if (Number.isNaN(data)) return '';
        const seg = Math.floor((Date.now() - data) / 1000);
        const min = Math.floor(seg / 60);
        const horas = Math.floor(min / 60);
        const dias = Math.floor(horas / 24);

        if (seg < 60) return 'agora';
        if (min < 60) return `há ${min} min`;
        if (horas < 24) return `há ${horas} h`;
        if (dias === 1) return 'ontem';
        if (dias < 7) return `há ${dias} dias`;
        if (dias < 30) return `há ${Math.floor(dias / 7)} sem`;
        return new Date(dataIso).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' });
    },

    _escape: function(texto) {
        if (texto === null || texto === undefined) return '';
        const el = document.createElement('span');
        el.textContent = String(texto);
        return el.innerHTML;
    },

    /** Para valores dentro de atributos HTML (escapa também as aspas). */
    _attr: function(texto) {
        return this._escape(texto).replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    },
};

window.LuftNotificacoes = LuftNotificacoes;

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => LuftNotificacoes.init());
} else {
    LuftNotificacoes.init();
}
