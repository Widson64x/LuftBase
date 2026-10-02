
// FORCED CSS PATCH TO BYPASS BROWSER CACHE
(function() {
    var style = document.createElement('style');
    style.innerHTML = `
        .luft-notif-item { background: transparent !important; }
        .luft-notif-item:hover { background: rgba(59, 130, 246, 0.05) !important; }
        .luft-notif-item.nao-lida { background: rgba(59, 130, 246, 0.08) !important; }
        .luft-notif-item.nao-lida:hover { background: rgba(59, 130, 246, 0.15) !important; }
    `;
    document.head.appendChild(style);
})();


/**
 * LuftNotificacoes — Sistema de notificações do LuftBase.
 *
 * Gerencia o drawer lateral de notificações, polling de contagem,
 * interações de leitura e renderização dinâmica da lista.
 */
const LuftNotificacoes = {

    /** @type {string} Endpoint base para API de notificações */
    _endpoint: (window.LUFT_RAIZ || '') + '/_luftbase/notificacoes',

    /** @type {number} Intervalo de polling para contagem (ms) */
    _pollingIntervalMs: 30000,

    /** @type {number} Timer ID do polling ativo */
    _pollingTimer: 0,

    /** @type {number} Página corrente para paginação */
    _paginaAtual: 1,

    /** @type {string} Filtro ativo: 'todas' ou 'nao_lidas' */
    _filtroAtivo: 'todas',

    /** @type {boolean} Se está carregando dados */
    _carregando: false,

    /** @type {boolean} Se há mais páginas disponíveis */
    _temMaisPaginas: true,

    /**
     * Inicializa o módulo de notificações.
     * Configura listeners, inicia polling e carrega a contagem inicial.
     */
    init: function() {
        const drawerHtml = document.getElementById('luft-notif-drawer');
        if (!drawerHtml) return;

        // Configurar endpoint customizado se disponível
        const configNode = document.getElementById('luftbase-notif-config');
        if (configNode) {
            try {
                const cfg = JSON.parse(configNode.textContent || '{}');
                this._endpoint = cfg.endpoint || this._endpoint;
                this._pollingIntervalMs = Math.max(cfg.polling_ms || 30000, 5000);
            } catch (_e) { /* ignora */ }
        }

        // Registrar listeners
        this._registrarListeners();

        // Carregar contagem inicial
        this.atualizarBadge();

        // Iniciar polling
        this._iniciarPolling();
    },

    /**
     * Registra event listeners para o drawer e itens de notificação.
     */
    _registrarListeners: function() {
        // Fechar ao clicar no backdrop
        const backdrop = document.getElementById('luft-notif-backdrop');
        if (backdrop) {
            backdrop.addEventListener('click', () => this.fecharDrawer());
        }

        // Botão de fechar
        const closeBtn = document.getElementById('luft-notif-close-btn');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => this.fecharDrawer());
        }

        // Tabs
        document.querySelectorAll('.luft-notif-tab').forEach(tab => {
            tab.addEventListener('click', (e) => {
                const filtro = e.currentTarget.dataset.filtro || 'todas';
                this.trocarTab(filtro);
            });
        });

        // Marcar todas como lidas
        const markAllBtn = document.getElementById('luft-notif-mark-all-btn');
        if (markAllBtn) {
            markAllBtn.addEventListener('click', () => this.marcarTodasComoLidas());
        }

        // Carregar mais
        const loadMoreBtn = document.getElementById('luft-notif-load-more-btn');
        if (loadMoreBtn) {
            loadMoreBtn.addEventListener('click', () => this.carregarMais());
        }

        // ESC para fechar
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') this.fecharDrawer();
        });
    },

    /**
     * Abre o drawer lateral de notificações.
     */
    abrirDrawer: function() {
        const drawer = document.getElementById('luft-notif-drawer');
        const backdrop = document.getElementById('luft-notif-backdrop');

        if (drawer) drawer.classList.add('open');
        if (backdrop) backdrop.classList.add('open');
        document.body.style.overflow = 'hidden';

        // Recarregar notificações ao abrir
        this._paginaAtual = 1;
        this._temMaisPaginas = true;
        this.carregarNotificacoes(true);
    },

    /**
     * Fecha o drawer lateral.
     */
    fecharDrawer: function() {
        const drawer = document.getElementById('luft-notif-drawer');
        const backdrop = document.getElementById('luft-notif-backdrop');

        if (drawer) drawer.classList.remove('open');
        if (backdrop) backdrop.classList.remove('open');
        document.body.style.overflow = '';
    },

    /**
     * Troca a aba ativa (Todas / Não lidas).
     * @param {string} filtro - 'todas' ou 'nao_lidas'
     */
    trocarTab: function(filtro) {
        this._filtroAtivo = filtro;
        this._paginaAtual = 1;
        this._temMaisPaginas = true;

        // Atualizar visual das tabs
        document.querySelectorAll('.luft-notif-tab').forEach(tab => {
            tab.classList.toggle('ativo', tab.dataset.filtro === filtro);
        });

        this.carregarNotificacoes(true);
    },

    /**
     * Carrega notificações da API.
     * @param {boolean} substituir - Se true, substitui a lista; se false, appenda.
     */
    carregarNotificacoes: function(substituir) {
        if (this._carregando) return;
        this._carregando = true;

        const lista = document.getElementById('luft-notif-list');
        if (!lista) { this._carregando = false; return; }

        if (substituir) {
            lista.innerHTML = this._renderizarSkeletons(4);
        }

        const params = new URLSearchParams({
            pagina: String(this._paginaAtual),
            limite: '20',
        });

        if (this._filtroAtivo === 'nao_lidas') {
            params.set('apenas_nao_lidas', 'true');
        }

        fetch(`${this._endpoint}?${params.toString()}`)
            .then(res => res.json())
            .then(data => {
                let notificacoes = data.itens || data.dados || [];
                if (this._filtroAtivo === 'nao_lidas') {
                    notificacoes = notificacoes.filter(n => !n.lida);
                }

                if (substituir) {
                    lista.innerHTML = '';
                }

                if (notificacoes.length === 0 && substituir) {
                    lista.innerHTML = this._renderizarEmptyState();
                    this._temMaisPaginas = false;
                } else {
                    notificacoes.forEach(notif => {
                        lista.insertAdjacentHTML('beforeend', this._renderizarItem(notif));
                    });

                    this._temMaisPaginas = (data.itens || data.dados || []).length >= 20;
                }

                this._atualizarBotaoCarregarMais();
                this._registrarListenersItens();
            })
            .catch(err => {
                console.error('[LuftNotificacoes] Erro ao carregar:', err);
                if (substituir) {
                    lista.innerHTML = this._renderizarEmptyState('Erro ao carregar notificações');
                }
            })
            .finally(() => {
                this._carregando = false;
            });
    },

    /**
     * Carrega a próxima página de notificações.
     */
    carregarMais: function() {
        if (!this._temMaisPaginas || this._carregando) return;
        this._paginaAtual++;
        this.carregarNotificacoes(false);
    },

    /**
     * Marca uma notificação específica como lida.
     * @param {number} id - ID da notificação.
     * @param {Event} event - Evento do clique (para stopPropagation).
     */
    marcarComoLida: function(id, event) {
        if (event) event.stopPropagation();
        const token = document.querySelector('meta[name="luft-csrf-token"]')?.content || "";

        fetch(`${this._endpoint}/${id}/leitura`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': token,
            },
        })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'success' || data.alterada !== undefined) {
                    // Atualizar visualmente o item
                    const item = document.querySelector(`.luft-notif-item[data-id="${id}"]`);
                    if (item) {
                        item.classList.remove('nao-lida');
                        const markBtn = item.querySelector('.luft-notif-mark-btn');
                        if (markBtn) markBtn.remove();
                    }

                    // Se estiver na aba não lidas, remover o card suavemente
                    if (this._filtroAtivo === 'nao_lidas' && item) {
                        item.style.opacity = '0';
                        setTimeout(() => {
                            item.remove();
                            const lista = document.getElementById('luft-notif-list');
                            if (lista && !lista.querySelector('.luft-notif-item')) {
                                lista.innerHTML = this._renderizarEmptyState();
                            }
                        }, 200);
                    }

                    // Atualizar badge
                    if (data.contagem !== undefined) {
                        this._setBadgeCount(data.contagem);
                    } else {
                        this.atualizarBadge();
                    }
                }
            })
            .catch(err => console.error('[LuftNotificacoes] Erro ao marcar como lida:', err));
    },

    /**
     * Marca todas as notificações como lidas.
     */
    marcarTodasComoLidas: function() {
        const token = document.querySelector('meta[name="luft-csrf-token"]')?.content || "";

        fetch(`${this._endpoint}/leitura-todas`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': token,
            },
        })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'success') {
                    // Remover indicadores visuais de não lida
                    document.querySelectorAll('.luft-notif-item.nao-lida').forEach(item => {
                        item.classList.remove('nao-lida');
                        const markBtn = item.querySelector('.luft-notif-mark-btn');
                        if (markBtn) markBtn.remove();
                    });

                    this._setBadgeCount(0);

                    // Se estiver na aba de não lidas, recarregar
                    if (this._filtroAtivo === 'nao_lidas') {
                        this._paginaAtual = 1;
                        this.carregarNotificacoes(true);
                    }
                }
            })
            .catch(err => console.error('[LuftNotificacoes] Erro ao marcar todas:', err));
    },

    /**
     * Atualiza o badge de contagem via API.
     */
    atualizarBadge: function() {
        fetch(`${this._endpoint}/contagem`, {
            headers: { 'X-Background-Request': '1' }
        })
            .then(res => res.json())
            .then(data => {
                this._setBadgeCount(data.contagem || 0);
            })
            .catch(() => { /* silencioso */ });
    },

    // ==========================================
    // MÉTODOS PRIVADOS
    // ==========================================

    /**
     * Inicia o polling periódico de contagem.
     */
    _iniciarPolling: function() {
        if (this._pollingTimer) clearInterval(this._pollingTimer);
        this._pollingTimer = setInterval(() => this.atualizarBadge(), this._pollingIntervalMs);
    },

    /**
     * Atualiza os elementos de badge com a contagem.
     * @param {number} count
     */
    _setBadgeCount: function(count) {
        const badges = document.querySelectorAll(
            '.luft-notif-badge-topbar, .luft-notif-header-badge, .luft-badge-notif, #luft-notif-badge'
        );
        badges.forEach(badge => {
            badge.textContent = count > 99 ? '99+' : String(count);
            badge.dataset.count = String(count);
            badge.style.display = count > 0 ? 'inline-flex' : 'none';
        });

        // Atualizar tab count de não lidas
        const tabCountNaoLidas = document.querySelector('.luft-notif-tab[data-filtro="nao_lidas"] .luft-notif-tab-count');
        if (tabCountNaoLidas) {
            tabCountNaoLidas.textContent = count > 99 ? '99+' : String(count);
        }
    },

    /**
     * Renderiza um item de notificação como HTML.
     * @param {Object} notif - Dados da notificação.
     * @returns {string} HTML do item.
     */
    _renderizarItem: function(notif) {
        const id = notif.id_notificacao || notif.id;
        const classeNaoLida = notif.lida ? '' : 'nao-lida';
        const icone = notif.icone || 'ph-bell';
        const tipoClasse = `tipo-${notif.tipo || 'INFO'}`;
        const tempoRelativo = this._formatarTempoRelativo(notif.data_criacao);

        let linkUrl = '';
        let linkTexto = '';
        if (notif.metadados) {
            if (notif.metadados.acao_url) {
                linkUrl = String(notif.metadados.acao_url).replace('/_luftcore/publicacoes/', '/publicacoes/');
                linkTexto = notif.metadados.texto_link || 'Acessar';
            } else if (notif.metadados.id_publicacao) {
                linkUrl = `/publicacoes/${notif.metadados.id_publicacao}`;
                linkTexto = 'Ler publicação';
            }
        }

        let markBtnHtml = '';
        if (!notif.lida) {
            markBtnHtml = `
                <button class="luft-notif-mark-btn" onclick="LuftNotificacoes.marcarComoLida(${id}, event)" title="Marcar como lida">
                    <i class="ph-bold ph-check"></i>
                </button>
            `;
        }

        return `
            <div class="luft-notif-item ${classeNaoLida}" data-id="${id}">
                <div class="luft-notif-icon ${tipoClasse}">
                    <i class="ph-fill ${icone}"></i>
                </div>
                <div class="luft-notif-content">
                    <p class="luft-notif-title">${this._escape(notif.titulo)}</p>
                    <p class="luft-notif-message">${this._escape(notif.mensagem)}</p>
                    ${linkUrl ? `<a href="${this._escape(linkUrl)}" onclick="LuftNotificacoes.marcarComoLida(${id}, event)" class="luft-notif-link" style="font-size: 0.75rem; color: var(--hub-cor-destaque, #1d63d8); text-decoration: none; font-weight: 500; display: block; margin-bottom: 0.25rem;">${this._escape(linkTexto)} <i class="ph-bold ph-arrow-right"></i></a>` : ''}
                    <div class="luft-notif-meta">
                        <span class="luft-notif-meta-tag">
                            <i class="ph-bold ph-tag"></i>
                            ${this._escape(notif.categoria || 'GERAL')}
                        </span>
                        <span class="luft-notif-time">
                            <i class="ph ph-clock"></i>
                            ${tempoRelativo}
                        </span>
                    </div>
                </div>
                ${markBtnHtml}
            </div>
        `;
    },

    /**
     * Renderiza skeletons de carregamento.
     * @param {number} quantidade
     * @returns {string} HTML dos skeletons.
     */
    _renderizarSkeletons: function(quantidade) {
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
                </div>
            `;
        }
        return html;
    },

    /**
     * Renderiza o estado vazio.
     * @param {string} mensagem - Mensagem customizada.
     * @returns {string} HTML do empty state.
     */
    _renderizarEmptyState: function(mensagem) {
        const titulo = this._filtroAtivo === 'nao_lidas'
            ? 'Tudo lido!'
            : (mensagem || 'Nenhuma notificação');

        const subtitulo = this._filtroAtivo === 'nao_lidas'
            ? 'Você está em dia com todas as notificações.'
            : 'Quando houver atividade no sistema, as notificações aparecerão aqui.';

        const icone = this._filtroAtivo === 'nao_lidas'
            ? 'ph-checks'
            : 'ph-bell-slash';

        return `
            <div class="luft-notif-empty">
                <div class="luft-notif-empty-icon">
                    <i class="ph-thin ${icone}"></i>
                </div>
                <h4 class="luft-notif-empty-title">${titulo}</h4>
                <p class="luft-notif-empty-text">${subtitulo}</p>
            </div>
        `;
    },

    /**
     * Atualiza a visibilidade do botão "Carregar mais".
     */
    _atualizarBotaoCarregarMais: function() {
        const footer = document.getElementById('luft-notif-load-more');
        if (footer) {
            footer.style.display = this._temMaisPaginas ? '' : 'none';
        }
    },

    /**
     * Registra listeners nos itens de notificação recém-renderizados.
     */
    _registrarListenersItens: function() {
        document.querySelectorAll('.luft-notif-item.nao-lida').forEach(item => {
            if (item.dataset.hasClickListener) return;
            item.dataset.hasClickListener = 'true';
            item.addEventListener('click', (e) => {
                if (e.target.closest('.luft-notif-mark-btn, a, button')) return;
                const id = item.dataset.id;
                if (id) {
                    this.marcarComoLida(Number(id));
                    const link = item.querySelector('a.luft-notif-link');
                    if (link && link.href) {
                        window.location.href = link.href;
                    }
                }
            });
        });
    },

    /**
     * Converte uma data ISO em tempo relativo legível.
     * @param {string} dataIso - Data em formato ISO 8601.
     * @returns {string} Texto como "agora", "há 5 min", "há 2h", "ontem", etc.
     */
    _formatarTempoRelativo: function(dataIso) {
        if (!dataIso) return '';

        const agora = Date.now();
        const data = new Date(dataIso).getTime();
        const diffMs = agora - data;
        const diffSeg = Math.floor(diffMs / 1000);
        const diffMin = Math.floor(diffSeg / 60);
        const diffHoras = Math.floor(diffMin / 60);
        const diffDias = Math.floor(diffHoras / 24);

        if (diffSeg < 60) return 'agora';
        if (diffMin < 60) return `há ${diffMin} min`;
        if (diffHoras < 24) return `há ${diffHoras}h`;
        if (diffDias === 1) return 'ontem';
        if (diffDias < 7) return `há ${diffDias} dias`;
        if (diffDias < 30) return `há ${Math.floor(diffDias / 7)} sem`;

        const dataObj = new Date(dataIso);
        return dataObj.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' });
    },

    /**
     * Escapa HTML para prevenir XSS.
     * @param {string} str
     * @returns {string}
     */
    _escape: function(str) {
        if (!str) return '';
        const el = document.createElement('span');
        el.textContent = str;
        return el.innerHTML;
    },
};

// Auto-init quando o DOM estiver pronto
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => LuftNotificacoes.init());
} else {
    LuftNotificacoes.init();
}
