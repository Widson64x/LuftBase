const LuftBase = {
    init: function() {
        this.habilitarMensagens = Boolean(window.LUFT_HABILITAR_MENSAGENS ?? true);
        this.catalogoMensagensStatus = {
            ...(window.LUFT_CATALOGO_MENSAGENS_STATUS || window.LUFT_STATUS_MESSAGES || {})
        };
        this.duracaoPadraoPopup = this._resolverInteiro(window.LUFT_STATUS_POPUP_DURATION, 8000);
        this.endpointMensagens = String(
            window.LUFT_ENDPOINT_MENSAGENS
            || window.LUFT_MESSAGE_BACKEND_ENDPOINT
            || (window.LUFT_RAIZ || '') + '/_luftbase/mensagens'
        );
        this.intervaloPollingMensagensMs = Math.max(
            this._resolverInteiro(
                window.LUFT_INTERVALO_POLLING_MENSAGENS_MS
                || window.LUFT_MESSAGE_BACKEND_POLL_INTERVAL_MS,
                15000,
            ),
            250,
        );
        this.cabecalhoOperacaoMensagens = String(
            window.LUFT_CABECALHO_OPERACAO_MENSAGENS
            || window.LUFT_MESSAGE_BACKEND_OPERATION_HEADER
            || 'X-LuftBase-Operacao-Id'
        );
        this._fetchNativo = typeof window.fetch === 'function' ? window.fetch.bind(window) : null;
        this._timerPollingMensagens = 0;
        this._promessaSincronizacaoMensagens = null;

        this.restaurarEstado();
        this.iniciarAnimacoes();
        this.configurarAlertas();
        this.configurarCompatibilidadeLegada();
        this.configurarMonitorInatividade();
        this.configurarSeletorIconesDeclarativo();


        if (this.habilitarMensagens) {
            this.interceptarFetchGlobal();
            this.iniciarPollingMensagensBackend();
            void this.sincronizarMensagensBackend();
        }
    },

    toggleSidebar: function() {
        const sidebar = document.getElementById('luft-sidebar');
        if (!sidebar) return;
        sidebar.classList.toggle('collapsed');
        localStorage.setItem('luft-sidebar-collapsed', sidebar.classList.contains('collapsed'));
    },

    toggleMenu: function(btn) {
        const sidebar = document.getElementById('luft-sidebar');
        if (sidebar && sidebar.classList.contains('collapsed')) {
            this.toggleSidebar();
            window.setTimeout(() => this._toggleLogic(btn), 150);
            return;
        }
        this._toggleLogic(btn);
    },

    _toggleLogic: function(btn) {
        if (!btn) return;
        btn.classList.toggle('ativo');
        const submenu = btn.nextElementSibling;
        if (submenu) submenu.classList.toggle('aberto');
    },

    // ----------------------------------------------------------------------
    // Tema (familia de cores) e Modo (claro/escuro) sao eixos independentes.
    // - Tema: data-luft-theme   -> definirTema(id)
    // - Modo: data-theme/data-luft-mode -> alternarModo() / definirModo(modo)
    // Um tema pode suportar so um modo; nesse caso o modo e fixo e o botao fica
    // visivel, porem bloqueado.
    // ----------------------------------------------------------------------
    _catalogoTemas: null,

    _lerCatalogoTemas: function() {
        if (this._catalogoTemas) return this._catalogoTemas;
        const catalogo = {};
        try {
            const no = document.getElementById('luft-temas-config');
            const lista = no ? JSON.parse(no.textContent || '[]') : [];
            lista.forEach((tema) => { catalogo[tema.id] = tema; });
        } catch (_) { /* catalogo ausente: cai no padrao abaixo */ }
        if (!catalogo.luft) {
            catalogo.luft = { id: 'luft', nome: 'Luft Corporativo', modos: ['claro', 'escuro'] };
        }
        this._catalogoTemas = catalogo;
        return catalogo;
    },

    /** Estado atual lido do DOM: tema, modos suportados e se o modo esta bloqueado. */
    obterEstadoTema: function() {
        const html = document.documentElement;
        const id = html.dataset.luftTheme || 'luft';
        const catalogo = this._lerCatalogoTemas();
        const info = catalogo[id] || catalogo.luft;
        const modos = (info.modos && info.modos.length) ? info.modos : ['claro', 'escuro'];
        const modoAtual = html.getAttribute('data-theme') === 'dark' ? 'escuro' : 'claro';
        return {
            tema: id,
            nomeTema: info.nome || id,
            modos: modos,
            bloqueado: modos.length < 2,
            modoEfetivo: modoAtual,
            // Sem o atributo (template antigo de uma aplicacao), preserva o que ja esta na tela.
            modoPreferido: html.dataset.luftModoPreferido || modoAtual,
        };
    },

    /** Resolve 'sistema' pelo navegador e impoe o modo unico de temas bloqueados. */
    _resolverModoEfetivo: function(temaId, preferido) {
        const info = this._lerCatalogoTemas()[temaId] || this._lerCatalogoTemas().luft;
        if (info.modos && info.modos.length === 1) return info.modos[0];
        if (preferido === 'sistema') {
            const escuro = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
            return escuro ? 'escuro' : 'claro';
        }
        return preferido === 'escuro' ? 'escuro' : 'claro';
    },

    /** Aplica tema + preferencia de modo ao DOM (sem persistir). */
    aplicarTema: function(temaId, modoPreferido) {
        const catalogo = this._lerCatalogoTemas();
        const id = catalogo[temaId] ? temaId : 'luft';
        const info = catalogo[id];
        const modos = (info.modos && info.modos.length) ? info.modos : ['claro', 'escuro'];
        const efetivo = this._resolverModoEfetivo(id, modoPreferido);
        const dataTheme = efetivo === 'escuro' ? 'dark' : 'light';

        const html = document.documentElement;
        html.setAttribute('data-luft-theme', id);
        html.setAttribute('data-theme', dataTheme);
        html.setAttribute('data-luft-mode', efetivo);
        html.setAttribute('data-luft-modo-preferido', modoPreferido);
        html.setAttribute('data-luft-modos', modos.join(','));
        html.setAttribute('data-luft-modo-bloqueado', modos.length < 2 ? 'true' : 'false');
        if (document.body) {
            document.body.setAttribute('data-theme', dataTheme);
            document.body.setAttribute('data-luft-mode', efetivo);
        }
        this._atualizarIconesTema(dataTheme);
        this._atualizarBotaoModo();
        document.dispatchEvent(new CustomEvent('luft:tema-alterado', {
            detail: { tema: id, modoEfetivo: efetivo, modoPreferido: modoPreferido, bloqueado: modos.length < 2 },
        }));
        return efetivo;
    },

    /** Alterna entre claro e escuro. Em temas de modo unico o botao fica bloqueado. */
    alternarModo: function() {
        const estado = this.obterEstadoTema();
        if (estado.bloqueado) {
            this._avisarModoBloqueado(estado);
            return;
        }
        const novo = estado.modoEfetivo === 'escuro' ? 'claro' : 'escuro';
        this.definirModo(novo);
    },

    /** Define o modo ('claro' | 'escuro' | 'sistema') mantendo o tema atual. */
    definirModo: function(modo) {
        const estado = this.obterEstadoTema();
        if (estado.bloqueado) {
            this._avisarModoBloqueado(estado);
            return;
        }
        const permitido = ['claro', 'escuro', 'sistema'].includes(modo) ? modo : 'claro';
        const efetivo = this.aplicarTema(estado.tema, permitido);
        try {
            localStorage.setItem('luft-tema', efetivo === 'escuro' ? 'dark' : 'light');
            localStorage.setItem('luft-modo', efetivo);
        } catch (_) { /* armazenamento indisponivel */ }
        void this._persistirPreferenciaTema(estado.tema, permitido);
    },

    /** Troca a familia de cores mantendo a preferencia de modo guardada do usuario. */
    definirTema: function(temaId, opcoes = {}) {
        const estado = this.obterEstadoTema();
        const modoPreferido = opcoes.modo || estado.modoPreferido;
        this.aplicarTema(temaId, modoPreferido);
        if (opcoes.persistir !== false) {
            void this._persistirPreferenciaTema(temaId, modoPreferido);
        }
    },

    /** @deprecated Use alternarModo(): o botao alterna o MODO, nao o tema. */
    alternarTema: function() {
        if (!this._avisouAlternarTema) {
            this._avisouAlternarTema = true;
            console.warn('[LuftBase] alternarTema() foi renomeada para alternarModo(); o tema e o modo sao conceitos diferentes.');
        }
        this.alternarModo();
    },

    _avisarModoBloqueado: function(estado) {
        const unico = estado.modos[0] === 'escuro' ? 'escuro' : 'claro';
        const mensagem = `O tema ${estado.nomeTema} oferece apenas o modo ${unico}. Escolha outro tema para alternar entre claro e escuro.`;
        if (typeof this.toast === 'function') this.toast('Modo bloqueado', mensagem, 'info');
    },

    /** Reflete no botao do menu se a alternancia esta disponivel ou bloqueada. */
    _atualizarBotaoModo: function() {
        const estado = this.obterEstadoTema();
        const botoes = document.querySelectorAll('[data-luft-alternar-modo], .luft-btn-action[onclick*="alternarTema"], .luft-btn-action[onclick*="alternarModo"]');
        botoes.forEach((botao) => {
            botao.setAttribute('data-luft-alternar-modo', '');
            botao.classList.toggle('luft-btn-action--bloqueado', estado.bloqueado);
            if (estado.bloqueado) {
                botao.setAttribute('aria-disabled', 'true');
                const unico = estado.modos[0] === 'escuro' ? 'escuro' : 'claro';
                botao.title = `Modo fixo: o tema ${estado.nomeTema} oferece apenas o modo ${unico}`;
            } else {
                botao.removeAttribute('aria-disabled');
                botao.title = estado.modoEfetivo === 'escuro' ? 'Mudar para o modo claro' : 'Mudar para o modo escuro';
            }
        });
    },

    _persistirPreferenciaTema: async function(temaId, modoPreferido) {
        const endpoint = document.body?.dataset.luftPreferenciaUrl || "";
        const token = document.querySelector('meta[name="luft-csrf-token"]')?.content || "";
        if (!endpoint || !token) return;
        try {
            await fetch(endpoint, {
                method: "PUT",
                credentials: "same-origin",
                headers: { "Content-Type": "application/json", "X-CSRF-Token": token },
                body: JSON.stringify({
                    tema: temaId || document.documentElement.dataset.luftTheme || "luft",
                    modo: String(modoPreferido || "sistema").toUpperCase(),
                }),
                __luftDesabilitarMensagens: true,
                __luftDesabilitarLatencia: true,
            });
        } catch (_) {}
    },

    restaurarEstado: function() {
        // O servidor e a fonte da verdade do tema/modo (renderizados no <html>). Aqui so
        // se sincroniza a interface com esse estado; nada em localStorage sobrescreve a
        // preferencia salva nem um modo fixado pelo tema.
        const estado = this.obterEstadoTema();
        this.aplicarTema(estado.tema, estado.modoPreferido);

        if (localStorage.getItem('luft-sidebar-collapsed') === 'true') {
            const sidebar = document.getElementById('luft-sidebar');
            if (sidebar) sidebar.classList.add('collapsed');
        }
    },

    _atualizarIconesTema: function(tema) {
        const icons = document.querySelectorAll('.luft-btn-action i.ph-moon, .luft-btn-action i.ph-sun');
        icons.forEach((icon) => {
            icon.className = tema === 'dark' ? 'ph-bold ph-sun' : 'ph-bold ph-moon';
        });

        const logoImg = document.querySelector('.luft-logo-img');
        if (!logoImg) return;

        const novaSrc = tema === 'dark'
            ? logoImg.getAttribute('data-dark')
            : logoImg.getAttribute('data-light');
        if (novaSrc) {
            logoImg.src = novaSrc;
        }
    },

    iniciarAnimacoes: function() {
        const elementos = document.querySelectorAll('.luft-animate-slide-up');
        elementos.forEach((el, index) => {
            el.style.animationDelay = `${index * 0.1}s`;
        });
    },

    configurarAlertas: function() {
        document.querySelectorAll('.luft-toast').forEach((toast) => {
            window.setTimeout(() => this.fecharToast(toast), 6000);
        });

        document.querySelectorAll('.luft-status-popup').forEach((popup) => {
            this._agendarFechamentoStatusPopup(popup);
        });

        document.querySelectorAll('.luft-alert').forEach((alerta) => {
            window.setTimeout(() => {
                alerta.style.opacity = '0';
                window.setTimeout(() => {
                    if (alerta.parentNode) alerta.remove();
                }, 300);
            }, 6000);
        });
    },

    _resolverInteiro: function(valor, padrao) {
        const numero = Number.parseInt(valor ?? padrao, 10);
        return Number.isNaN(numero) ? padrao : numero;
    },

    _normalizarTipoMensagem: function(tipo) {
        const aliases = {
            error: 'danger',
            erro: 'danger',
            sucesso: 'success',
            alerta: 'warning',
            aviso: 'warning',
        };
        const tipoNormalizado = String(tipo || '').trim().toLowerCase();
        const tipoResolvido = aliases[tipoNormalizado] || tipoNormalizado;
        return ['success', 'danger', 'warning', 'info'].includes(tipoResolvido)
            ? tipoResolvido
            : 'info';
    },

    _tituloMensagemPadrao: function(tipo) {
        const titulos = {
            success: 'Operação concluída',
            danger: 'Erro crítico',
            warning: 'Monitoramento ativo',
            info: 'Informação do sistema',
        };
        return titulos[this._normalizarTipoMensagem(tipo)] || titulos.info;
    },

    _iconeMensagemPadrao: function(tipo) {
        const icones = {
            success: 'ph-check-circle',
            danger: 'ph-warning-octagon',
            warning: 'ph-warning-circle',
            info: 'ph-info',
        };
        return icones[this._normalizarTipoMensagem(tipo)] || icones.info;
    },

    _resolverPopupStatus: function(configuracao = {}) {
        const payload = typeof configuracao === 'string'
            ? { ...(this.catalogoMensagensStatus[configuracao] || {}), chave: configuracao }
            : { ...configuracao };

        const tipo = this._normalizarTipoMensagem(payload.tipo);
        let duracao = payload.duracao;
        if (duracao === undefined || duracao === null || duracao === '') {
            duracao = payload.persistente ? 0 : this.duracaoPadraoPopup;
        } else {
            duracao = this._resolverInteiro(duracao, this.duracaoPadraoPopup);
        }

        const persistente = Boolean(payload.persistente) || duracao === 0;

        return {
            chave: payload.chave || 'mensagem-customizada',
            titulo: payload.titulo || this._tituloMensagemPadrao(tipo),
            mensagem: String(payload.mensagem || '').trim(),
            tipo,
            icone: payload.icone || this._iconeMensagemPadrao(tipo),
            spinner: Boolean(payload.spinner),
            persistente,
            duracao: persistente ? 0 : duracao,
        };
    },

    _obterUrlEndpointMensagens: function() {
        try {
            return new URL(this.endpointMensagens, window.location.origin).toString();
        } catch (_error) {
            return this.endpointMensagens;
        }
    },

    _resolverUrlRecurso: function(resource) {
        if (resource instanceof Request) {
            return resource.url;
        }

        try {
            return new URL(String(resource || ''), window.location.origin).toString();
        } catch (_error) {
            return String(resource || '');
        }
    },

    _deveIgnorarInterceptacaoBackend: function(resource) {
        return this._resolverUrlRecurso(resource) === this._obterUrlEndpointMensagens();
    },

    _requisitarEndpointMensagens: async function(payload = null) {
        if (typeof this._fetchNativo !== 'function') {
            return null;
        }

        const options = {
            method: payload === null ? 'GET' : 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
                'X-Background-Request': '1',
            },
            credentials: 'same-origin',
        };

        if (payload !== null) {
            options.body = JSON.stringify(payload);
        }

        const response = await this._fetchNativo(this.endpointMensagens, options);
        if (!response.ok) {
            return null;
        }

        try {
            return await response.json();
        } catch (_error) {
            return null;
        }
    },

    _aplicarMensagemBackend: function(comando = {}) {
        const tipo = String(comando.tipo || comando.kind || '').trim().toLowerCase();
        const chavesParaFechar = Array.isArray(comando.chaves_para_fechar)
            ? comando.chaves_para_fechar
            : (Array.isArray(comando.dismiss_keys) ? comando.dismiss_keys : []);

        chavesParaFechar.forEach((chave) => this.fecharStatusPopupPorChave(chave, true));

        if (tipo === 'fechar_popup' || tipo === 'dismiss') {
            return;
        }

        if (comando.popup && typeof comando.popup === 'object') {
            this.mostrarPopupStatus(comando.popup);
        }
    },

    sincronizarMensagensBackend: async function() {
        if (!this.habilitarMensagens) {
            return [];
        }

        if (this._promessaSincronizacaoMensagens) {
            return this._promessaSincronizacaoMensagens;
        }

        this._promessaSincronizacaoMensagens = (async () => {
            const payload = await this._requisitarEndpointMensagens();
            const comandos = Array.isArray(payload?.comandos)
                ? payload.comandos
                : (Array.isArray(payload?.messages) ? payload.messages : []);
            comandos.forEach((comando) => this._aplicarMensagemBackend(comando));
            return comandos;
        })();

        try {
            return await this._promessaSincronizacaoMensagens;
        } finally {
            this._promessaSincronizacaoMensagens = null;
        }
    },

    iniciarPollingMensagensBackend: function() {
        if (!this.habilitarMensagens || this._timerPollingMensagens) {
            return;
        }

        this._timerPollingMensagens = window.setInterval(() => {
            void this.sincronizarMensagensBackend();
        }, this.intervaloPollingMensagensMs);
    },

    iniciarOperacaoBackend: async function(contexto = {}) {
        if (!this.habilitarMensagens) {
            return null;
        }

        const payload = await this._requisitarEndpointMensagens({
            acao: 'iniciar_operacao',
            contexto,
        });
        return payload?.id_operacao || payload?.operation_id || null;
    },

    finalizarOperacaoBackend: async function(idOperacao, sucesso = true) {
        if (!this.habilitarMensagens || !idOperacao) {
            return false;
        }

        const payload = await this._requisitarEndpointMensagens({
            acao: 'finalizar_operacao',
            id_operacao: idOperacao,
            sucesso,
        });
        return Boolean(payload?.finalizada ?? payload?.finished);
    },

    interceptarFetchGlobal: function() {
        if (!this.habilitarMensagens || window.__luftbaseFetchInterceptado || typeof window.fetch !== 'function') {
            return;
        }

        const originalFetch = this._fetchNativo || window.fetch.bind(window);
        this._fetchNativo = originalFetch;
        window.__luftbaseFetchInterceptado = true;

        window.fetch = async (resource, config) => {
            if (this._deveIgnorarInterceptacaoBackend(resource)) {
                return originalFetch(resource, config || {});
            }

            const requestConfig = { ...(config || {}) };
            const headers = new Headers(requestConfig.headers || (resource instanceof Request ? resource.headers : undefined) || {});
            const desabilitarMensagens = Boolean(requestConfig.__luftDesabilitarMensagens || requestConfig.__luftDisableMessages);
            const desabilitarLatencia = Boolean(requestConfig.__luftDesabilitarLatencia || requestConfig.__luftDisableLatency);
            const metodo = String(
                requestConfig.method || (resource instanceof Request ? resource.method : 'GET') || 'GET'
            ).toUpperCase();
            let idOperacao = null;

            delete requestConfig.__luftDesabilitarMensagens;
            delete requestConfig.__luftDisableMessages;
            delete requestConfig.__luftDesabilitarLatencia;
            delete requestConfig.__luftDisableLatency;
            requestConfig.headers = headers;

            if (!headers.has('X-Requested-With')) {
                headers.append('X-Requested-With', 'XMLHttpRequest');
            }

            try {
                if (!desabilitarMensagens && !desabilitarLatencia) {
                    idOperacao = await this.iniciarOperacaoBackend({
                        tipo: 'fetch',
                        metodo,
                        url: this._resolverUrlRecurso(resource),
                    });
                    if (idOperacao) {
                        headers.set(this.cabecalhoOperacaoMensagens, idOperacao);
                    }
                }

                const response = await originalFetch(resource, requestConfig);

                if (!desabilitarMensagens) {
                    void this.sincronizarMensagensBackend();
                }

                return response;
            } catch (error) {
                if (idOperacao) {
                    await this.finalizarOperacaoBackend(idOperacao, false);
                }
                if (!desabilitarMensagens) {
                    void this.sincronizarMensagensBackend();
                }
                throw error;
            }
        };
    },

    monitorarOperacaoBackend: async function(executor, opcoes = {}) {
        if (typeof executor !== 'function') {
            throw new TypeError('executor deve ser uma função assíncrona');
        }

        const desabilitarMensagens = Boolean(opcoes.desabilitarMensagens || opcoes.disableMessages);
        const desabilitarLatencia = Boolean(opcoes.desabilitarLatencia || opcoes.disableLatency);
        let idOperacao = null;

        try {
            if (!desabilitarMensagens && !desabilitarLatencia) {
                idOperacao = await this.iniciarOperacaoBackend(opcoes.contexto || opcoes.metadata || {});
            }

            const resultado = await executor();
            if (idOperacao) {
                await this.finalizarOperacaoBackend(idOperacao, true);
            }
            return resultado;
        } catch (error) {
            if (idOperacao) {
                await this.finalizarOperacaoBackend(idOperacao, false);
            }
            throw error;
        } finally {
            if (!desabilitarMensagens) {
                void this.sincronizarMensagensBackend();
            }
        }
    },

    monitorarOperacaoLenta: function(executor, opcoes = {}) {
        return this.monitorarOperacaoBackend(executor, opcoes);
    },

    configurarCompatibilidadeLegada: function() {
        const self = this;

        window.LuftMessageBridge = {
            show: function(message, tipo = 'info', opcoes = {}) {
                return self.notificar(message, tipo, opcoes.title || null, opcoes);
            },
            showStatusPopup: function(configuracao = {}) {
                return self.mostrarPopupStatus(configuracao);
            },
            alert: function(message) {
                return self.notificar(message, 'warning');
            },
        };

        window.NotificationSystem = {
            show: function(message, tipo = 'info', duracao = 3500) {
                return self.notificar(message, tipo, null, { duracao });
            },
            success: function(message, duracao = 3500) {
                return this.show(message, 'success', duracao);
            },
            warning: function(message, duracao = 5000) {
                return this.show(message, 'warning', duracao);
            },
            error: function(message, duracao = 6000) {
                return this.show(message, 'danger', duracao);
            },
            info: function(message, duracao = 3500) {
                return this.show(message, 'info', duracao);
            },
        };

        Object.defineProperty(window, 'showToast', {
            configurable: true,
            get() {
                return (message, tipo = 'success') => self.notificar(message, tipo);
            },
            set(_valorLegado) {
            },
        });

        window.alert = function(message) {
            return self.notificar(message, 'warning');
        };
    },

    notificar: function(mensagem, tipo = 'info', titulo = null, opcoes = {}) {
        const configuracao = (mensagem && typeof mensagem === 'object' && !Array.isArray(mensagem))
            ? { ...mensagem }
            : { ...opcoes, mensagem, tipo, titulo };
        return this.mostrarPopupStatus(configuracao);
    },

    mostrarPopup: function(mensagem, tipo = 'info', titulo = null, opcoes = {}) {
        return this.notificar(mensagem, tipo, titulo, opcoes);
    },

    toast: function(titulo, mensagem = null, tipo = 'info', opcoes = {}) {
        // Suporta tanto LuftBase.toast('Mensagem', 'success')
        // quanto LuftBase.toast('Titulo', 'Mensagem', 'success')
        if (arguments.length === 1) {
            return this.notificar(titulo, 'info');
        }
        if (arguments.length === 2 && ['info', 'success', 'warning', 'danger', 'error'].includes(mensagem)) {
            const t = mensagem === 'error' ? 'danger' : mensagem;
            return this.notificar(titulo, t);
        }
        const tipoFinal = tipo === 'error' ? 'danger' : tipo;
        return this.notificar(mensagem, tipoFinal, titulo, opcoes);
    },

    alerta: function(mensagem, tipo = 'info', titulo = null) {
        const t = tipo === 'error' ? 'danger' : tipo;
        return this.notificar(mensagem, t, titulo);
    },

    registrarMensagemStatus: function(chave, configuracao = {}) {
        if (!chave || typeof chave !== 'string') return null;
        this.catalogoMensagensStatus[chave] = { ...(configuracao || {}), chave };
        return this.obterMensagemStatus(chave);
    },

    obterMensagemStatus: function(chave = null, overrides = {}) {
        const base = chave ? (this.catalogoMensagensStatus[chave] || {}) : {};
        return this._resolverPopupStatus({ ...base, ...(overrides || {}), chave: overrides.chave || chave || base.chave });
    },

    mostrarMensagemStatus: function(chave, overrides = {}) {
        return this.mostrarPopupStatus({ ...(overrides || {}), chave });
    },

    mostrarPopupStatus: function(configuracao = {}) {
        const popupConfig = this._resolverPopupStatus(configuracao);
        if (!popupConfig.mensagem) {
            return null;
        }

        const container = this._obterContainerStatusPopups();
        if (!container) {
            return null;
        }

        if (popupConfig.chave) {
            const popupExistente = [...container.querySelectorAll('.luft-status-popup')].find(
                (item) => item.dataset.key === popupConfig.chave
            );
            if (popupExistente) {
                this.fecharStatusPopup(popupExistente, true);
            }
        }

        const popup = document.createElement('div');
        popup.className = `luft-status-popup luft-status-popup-${popupConfig.tipo} animate-slide-right`;
        if (popupConfig.spinner) {
            popup.classList.add('is-loading');
        }
        popup.dataset.key = popupConfig.chave;
        popup.dataset.duration = String(popupConfig.duracao);
        popup.dataset.persistent = popupConfig.persistente ? 'true' : 'false';
        popup.setAttribute('role', 'status');
        popup.onclick = () => this.fecharStatusPopup(popup);

        const media = document.createElement('div');
        media.className = 'luft-status-popup-media';
        if (popupConfig.spinner) {
            const spinner = document.createElement('span');
            spinner.className = 'luft-status-popup-spinner';
            spinner.setAttribute('aria-hidden', 'true');
            media.appendChild(spinner);
        } else {
            const icon = document.createElement('i');
            icon.className = `ph-fill ${popupConfig.icone}`;
            icon.setAttribute('aria-hidden', 'true');
            media.appendChild(icon);
        }

        const content = document.createElement('div');
        content.className = 'luft-status-popup-content';

        const title = document.createElement('span');
        title.className = 'luft-status-popup-title';
        title.textContent = popupConfig.titulo;

        const text = document.createElement('span');
        text.className = 'luft-status-popup-text';
        text.textContent = popupConfig.mensagem;

        const closeButton = document.createElement('button');
        closeButton.className = 'luft-status-popup-close';
        closeButton.type = 'button';
        closeButton.title = 'Fechar';
        closeButton.onclick = (event) => {
            event.stopPropagation();
            this.fecharStatusPopup(popup);
        };

        const closeIcon = document.createElement('i');
        closeIcon.className = 'ph-bold ph-x';
        closeButton.appendChild(closeIcon);

        content.appendChild(title);
        content.appendChild(text);
        popup.appendChild(media);
        popup.appendChild(content);
        popup.appendChild(closeButton);
        container.appendChild(popup);

        this._agendarFechamentoStatusPopup(popup);
        return popup;
    },

    _obterContainerStatusPopups: function() {
        let container = document.querySelector('.luft-status-popups-container');
        if (container || !document.body) {
            return container;
        }

        container = document.createElement('div');
        container.className = 'luft-status-popups-container';
        container.setAttribute('aria-live', 'polite');
        document.body.appendChild(container);
        return container;
    },

    _agendarFechamentoStatusPopup: function(popup) {
        if (!popup) return;
        const persistente = popup.dataset.persistent === 'true';
        const duracao = this._resolverInteiro(popup.dataset.duration, 0);
        if (persistente || duracao <= 0) {
            return;
        }

        const timeoutId = window.setTimeout(() => this.fecharStatusPopup(popup), duracao);
        popup.dataset.timeoutId = String(timeoutId);
    },

    fecharStatusPopup: function(popup, imediato = false) {
        if (!popup) return;

        const timeoutId = this._resolverInteiro(popup.dataset.timeoutId, 0);
        if (timeoutId > 0) {
            window.clearTimeout(timeoutId);
        }

        if (imediato) {
            if (popup.parentNode) popup.remove();
            return;
        }

        if (popup.classList.contains('luft-status-popup-closing')) return;

        popup.classList.add('luft-status-popup-closing');
        popup.style.opacity = '0';
        popup.style.transform = 'translateY(18px)';
        window.setTimeout(() => {
            if (popup.parentNode) popup.remove();
        }, 280);
    },

    fecharStatusPopupPorChave: function(chave, imediato = false) {
        const chaveNormalizada = String(chave || '').trim();
        if (!chaveNormalizada) return;

        document.querySelectorAll('.luft-status-popup').forEach((popup) => {
            if (popup.dataset.key === chaveNormalizada) {
                this.fecharStatusPopup(popup, imediato);
            }
        });
    },

    limparStatusPopups: function() {
        document.querySelectorAll('.luft-status-popup').forEach((popup) => this.fecharStatusPopup(popup));
    },

    fecharToast: function(toast) {
        if (!toast || toast.classList.contains('luft-toast-closing')) return;
        toast.classList.add('luft-toast-closing');
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(60px)';
        window.setTimeout(() => {
            if (toast.parentNode) toast.remove();
        }, 320);
    },

    abrirModal: function(id) {
        const modal = document.getElementById(id);
        const backdrop = document.getElementById(`${id}-backdrop`);
        if (modal && backdrop) {
            backdrop.classList.add('show');
            modal.classList.add('show');
            document.body.style.overflow = 'hidden';
        }
    },

    fecharModal: function(id) {
        const modal = document.getElementById(id);
        const backdrop = document.getElementById(`${id}-backdrop`);
        if (modal && backdrop) {
            backdrop.classList.remove('show');
            modal.classList.remove('show');
            document.body.style.overflow = '';
        }
    },

    abrirTab: function(btn, painelId) {
        const container = btn.closest('.luft-tabs');
        if (!container) return;
        container.querySelectorAll('.luft-tab-btn').forEach((botao) => botao.classList.remove('ativo'));
        btn.classList.add('ativo');
        const panel = document.getElementById(painelId);
        if (panel) {
            const panelContainer = panel.parentElement;
            if (panelContainer) {
                panelContainer.querySelectorAll('.luft-tab-panel').forEach((p) => p.classList.remove('ativo'));
            }
            panel.classList.add('ativo');
        }
    },

    toggleDropdown: function(id) {
        const menu = document.getElementById(`${id}-menu`);
        if (!menu) return;
        const isOpen = menu.classList.contains('open');
        document.querySelectorAll('.luft-dropdown-menu.open').forEach((item) => item.classList.remove('open'));
        if (!isOpen) menu.classList.add('open');
    },

    _fecharDropdowns: function(event) {
        if (!event.target.closest('.luft-dropdown')) {
            document.querySelectorAll('.luft-dropdown-menu.open').forEach((menu) => menu.classList.remove('open'));
        }
    },

    toggleAccordion: function(btn) {
        const item = btn.closest('.luft-accordion-item');
        if (!item) return;
        const body = item.querySelector('.luft-accordion-body');
        const isOpen = btn.classList.contains('aberto');
        btn.classList.toggle('aberto', !isOpen);
        if (body) body.classList.toggle('aberto', !isOpen);
    },

    abrirDrawer: function(id) {
        if (id === 'luft-notif-drawer' || id === 'luft-notificacoes-drawer') {
            if (window.LuftNotificacoes && typeof window.LuftNotificacoes.abrirDrawer === 'function') {
                window.LuftNotificacoes.abrirDrawer();
                return;
            }
        }
        const drawer = document.getElementById(id);
        const backdrop = document.getElementById(`${id}-backdrop`);
        if (drawer) drawer.classList.add('open');
        if (backdrop) backdrop.classList.add('open');
        document.body.style.overflow = 'hidden';
    },

    fecharDrawer: function(id) {
        if (id === 'luft-notif-drawer' || id === 'luft-notificacoes-drawer') {
            if (window.LuftNotificacoes && typeof window.LuftNotificacoes.fecharDrawer === 'function') {
                window.LuftNotificacoes.fecharDrawer();
                return;
            }
        }
        const drawer = document.getElementById(id);
        const backdrop = document.getElementById(`${id}-backdrop`);
        if (drawer) drawer.classList.remove('open');
        if (backdrop) backdrop.classList.remove('open');
        document.body.style.overflow = '';
    },

    copiarTexto: function(texto, btn) {
        const fallback = () => {
            const el = document.createElement('textarea');
            el.value = texto;
            el.style.position = 'fixed';
            el.style.opacity = '0';
            document.body.appendChild(el);
            el.select();
            document.execCommand('copy');
            document.body.removeChild(el);
        };

        if (navigator.clipboard && window.isSecureContext) {
            navigator.clipboard.writeText(texto).catch(fallback);
        } else {
            fallback();
        }

        if (!btn) return;

        const original = btn.innerHTML;
        btn.innerHTML = '<i class="ph-bold ph-check"></i> Copiado!';
        btn.classList.add('copied');
        window.setTimeout(() => {
            btn.innerHTML = original;
            btn.classList.remove('copied');
        }, 2000);
    },

    confirmar: function(id, callback) {
        this.abrirModal(id);
        const btn = document.getElementById(`${id}-confirm-btn`);
        if (!btn) return;

        const handler = () => {
            this.fecharModal(id);
            btn.removeEventListener('click', handler);
            if (typeof callback === 'function') callback();
        };
        btn.addEventListener('click', handler);
    },

    initFileUpload: function(inputId) {
        const input = document.getElementById(inputId);
        if (!input) return;

        const zone = input.closest('.luft-file-upload');
        const nameEl = zone ? zone.querySelector('.luft-file-name') : null;

        if (zone) {
            zone.addEventListener('click', (event) => {
                if (event.target !== input) input.click();
            });
            zone.addEventListener('dragover', (event) => {
                event.preventDefault();
                zone.classList.add('drag-over');
            });
            zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
            zone.addEventListener('drop', (event) => {
                event.preventDefault();
                zone.classList.remove('drag-over');
                if (!event.dataTransfer.files.length) return;

                try {
                    input.files = event.dataTransfer.files;
                } catch (_error) {
                }

                if (nameEl) {
                    nameEl.textContent = [...event.dataTransfer.files].map((file) => file.name).join(', ');
                    nameEl.classList.add('show');
                }
            });
        }

        input.addEventListener('change', () => {
            if (nameEl && input.files.length) {
                nameEl.textContent = [...input.files].map((file) => file.name).join(', ');
                nameEl.classList.add('show');
            }
        });
    },

    removerChip: function(btn) {
        const chip = btn.closest('.luft-chip');
        if (!chip) return;
        chip.style.transition = 'opacity 0.2s ease, transform 0.2s ease';
        chip.style.opacity = '0';
        chip.style.transform = 'scale(0.7)';
        window.setTimeout(() => {
            if (chip.parentNode) chip.remove();
        }, 220);
    },

    configurarMonitorInatividade: function() {
        if (!document.querySelector('.luft-user, .luft-sidebar, form[action*="logout"], form[action*="sair"]')) {
            return;
        }

        const TEMPO_INATIVIDADE_MS = 10 * 60 * 1000;
        let timerInatividade = null;

        const deslogar = () => {
            const formLogout = document.querySelector('form[action*="logout"], form[action*="sair"]');
            if (formLogout) {
                formLogout.submit();
            } else {
                window.location.href = (window.LUFT_RAIZ || '') + '/logout';
            }
        };

        const reiniciarTimer = () => {
            if (timerInatividade) {
                clearTimeout(timerInatividade);
            }
            timerInatividade = setTimeout(deslogar, TEMPO_INATIVIDADE_MS);
        };

        let ultimoRegistro = Date.now();
        const registrarAcao = () => {
            const agora = Date.now();
            if (agora - ultimoRegistro > 1000) {
                ultimoRegistro = agora;
                reiniciarTimer();
            }
        };

        ['mousemove', 'mousedown', 'keydown', 'touchstart', 'scroll', 'click'].forEach((evento) => {
            window.addEventListener(evento, registrarAcao, { passive: true });
        });

        reiniciarTimer();
    },

    // --------------------------------------------------------------------------
    // Componente Reutilizável: Seletor de Ícones Phosphor (240+ Ícones)
    // --------------------------------------------------------------------------
    _catalogoIcones: [
        // Logística, Transporte & Carga
        { value: 'ph-bold ph-truck', label: 'Caminhão', tags: 'transporte frete rota entrega veiculo frota logistica', categoria: 'logistica' },
        { value: 'ph-bold ph-forklift', label: 'Empilhadeira', tags: 'armazem estoque logistica carga palete movimentacao', categoria: 'logistica' },
        { value: 'ph-bold ph-warehouse', label: 'Armazém / CD', tags: 'galpao deposito centro distribuicao estoque predio', categoria: 'logistica' },
        { value: 'ph-bold ph-package', label: 'Pacote / Caixa', tags: 'encomenda volume carga produto caixa entrega', categoria: 'logistica' },
        { value: 'ph-bold ph-cube', label: 'Cubo / Carga', tags: 'volume bloco mercadoria dimensao cubagem', categoria: 'logistica' },
        { value: 'ph-bold ph-airplane-tilt', label: 'Aéreo Inclinado', tags: 'aviao voo carga aerea expresso rapido', categoria: 'logistica' },
        { value: 'ph-bold ph-airplane', label: 'Avião', tags: 'aeronave transporte internacional voo', categoria: 'logistica' },
        { value: 'ph-bold ph-boat', label: 'Navio / Marítimo', tags: 'embarcacao porto cabotagem mar conteiner navio', categoria: 'logistica' },
        { value: 'ph-bold ph-train', label: 'Trem / Ferrovia', tags: 'vagao trilho multimodal transporte ferrovia', categoria: 'logistica' },
        { value: 'ph-bold ph-car', label: 'Carro / Veículo', tags: 'automovel utilitario frota leve passageiro', categoria: 'logistica' },
        { value: 'ph-bold ph-navigation-arrow', label: 'Navegação / Rota', tags: 'direcao gps roteirizacao destino trajeto mapa', categoria: 'logistica' },
        { value: 'ph-bold ph-map-pin', label: 'Ponto no Mapa', tags: 'localizacao filial cliente entrega destino origem', categoria: 'logistica' },
        { value: 'ph-bold ph-map-trifold', label: 'Mapa Dobrado', tags: 'geografia regiao territorio malha rotas', categoria: 'logistica' },
        { value: 'ph-bold ph-path', label: 'Trajeto / Rota', tags: 'itinerario percurso caminho trajeto viagem', categoria: 'logistica' },
        { value: 'ph-bold ph-compass', label: 'Bússola', tags: 'orientacao direcao rumo coordenadas navegacao', categoria: 'logistica' },
        { value: 'ph-bold ph-gas-pump', label: 'Combustível / Posto', tags: 'abastecimento diesel gasolina consumo frota', categoria: 'logistica' },
        { value: 'ph-bold ph-traffic-cone', label: 'Cone / Ocorrência', tags: 'bloqueio transito atencao desvio pista', categoria: 'logistica' },
        { value: 'ph-bold ph-traffic-signal', label: 'Semáforo', tags: 'sinal transito controle fluxo parada siga', categoria: 'logistica' },
        { value: 'ph-bold ph-road-horizon', label: 'Rodovia / Estrada', tags: 'pista pedagio viagem trecho rodovia asfalto', categoria: 'logistica' },
        { value: 'ph-bold ph-gauge', label: 'Velocímetro / Medidor', tags: 'velocidade medicao telemetria tacografo indicador', categoria: 'logistica' },
        { value: 'ph-bold ph-speedometer', label: 'Tacômetro', tags: 'rpm motor desempenho telemetria rotacao', categoria: 'logistica' },
        { value: 'ph-bold ph-barricade', label: 'Barricada / Barreira', tags: 'bloqueio alfandega barreira fiscal posto controle', categoria: 'logistica' },
        { value: 'ph-bold ph-anchor', label: 'Âncora / Porto', tags: 'porto atracacao maritimo terminal cais', categoria: 'logistica' },
        { value: 'ph-bold ph-airplane-takeoff', label: 'Decolagem', tags: 'partida envio saida embarque despacho inicio', categoria: 'logistica' },
        { value: 'ph-bold ph-airplane-landing', label: 'Pouso / Chegada', tags: 'destino recebimento desembarque entrega fim', categoria: 'logistica' },

        // Dashboards, Métricas & BI
        { value: 'ph-bold ph-squares-four', label: 'Módulos (Grid)', tags: 'hub painel aplicacoes portal matriz geral', categoria: 'dashboard' },
        { value: 'ph-bold ph-chart-pie', label: 'Gráfico Pizza', tags: 'indicador porcentagem divisao participacao bi', categoria: 'dashboard' },
        { value: 'ph-bold ph-chart-pie-slice', label: 'Fatia de Gráfico', tags: 'segmento fatia detalhe metrica divisao', categoria: 'dashboard' },
        { value: 'ph-bold ph-chart-line-up', label: 'Gráfico Subindo', tags: 'crescimento evolucao faturamento metas kpi lucro', categoria: 'dashboard' },
        { value: 'ph-bold ph-chart-line-down', label: 'Gráfico Caindo', tags: 'queda reducao custo sinistro perdas prejuizo', categoria: 'dashboard' },
        { value: 'ph-bold ph-chart-bar', label: 'Gráfico Barras', tags: 'comparativo colunas dados estatistica volume', categoria: 'dashboard' },
        { value: 'ph-bold ph-chart-bar-horizontal', label: 'Barras Horizontais', tags: 'ranking comparacao desempenho ordenacao', categoria: 'dashboard' },
        { value: 'ph-bold ph-chart-donut', label: 'Gráfico Donut', tags: 'indicador anel distribuicao status rosca', categoria: 'dashboard' },
        { value: 'ph-bold ph-presentation-chart', label: 'Apresentação BI', tags: 'relatorio executivo reuniao diretoria kpi slide', categoria: 'dashboard' },
        { value: 'ph-bold ph-trend-up', label: 'Tendência Alta', tags: 'crescimento positivo alta ganho aceleracao', categoria: 'dashboard' },
        { value: 'ph-bold ph-trend-down', label: 'Tendência Baixa', tags: 'queda decrescente baixa prejuizo desaceleracao', categoria: 'dashboard' },
        { value: 'ph-bold ph-activity', label: 'Atividade / Pulso', tags: 'tempo real monitoramento batimento online operando', categoria: 'dashboard' },
        { value: 'ph-bold ph-pulse', label: 'Pulsação / Sensor', tags: 'iot sinal monitoramento telemetria sensor ritmo', categoria: 'dashboard' },
        { value: 'ph-bold ph-chart-polar', label: 'Gráfico Polar', tags: 'radar analise multicriterio desempenho teia', categoria: 'dashboard' },
        { value: 'ph-bold ph-graph', label: 'Grafo / Nós', tags: 'rede nos relacionamentos fluxo arvore conexoes', categoria: 'dashboard' },
        { value: 'ph-bold ph-table', label: 'Tabela / Planilha', tags: 'linhas colunas dados grid relatorio exportacao', categoria: 'dashboard' },
        { value: 'ph-bold ph-columns', label: 'Colunas', tags: 'layout divisao kanban estrutura colunas', categoria: 'dashboard' },
        { value: 'ph-bold ph-rows', label: 'Linhas / Registros', tags: 'listagem registros itens grade linhas', categoria: 'dashboard' },
        { value: 'ph-bold ph-kanban', label: 'Quadro Kanban', tags: 'tarefas esteira agil sprints fluxo cartoes', categoria: 'dashboard' },
        { value: 'ph-bold ph-funnel', label: 'Funil de Processos', tags: 'conversao etapas pipeline leads filtragem', categoria: 'dashboard' },

        // Gestão, Finanças & Negócios
        { value: 'ph-bold ph-briefcase', label: 'Maleta / Corporativo', tags: 'trabalho gestao empresa negocios administracao profissional', categoria: 'negocios' },
        { value: 'ph-bold ph-buildings', label: 'Filiais / CD', tags: 'empresas matriz filial armazem escritorio predio sedes', categoria: 'negocios' },
        { value: 'ph-bold ph-bank', label: 'Banco / Financeiro', tags: 'instituicao conta pagamento cobranca tesouraria saldo', categoria: 'negocios' },
        { value: 'ph-bold ph-calculator', label: 'Calculadora', tags: 'calculo contabilidade impostos frete orcamento soma', categoria: 'negocios' },
        { value: 'ph-bold ph-money', label: 'Dinheiro / Cédula', tags: 'valores faturamento caixa financeiro receita', categoria: 'negocios' },
        { value: 'ph-bold ph-receipt', label: 'Comprovante / Recibo', tags: 'nota fiscal fatura canhoto cte nfe comprovante cupom', categoria: 'negocios' },
        { value: 'ph-bold ph-currency-circle-dollar', label: 'Cifrão / Moeda', tags: 'preco valor custo orcamento cobranca tarifa', categoria: 'negocios' },
        { value: 'ph-bold ph-handshake', label: 'Aperto de Mão', tags: 'acordo contrato parceria cliente fornecedor negociacao', categoria: 'negocios' },
        { value: 'ph-bold ph-scales', label: 'Balança / Jurídico', tags: 'justica balanca pesagem conformidade compliance direito', categoria: 'negocios' },
        { value: 'ph-bold ph-certificate', label: 'Certificado / Qualidade', tags: 'qualidade iso aprovacao homologacao laudo certidao', categoria: 'negocios' },
        { value: 'ph-bold ph-identification-badge', label: 'Crachá / Identidade', tags: 'funcionario cracha identificacao registro matricula', categoria: 'negocios' },
        { value: 'ph-bold ph-target', label: 'Alvo / Objetivos', tags: 'meta objetivo foco estrategia indicador mira', categoria: 'negocios' },
        { value: 'ph-bold ph-trademark', label: 'Marca Registrada', tags: 'propriedade patente marca registro copyright', categoria: 'negocios' },
        { value: 'ph-bold ph-suitcase', label: 'Valise / Viagem', tags: 'deslocamento viagem diaria pernoite transporte', categoria: 'negocios' },
        { value: 'ph-bold ph-storefront', label: 'Loja / PDV', tags: 'comercio varejo ponto filial shopping balcao', categoria: 'negocios' },
        { value: 'ph-bold ph-shopping-cart', label: 'Carrinho / Compras', tags: 'suprimentos pedido compras aquisicao pedidos', categoria: 'negocios' },
        { value: 'ph-bold ph-tag', label: 'Etiqueta / Preço', tags: 'categoria classificacao tag rotulo preco tabela', categoria: 'negocios' },
        { value: 'ph-bold ph-credit-card', label: 'Cartão de Crédito', tags: 'pagamento cartao debito despesa transacao', categoria: 'negocios' },
        { value: 'ph-bold ph-piggy-bank', label: 'Cofrinho / Poupança', tags: 'reserva economia reducao custo investimento saving', categoria: 'negocios' },
        { value: 'ph-bold ph-coins', label: 'Moedas / Valores', tags: 'valores cambio taxa pedagio moedas centavos', categoria: 'negocios' },

        // Segurança, Acesso & Auditoria
        { value: 'ph-bold ph-shield-check', label: 'Escudo Seguro', tags: 'seguranca aprovado protecao auditoria confiavel rbac', categoria: 'seguranca' },
        { value: 'ph-bold ph-shield-warning', label: 'Alerta Segurança', tags: 'vulnerabilidade risco perigo ameaca aviso brecha', categoria: 'seguranca' },
        { value: 'ph-bold ph-shield-chevron', label: 'Escudo Divisão', tags: 'defesa militar protecao blindagem inspecao', categoria: 'seguranca' },
        { value: 'ph-bold ph-shield-plus', label: 'Adicionar Proteção', tags: 'nova regra protecao firewall seguranca regra', categoria: 'seguranca' },
        { value: 'ph-bold ph-shield-slash', label: 'Proteção Desativada', tags: 'desprotegido alerta perigo bypass liberado', categoria: 'seguranca' },
        { value: 'ph-bold ph-lock-key', label: 'Cadeado com Chave', tags: 'privado seguro senha acesso restrito bloqueado rbac', categoria: 'seguranca' },
        { value: 'ph-bold ph-lock-open', label: 'Cadeado Aberto', tags: 'desbloqueado publico livre liberado sem senha', categoria: 'seguranca' },
        { value: 'ph-bold ph-key', label: 'Chave de Acesso', tags: 'permissao credencial token autenticacao api chave secreta', categoria: 'seguranca' },
        { value: 'ph-bold ph-fingerprint', label: 'Biometria / Digital', tags: 'leitor identificacao unica autenticacao digital dedo', categoria: 'seguranca' },
        { value: 'ph-bold ph-password', label: 'Senha / Código', tags: 'pin codigo segredo autenticador mfa otp chave', categoria: 'seguranca' },
        { value: 'ph-bold ph-user-focus', label: 'Foco no Usuário', tags: 'rastreamento monitoramento usuario auditoria rastreio', categoria: 'seguranca' },
        { value: 'ph-bold ph-detective', label: 'Investigação / Auditor', tags: 'auditoria pericia investigacao compliance rastro log', categoria: 'seguranca' },
        { value: 'ph-bold ph-police-car', label: 'Viatura / Ronda', tags: 'seguranca patrimonial escolta gerenciamento risco gr ronda', categoria: 'seguranca' },
        { value: 'ph-bold ph-siren', label: 'Sirene / Alarme', tags: 'emergencia panico sinistro alerta gravissimo alarme', categoria: 'seguranca' },
        { value: 'ph-bold ph-eye', label: 'Olho / Visível', tags: 'visualizacao monitoramento inspecao consulta ver', categoria: 'seguranca' },
        { value: 'ph-bold ph-eye-slash', label: 'Olho Oculto', tags: 'oculto invisivel mascara sigiloso confidencial esconder', categoria: 'seguranca' },
        { value: 'ph-bold ph-vault', label: 'Cofre / Vault', tags: 'segredos credenciais senhas criptografia hvac hashicorp', categoria: 'seguranca' },
        { value: 'ph-bold ph-safe', label: 'Caixa Forte', tags: 'valores cofre seguro protecao reserva fisica', categoria: 'seguranca' },
        { value: 'ph-bold ph-identification-card', label: 'Cartão Documento', tags: 'cnh rg cpf motorista habilitacao documento', categoria: 'seguranca' },
        { value: 'ph-bold ph-scan', label: 'Scanner / Varredura', tags: 'leitura varredura biometria autenticacao scan', categoria: 'seguranca' },

        // Tecnologia, Sistemas & TI
        { value: 'ph-bold ph-database', label: 'Banco de Dados', tags: 'postgresql sql server oracle dados tabelas persistencia bd', categoria: 'tecnologia' },
        { value: 'ph-bold ph-hard-drives', label: 'Servidores de Disco', tags: 'storage matriz storage raid cluster servidor', categoria: 'tecnologia' },
        { value: 'ph-bold ph-hard-drive', label: 'Disco Rígido / SSD', tags: 'armazenamento memoria particao hd ssd nvme', categoria: 'tecnologia' },
        { value: 'ph-bold ph-cpu', label: 'Processador / CPU', tags: 'hardware processamento hardware infra chipset processador', categoria: 'tecnologia' },
        { value: 'ph-bold ph-cloud', label: 'Nuvem / Cloud', tags: 'servicos nuvem aws azure google hospedagem nuvem', categoria: 'tecnologia' },
        { value: 'ph-bold ph-cloud-arrow-up', label: 'Upload Nuvem', tags: 'backup sincronizacao envio cloud subir nuvem', categoria: 'tecnologia' },
        { value: 'ph-bold ph-cloud-arrow-down', label: 'Download Nuvem', tags: 'restauracao baixar arquivos nuvem restore', categoria: 'tecnologia' },
        { value: 'ph-bold ph-cloud-check', label: 'Nuvem Conectada', tags: 'online sincronizado cloud disponivel status ok', categoria: 'tecnologia' },
        { value: 'ph-bold ph-server', label: 'Servidor / Host', tags: 'maquina vm linux windows node instancia host', categoria: 'tecnologia' },
        { value: 'ph-bold ph-terminal-window', label: 'Prompt / Terminal', tags: 'console shell comando bash powershell cli terminal', categoria: 'tecnologia' },
        { value: 'ph-bold ph-git-branch', label: 'Branch / Versão', tags: 'git repositorio controle versao deploy release branch', categoria: 'tecnologia' },
        { value: 'ph-bold ph-git-commit', label: 'Commit Git', tags: 'revisao alteracao codigo release ponto salvamento', categoria: 'tecnologia' },
        { value: 'ph-bold ph-git-pull-request', label: 'Pull Request', tags: 'merge revisao codigo aprovacao devops pr', categoria: 'tecnologia' },
        { value: 'ph-bold ph-code', label: 'Código / Dev', tags: 'programacao software desenvolvimento html python script', categoria: 'tecnologia' },
        { value: 'ph-bold ph-brackets-curly', label: 'Chaves / JSON', tags: 'api payload json rest endpoint contrato chaves', categoria: 'tecnologia' },
        { value: 'ph-bold ph-wifi-high', label: 'Wi-Fi / Sem Fio', tags: 'rede sem fio conexao antena internet wireless', categoria: 'tecnologia' },
        { value: 'ph-bold ph-plugs', label: 'Conectores / Integração', tags: 'plug integracao api webhook conector tomada', categoria: 'tecnologia' },
        { value: 'ph-bold ph-network', label: 'Rede Corporativa', tags: 'lan vpn switch roteador intranet fibra', categoria: 'tecnologia' },
        { value: 'ph-bold ph-bug', label: 'Bug / Falha', tags: 'erro depuracao log crash issue defeito correcao', categoria: 'tecnologia' },
        { value: 'ph-bold ph-circuitry', label: 'Circuito / Chip', tags: 'automacao arquitetura placa eletronica circuito chip', categoria: 'tecnologia' },

        // Comunicação, Alertas & Suporte
        { value: 'ph-bold ph-headset', label: 'Suporte / Atendimento', tags: 'helpdesk sac chamado atendimento cliente ramal operador', categoria: 'comunicacao' },
        { value: 'ph-bold ph-chat-teardrop-text', label: 'Mensagem Balão', tags: 'conversa chat comentario ticket texto recado', categoria: 'comunicacao' },
        { value: 'ph-bold ph-chat-circle-dots', label: 'Chat com Pontos', tags: 'digitando resposta suporte comunicacao baloes', categoria: 'comunicacao' },
        { value: 'ph-bold ph-chats', label: 'Conversas Múltiplas', tags: 'dialogos canais grupos mensagens comunicados conversas', categoria: 'comunicacao' },
        { value: 'ph-bold ph-envelope-simple', label: 'E-mail / Envelope', tags: 'correio mensagem contato notificacao email caixa postal', categoria: 'comunicacao' },
        { value: 'ph-bold ph-envelope-open', label: 'E-mail Aberto', tags: 'lido mensagem aberta confirmacao visualizacao', categoria: 'comunicacao' },
        { value: 'ph-bold ph-bell', label: 'Sino / Notificação', tags: 'alerta aviso lembrete novidade push notificacao sino', categoria: 'comunicacao' },
        { value: 'ph-bold ph-bell-ringing', label: 'Sino Tocando', tags: 'alerta urgente chamada aviso imediato tocar som', categoria: 'comunicacao' },
        { value: 'ph-bold ph-megaphone', label: 'Megafone / Comunicado', tags: 'anuncio publicacao broadcast aviso geral comunicado mural', categoria: 'comunicacao' },
        { value: 'ph-bold ph-broadcast', label: 'Transmissão de Sinal', tags: 'antena difusao comunicador torre sinal transmissao', categoria: 'comunicacao' },
        { value: 'ph-bold ph-phone-call', label: 'Telefone Ligando', tags: 'chamada voz contato telefonia celular ligacao', categoria: 'comunicacao' },
        { value: 'ph-bold ph-newspaper', label: 'Jornal / Notícias', tags: 'mural noticias informativos artigos comunicacao boletim', categoria: 'comunicacao' },
        { value: 'ph-bold ph-article', label: 'Artigo / Boletim', tags: 'post publicacao texto blog comunicado materia', categoria: 'comunicacao' },
        { value: 'ph-bold ph-rss', label: 'Feed RSS', tags: 'atualizacoes sindicacao canal noticias feed', categoria: 'comunicacao' },
        { value: 'ph-bold ph-at', label: 'Arroba / Menção', tags: 'email mencao usuario tag perfil endereco', categoria: 'comunicacao' },
        { value: 'ph-bold ph-paper-plane-tilt', label: 'Aviãozinho / Enviar', tags: 'disparo enviar mensagem envio direto telegrama', categoria: 'comunicacao' },
        { value: 'ph-bold ph-radio', label: 'Rádio Comunicador', tags: 'walkie talkie radio frequencia operacao cco canal', categoria: 'comunicacao' },
        { value: 'ph-bold ph-speaker-high', label: 'Alto-falante', tags: 'som volume audio aviso sonoro megafone', categoria: 'comunicacao' },
        { value: 'ph-bold ph-chat-centered-text', label: 'Diálogo Central', tags: 'comunicacao chat central aviso popup', categoria: 'comunicacao' },
        { value: 'ph-bold ph-notification', label: 'Balão Notificação', tags: 'aviso mensagem alerta pop-up sino aviso', categoria: 'comunicacao' },

        // Operações, Ferramentas & Configuração
        { value: 'ph-bold ph-gear', label: 'Engrenagem / Config', tags: 'configuracoes parametros ajustes sistema manutencao motor', categoria: 'operacoes' },
        { value: 'ph-bold ph-gears', label: 'Engrenagens Múltiplas', tags: 'processos integracao motor operacoes rotinas sincronismo', categoria: 'operacoes' },
        { value: 'ph-bold ph-sliders', label: 'Controles / Sliders', tags: 'parametros filtros ajustes customizacao opcoes painel', categoria: 'operacoes' },
        { value: 'ph-bold ph-wrench', label: 'Chave de Boca', tags: 'reparo manutencao conserto ferramenta assistencia chave', categoria: 'operacoes' },
        { value: 'ph-bold ph-hammer', label: 'Martelo / Oficina', tags: 'construcao obra ferramentaria reparo oficina ajuste', categoria: 'operacoes' },
        { value: 'ph-bold ph-screwdriver', label: 'Chave de Fenda', tags: 'manutencao instalacao ajuste mecanica ferramenta', categoria: 'operacoes' },
        { value: 'ph-bold ph-toolbox', label: 'Caixa de Ferramentas', tags: 'utilitarios kit ferramentas suporte manutencao maleta', categoria: 'operacoes' },
        { value: 'ph-bold ph-magic-wand', label: 'Varinha Mágica / IA', tags: 'automacao assistente ia facilitador gerador magica', categoria: 'operacoes' },
        { value: 'ph-bold ph-crosshair', label: 'Mira / Precisão', tags: 'calibracao precisao foco rastreador ponto mira', categoria: 'operacoes' },
        { value: 'ph-bold ph-funnel-simple', label: 'Filtro Simples', tags: 'filtragem selecao criterio busca refinamento funil', categoria: 'operacoes' },
        { value: 'ph-bold ph-magnifying-glass', label: 'Lupa / Pesquisa', tags: 'busca consulta pesquisa localizar filtro achar', categoria: 'operacoes' },
        { value: 'ph-bold ph-lightning', label: 'Raio / Energia', tags: 'desempenho rapido eletricidade express forca energia', categoria: 'operacoes' },
        { value: 'ph-bold ph-recycle', label: 'Reciclagem / Ciclo', tags: 'sustentabilidade renovacao ciclo reprocessar ecologia', categoria: 'operacoes' },
        { value: 'ph-bold ph-compass-tool', label: 'Compasso / Desenho', tags: 'projeto arquitetura planejamento precisao desenho', categoria: 'operacoes' },
        { value: 'ph-bold ph-pencil-simple', label: 'Lápis / Editar', tags: 'redigir editar alterar anotacao preencher lapis', categoria: 'operacoes' },
        { value: 'ph-bold ph-eraser', label: 'Borracha / Limpar', tags: 'apagar resetar limpar remover estorno desfazer', categoria: 'operacoes' },
        { value: 'ph-bold ph-scissors', label: 'Tesoura / Recortar', tags: 'cortar separar dividir fracionar tesoura', categoria: 'operacoes' },
        { value: 'ph-bold ph-ruler', label: 'Régua / Medida', tags: 'dimensoes cubagem tamanho medicao escala', categoria: 'operacoes' },
        { value: 'ph-bold ph-paint-bucket', label: 'Balde de Tinta', tags: 'tema aparencia cores personalizacao layout pintura', categoria: 'operacoes' },
        { value: 'ph-bold ph-palette', label: 'Paleta de Cores', tags: 'design identidade visual visual cores tema paleta', categoria: 'operacoes' },

        // Pessoas, Equipes & Contatos
        { value: 'ph-bold ph-user', label: 'Usuário Individual', tags: 'pessoa perfil operador cliente motorista conta user', categoria: 'usuarios' },
        { value: 'ph-bold ph-users', label: 'Usuários / Grupo', tags: 'equipe time departamento setor departamento grupo', categoria: 'usuarios' },
        { value: 'ph-bold ph-user-circle', label: 'Avatar Circular', tags: 'perfil conta autenticacao login meu perfil foto', categoria: 'usuarios' },
        { value: 'ph-bold ph-user-gear', label: 'Usuário Administrador', tags: 'admin gestor configurador analista permissao master', categoria: 'usuarios' },
        { value: 'ph-bold ph-users-three', label: 'Equipe de Três', tags: 'time colaboradores reuniao equipe comite grupo', categoria: 'usuarios' },
        { value: 'ph-bold ph-users-four', label: 'Grande Equipe', tags: 'departamento congregacao empresa quadro geral pessoal', categoria: 'usuarios' },
        { value: 'ph-bold ph-user-list', label: 'Lista de Contatos', tags: 'diretorio lista funcionarios cadastro pessoas rascunho', categoria: 'usuarios' },
        { value: 'ph-bold ph-address-book', label: 'Agenda de Contatos', tags: 'contatos telefones enderecos fornecedores agenda', categoria: 'usuarios' },
        { value: 'ph-bold ph-user-plus', label: 'Novo Usuário', tags: 'cadastro inclusao admissao convidar registrar novo', categoria: 'usuarios' },
        { value: 'ph-bold ph-user-minus', label: 'Remover Usuário', tags: 'desligamento exclusao bloquear revogar saida', categoria: 'usuarios' },
        { value: 'ph-bold ph-user-switch', label: 'Trocar Usuário', tags: 'impersonate alternar conta trocar login alternar', categoria: 'usuarios' },
        { value: 'ph-bold ph-student', label: 'Treinamento / Aluno', tags: 'capacitacao curso onboarding treinamento aluno', categoria: 'usuarios' },
        { value: 'ph-bold ph-crown', label: 'Coroa / Master VIP', tags: 'master vip gestor supremo dono lider realeza', categoria: 'usuarios' },
        { value: 'ph-bold ph-medal', label: 'Medalha / Destaque', tags: 'premiacao reconhecimento kpi batido bonus honra', categoria: 'usuarios' },
        { value: 'ph-bold ph-trophy', label: 'Troféu / Campeão', tags: 'conquista lideranca resultado ouro primeiro lugar', categoria: 'usuarios' },
        { value: 'ph-bold ph-first-aid', label: 'Primeiros Socorros', tags: 'saude seguranca trabalho ambulancia cipa medico', categoria: 'usuarios' },
        { value: 'ph-bold ph-hand-palm', label: 'Palma / Pare', tags: 'parada seguranca espera atencao pare cuidado', categoria: 'usuarios' },
        { value: 'ph-bold ph-thumbs-up', label: 'Positivo / Joinha', tags: 'aprovado concordo positivo confirmacao like legal', categoria: 'usuarios' },
        { value: 'ph-bold ph-heart', label: 'Coração / Favorito', tags: 'favorito saude bem-estar apreco curtir vida', categoria: 'usuarios' },
        { value: 'ph-bold ph-baby', label: 'Iniciante / Trainee', tags: 'junior novo estagiario comeco trainee novato', categoria: 'usuarios' },

        // Documentos, Arquivos & Registros
        { value: 'ph-bold ph-file-text', label: 'Documento / Arquivo', tags: 'relatorio texto minuta contrato proposta arquivo doc', categoria: 'documentos' },
        { value: 'ph-bold ph-files', label: 'Múltiplos Documentos', tags: 'lote documentos arquivo massa impressao pastas', categoria: 'documentos' },
        { value: 'ph-bold ph-file-arrow-up', label: 'Upload de Arquivo', tags: 'importar carregar anexo envio documento subir', categoria: 'documentos' },
        { value: 'ph-bold ph-file-arrow-down', label: 'Download de Arquivo', tags: 'baixar exportar salvar pdf planilha baixar', categoria: 'documentos' },
        { value: 'ph-bold ph-file-pdf', label: 'Arquivo PDF', tags: 'documento pdf impressao oficial laudo termo', categoria: 'documentos' },
        { value: 'ph-bold ph-file-code', label: 'Arquivo Código / XML', tags: 'xml nfe cte sped xml json script programacao', categoria: 'documentos' },
        { value: 'ph-bold ph-folder', label: 'Pasta Fechada', tags: 'diretorio arquivos documentos pasta guardar', categoria: 'documentos' },
        { value: 'ph-bold ph-folder-notch-open', label: 'Pasta Aberta', tags: 'explorador arquivos conteudo pasta visualizando', categoria: 'documentos' },
        { value: 'ph-bold ph-folder-plus', label: 'Nova Pasta', tags: 'criar diretorio organizar separar pasta nova', categoria: 'documentos' },
        { value: 'ph-bold ph-clipboard-text', label: 'Prancheta / Checklist', tags: 'vistoria auditoria checklist conferencia prancheta itens', categoria: 'documentos' },
        { value: 'ph-bold ph-notebook', label: 'Caderno / Anotações', tags: 'notas diario rascunho livro ata memoria', categoria: 'documentos' },
        { value: 'ph-bold ph-book-bookmark', label: 'Manual / POP', tags: 'pop instrucao de trabalho manual norma documentacao guia', categoria: 'documentos' },
        { value: 'ph-bold ph-books', label: 'Biblioteca / Acervo', tags: 'legislacao arquivos historicos livros normas acervo', categoria: 'documentos' },
        { value: 'ph-bold ph-archive', label: 'Arquivo Morto', tags: 'arquivo guarda fisica temporalidade arquivamento historico', categoria: 'documentos' },
        { value: 'ph-bold ph-tray', label: 'Bandeja de Entrada', tags: 'caixa entrada pendencias triagem despacho caixa', categoria: 'documentos' },
        { value: 'ph-bold ph-printer', label: 'Impressora / Etiqueta', tags: 'impressao etiquetas danfe etiqueta zebra termica imprimir', categoria: 'documentos' },
        { value: 'ph-bold ph-scroll', label: 'Pergaminho / Histórico', tags: 'historico log trilha de auditoria certidao pergaminho', categoria: 'documentos' },
        { value: 'ph-bold ph-signature', label: 'Assinatura Digital', tags: 'assinatura digital aceite aprovacao chancela firma', categoria: 'documentos' },
        { value: 'ph-bold ph-newspaper-clipping', label: 'Recorte de Notícia', tags: 'clipping extrato trecho comprovante recorte', categoria: 'documentos' },
        { value: 'ph-bold ph-bookmarks', label: 'Marcadores de Página', tags: 'favoritos etiquetas referencias salvo marcadores', categoria: 'documentos' },

        // Dispositivos, Hardware & Auto ID
        { value: 'ph-bold ph-desktop', label: 'Computador / Estação', tags: 'desktop pc tela terminal estacao trabalho computador', categoria: 'dispositivos' },
        { value: 'ph-bold ph-desktop-tower', label: 'Torre de PC', tags: 'gabinete servidor estacao fisica hardware torre', categoria: 'dispositivos' },
        { value: 'ph-bold ph-laptop', label: 'Notebook / Portátil', tags: 'notebook laptop trabalho remoto portatil computador', categoria: 'dispositivos' },
        { value: 'ph-bold ph-device-mobile', label: 'Smartphone / Celular', tags: 'celular smartphone app mobile motorista aplicativo celular', categoria: 'dispositivos' },
        { value: 'ph-bold ph-device-tablet', label: 'Tablet / Coletor', tags: 'coletor dados conferencia tablet portatil wms', categoria: 'dispositivos' },
        { value: 'ph-bold ph-barcode', label: 'Código de Barras', tags: 'ean13 code128 leitura conferencia etiqueta codigo', categoria: 'dispositivos' },
        { value: 'ph-bold ph-qr-code', label: 'QR Code', tags: 'leitura rapida chave cte nfe rastreio url codigo qrcode', categoria: 'dispositivos' },
        { value: 'ph-bold ph-camera', label: 'Câmera Fotográfica', tags: 'foto comprovante canhoto ocorrencia avaria imagem', categoria: 'dispositivos' },
        { value: 'ph-bold ph-video-camera', label: 'Câmera CFTV', tags: 'monitoramento seguranca video gravacao portaria camera', categoria: 'dispositivos' },
        { value: 'ph-bold ph-microphone', label: 'Microfone / Áudio', tags: 'gravacao voz chamado atendimento fala som', categoria: 'dispositivos' },
        { value: 'ph-bold ph-keyboard', label: 'Teclado', tags: 'digitacao entrada dados estacao periferico teclado', categoria: 'dispositivos' },
        { value: 'ph-bold ph-mouse', label: 'Mouse', tags: 'cursor periferico controle clique mouse', categoria: 'dispositivos' },
        { value: 'ph-bold ph-monitor', label: 'Monitor / Display', tags: 'tela visualizacao painel televisao tv cco monitor', categoria: 'dispositivos' },
        { value: 'ph-bold ph-watch', label: 'Relógio de Pulso', tags: 'ponto horas jornada tempo relogio smart', categoria: 'dispositivos' },
        { value: 'ph-bold ph-sim-card', label: 'Chip / SIM Card', tags: 'telefonia 4g 5g conexao rastreador chip cartao', categoria: 'dispositivos' },
        { value: 'ph-bold ph-usb', label: 'USB / Pendrive', tags: 'certificado a3 chave conexao midia memoria usb', categoria: 'dispositivos' },
        { value: 'ph-bold ph-speaker-simple-high', label: 'Alto-falante Caixa', tags: 'anuncio chamada audio som caixa', categoria: 'dispositivos' },
        { value: 'ph-bold ph-television', label: 'TV Sala de Operações', tags: 'torre de controle painel cco display tv televisao', categoria: 'dispositivos' },
        { value: 'ph-bold ph-game-controller', label: 'Controle / Joystick', tags: 'simulador controle gamificacao joystick', categoria: 'dispositivos' },
        { value: 'ph-bold ph-app-window', label: 'Janela de Aplicação', tags: 'sistema tela modulo janela software app janela', categoria: 'dispositivos' },

        // Status, Ações & Marcadores
        { value: 'ph-bold ph-check-circle', label: 'Círculo Checado', tags: 'sucesso confirmado aprovado concluido ok feito', categoria: 'status' },
        { value: 'ph-bold ph-x-circle', label: 'Círculo Cancelado', tags: 'erro cancelado recusado reprovado falha x', categoria: 'status' },
        { value: 'ph-bold ph-warning', label: 'Atenção / Triângulo', tags: 'aviso perigo alerta atencao cuidado perigoso', categoria: 'status' },
        { value: 'ph-bold ph-warning-circle', label: 'Alerta Circular', tags: 'notificacao aviso pendente atencao circular', categoria: 'status' },
        { value: 'ph-bold ph-info', label: 'Informação', tags: 'ajuda detalhe dica orientacao faq informacao', categoria: 'status' },
        { value: 'ph-bold ph-question', label: 'Dúvida / Ajuda', tags: 'ajuda suporte duvida manual faq pergunta', categoria: 'status' },
        { value: 'ph-bold ph-star', label: 'Estrela / Favorito', tags: 'avaliacao destaque classificacao prioritario estrela', categoria: 'status' },
        { value: 'ph-bold ph-sparkle', label: 'Brilho / Novidade', tags: 'novo recurso destaque recente ia premium novidade', categoria: 'status' },
        { value: 'ph-bold ph-clock', label: 'Relógio / Tempo', tags: 'horario agendamento tempo sla prazo relogio hora', categoria: 'status' },
        { value: 'ph-bold ph-clock-countdown', label: 'Cronômetro / Prazo', tags: 'contagem regressiva prazo limite sla cronometro', categoria: 'status' },
        { value: 'ph-bold ph-calendar', label: 'Calendário', tags: 'data dia mes agendamento agenda calendario ano', categoria: 'status' },
        { value: 'ph-bold ph-calendar-check', label: 'Data Agendada', tags: 'compromisso marcado entrega agendada janela check', categoria: 'status' },
        { value: 'ph-bold ph-calendar-blank', label: 'Calendário Limpo', tags: 'planejamento escala periodo vazio em branco', categoria: 'status' },
        { value: 'ph-bold ph-hourglass', label: 'Ampulheta / Espera', tags: 'aguardando processando pendente fila tempo ampulheta', categoria: 'status' },
        { value: 'ph-bold ph-flag', label: 'Bandeira / Marco', tags: 'prioridade marco entrega etapa ponto bandeira meta', categoria: 'status' },
        { value: 'ph-bold ph-bookmark', label: 'Marcador de Página', tags: 'salvo favorito marcar referencia marcador', categoria: 'status' },
        { value: 'ph-bold ph-push-pin', label: 'Alfinete / Fixado', tags: 'fixar importante topo destaque aviso pin fixo', categoria: 'status' },
        { value: 'ph-bold ph-circle-notch', label: 'Carregando / Spinner', tags: 'processando aguarde load spinner rodando', categoria: 'status' },
        { value: 'ph-bold ph-arrow-counter-clockwise', label: 'Seta / Atualizar', tags: 'recarregar sincronizar refresh reiniciar voltar', categoria: 'status' },
        { value: 'ph-bold ph-thumbs-up-bold', label: 'Aprovado / Joinha', tags: 'concordo confirmado ok joinha curtir sim', categoria: 'status' }
    ],

    _categoriaNomes: {
        'todos': 'Todos',
        'logistica': '🚚 Logística & Frota',
        'dashboard': '📊 Dashboards & BI',
        'negocios': '💼 Gestão & Negócios',
        'seguranca': '🛡️ Segurança & Auditoria',
        'tecnologia': '🖥️ Tecnologia & TI',
        'comunicacao': '💬 Comunicação & Suporte',
        'operacoes': '⚙️ Operações & Ferramentas',
        'usuarios': '👥 Pessoas & Equipes',
        'documentos': '📄 Documentos & Relatórios',
        'dispositivos': '📱 Dispositivos & Hardware',
        'status': '⭐ Status & Marcadores'
    },

    abrirSeletorIcones: function(opcoes = {}) {
        let modal = document.getElementById('luft-modal-seletor-icones');
        if (!modal) {
            this._criarModalSeletorIcones();
            modal = document.getElementById('luft-modal-seletor-icones');
        }

        this._seletorIconesOpcoes = {
            targetInput: opcoes.targetInput || null,
            targetPreview: opcoes.targetPreview || null,
            iconeAtual: opcoes.iconeAtual || 'ph-bold ph-app-window',
            cor: opcoes.cor || null,
            onSelect: typeof opcoes.onSelect === 'function' ? opcoes.onSelect : null
        };

        this._iconeSelecionadoTemp = this._seletorIconesOpcoes.iconeAtual;
        this._categoriaIconeAtual = 'todos';

        // Atualiza preview superior do modal
        const previewIcon = document.getElementById('luft-picker-preview-icon');
        const previewClass = document.getElementById('luft-picker-preview-class');
        if (previewIcon) {
            previewIcon.className = this._iconeSelecionadoTemp;
            if (this._seletorIconesOpcoes.cor) {
                previewIcon.style.color = this._seletorIconesOpcoes.cor;
            } else {
                previewIcon.style.color = 'var(--luft-primary-600)';
            }
        }
        if (previewClass) {
            previewClass.innerText = this._iconeSelecionadoTemp;
        }

        // Limpa busca
        const inputBusca = document.getElementById('luft-picker-busca');
        if (inputBusca) {
            inputBusca.value = '';
        }

        // Renderiza abas e grid
        this._renderizarPillsCategorias();
        this._filtrarERenderizarIcones();

        this.abrirModal('luft-modal-seletor-icones');

        if (inputBusca) {
            setTimeout(() => inputBusca.focus(), 150);
        }
    },

    _criarModalSeletorIcones: function() {
        const backdrop = document.createElement('div');
        backdrop.className = 'luft-modal-backdrop';
        backdrop.id = 'luft-modal-seletor-icones-backdrop';
        backdrop.onclick = () => LuftBase.fecharModal('luft-modal-seletor-icones');

        const modal = document.createElement('div');
        modal.className = 'luft-modal luft-modal-lg';
        modal.id = 'luft-modal-seletor-icones';
        modal.style.maxWidth = '920px';
        modal.style.width = '94vw';
        modal.style.borderRadius = 'var(--luft-radius-xl)';
        modal.style.zIndex = '1060';

        modal.innerHTML = `
            <div class="luft-modal-header" style="border-bottom: 1px solid var(--luft-border-light); padding: 18px 24px;">
                <div class="d-flex align-items-center gap-3">
                    <div style="width: 40px; height: 40px; border-radius: var(--luft-radius-md); background: var(--luft-primary-50, #eff6ff); color: var(--luft-primary-600, #2563eb); display: flex; align-items: center; justify-content: center; font-size: 1.4rem;">
                        <i class="ph-bold ph-squares-four"></i>
                    </div>
                    <div>
                        <h3 class="luft-modal-title" style="margin: 0; font-size: 1.15rem; font-weight: 800;">Catálogo de Ícones do Sistema</h3>
                        <p class="text-xs text-muted" style="margin: 2px 0 0 0;">Mais de 240 ícones prontos organizados por segmento de operação.</p>
                    </div>
                </div>
                <button type="button" class="luft-modal-close" onclick="LuftBase.fecharModal('luft-modal-seletor-icones')" title="Fechar"><i class="ph-bold ph-x"></i></button>
            </div>

            <div class="luft-modal-body" style="padding: 20px 24px; display: flex; flex-direction: column; gap: 16px;">
                <!-- Barra Superior com Busca e Preview Ativo -->
                <div style="display: flex; gap: 16px; align-items: stretch; flex-wrap: wrap;">
                    <div style="flex: 1; min-width: 280px; position: relative;">
                        <i class="ph-bold ph-magnifying-glass" style="position: absolute; left: 14px; top: 50%; transform: translateY(-50%); font-size: 1.1rem; color: var(--luft-text-muted);"></i>
                        <input 
                            type="text" 
                            id="luft-picker-busca" 
                            class="luft-form-control" 
                            placeholder="Buscar ícone por nome, palavra-chave ou categoria (ex: caminhão, chart, user)..." 
                            style="padding-left: 42px; height: 46px; border-radius: var(--luft-radius-lg); font-size: 0.9rem;"
                            oninput="LuftBase._filtrarERenderizarIcones()"
                        >
                    </div>

                    <div style="display: flex; align-items: center; gap: 12px; padding: 6px 16px; background: var(--luft-bg-app); border: 1px solid var(--luft-border-light); border-radius: var(--luft-radius-lg);">
                        <div id="luft-picker-preview-box" style="width: 36px; height: 36px; border-radius: var(--luft-radius-md); background: var(--luft-bg-card); border: 1px solid var(--luft-border-light); display: flex; align-items: center; justify-content: center; font-size: 1.4rem;">
                            <i id="luft-picker-preview-icon" class="ph-bold ph-app-window"></i>
                        </div>
                        <div style="display: flex; flex-direction: column;">
                            <span class="text-xs text-muted font-semibold" style="text-transform: uppercase; letter-spacing: 0.5px;">Selecionado</span>
                            <span id="luft-picker-preview-class" class="font-mono text-xs font-bold text-main" style="word-break: break-all;">ph-bold ph-app-window</span>
                        </div>
                    </div>
                </div>

                <!-- Categorias (Pills Horizontais) -->
                <div id="luft-picker-pills" style="display: flex; gap: 6px; overflow-x: auto; padding-bottom: 4px; scrollbar-width: thin;"></div>

                <!-- Grade de Ícones -->
                <div 
                    id="luft-picker-grid" 
                    style="display: grid; grid-template-columns: repeat(auto-fill, minmax(115px, 1fr)); gap: 10px; max-height: 380px; overflow-y: auto; padding: 4px 6px 12px 2px; border-radius: var(--luft-radius-md);"
                ></div>

                <div id="luft-picker-empty" style="display: none; text-align: center; padding: 40px 20px; color: var(--luft-text-muted);">
                    <i class="ph-bold ph-magnifying-glass" style="font-size: 2.2rem; opacity: 0.5; margin-bottom: 8px; display: block;"></i>
                    <p style="margin: 0; font-weight: 600;">Nenhum ícone encontrado para a busca informada.</p>
                    <small style="opacity: 0.75;">Tente buscar por termos genéricos como "carga", "rede", "gráfico" ou navegue pelas abas acima.</small>
                </div>
            </div>

            <div class="luft-modal-footer" style="border-top: 1px solid var(--luft-border-light); padding: 14px 24px; display: flex; justify-content: space-between; align-items: center;">
                <span id="luft-picker-contador" class="text-xs text-muted font-mono">240 ícones disponíveis</span>
                <div class="d-flex align-items-center gap-2">
                    <button type="button" class="btn btn-outline btn-sm" onclick="LuftBase.fecharModal('luft-modal-seletor-icones')">Cancelar</button>
                    <button type="button" class="btn btn-primary btn-sm d-flex align-items-center gap-2" onclick="LuftBase._confirmarSelecaoIcone()">
                        <i class="ph-bold ph-check"></i>
                        <span>Aplicar Ícone</span>
                    </button>
                </div>
            </div>
        `;

        document.body.appendChild(backdrop);
        document.body.appendChild(modal);
    },

    _renderizarPillsCategorias: function() {
        const container = document.getElementById('luft-picker-pills');
        if (!container) return;

        let html = '';
        Object.entries(this._categoriaNomes).forEach(([chave, label]) => {
            const count = chave === 'todos' 
                ? this._catalogoIcones.length 
                : this._catalogoIcones.filter(i => i.categoria === chave).length;
            const ativa = this._categoriaIconeAtual === chave;
            html += `
                <button 
                    type="button" 
                    class="btn btn-sm ${ativa ? 'btn-primary' : 'btn-outline'}" 
                    style="border-radius: 9999px; padding: 4px 12px; font-size: 0.75rem; white-space: nowrap; font-weight: 600; display: inline-flex; align-items: center; gap: 6px;"
                    onclick="LuftBase._trocarCategoriaIcone('${chave}')"
                >
                    <span>${label}</span>
                    <span style="opacity: 0.7; font-size: 0.65rem; background: ${ativa ? 'rgba(255,255,255,0.25)' : 'var(--luft-bg-app)'}; padding: 1px 6px; border-radius: 9999px;">${count}</span>
                </button>
            `;
        });
        container.innerHTML = html;
    },

    _trocarCategoriaIcone: function(chave) {
        this._categoriaIconeAtual = chave;
        this._renderizarPillsCategorias();
        this._filtrarERenderizarIcones();
    },

    _filtrarERenderizarIcones: function() {
        const inputBusca = document.getElementById('luft-picker-busca');
        const termo = (inputBusca ? inputBusca.value : '').toLowerCase().trim();
        const grid = document.getElementById('luft-picker-grid');
        const empty = document.getElementById('luft-picker-empty');
        const contador = document.getElementById('luft-picker-contador');
        if (!grid) return;

        const filtrados = this._catalogoIcones.filter(item => {
            const matchCategoria = (this._categoriaIconeAtual === 'todos' || item.categoria === this._categoriaIconeAtual);
            if (!matchCategoria) return false;
            if (!termo) return true;
            return item.value.toLowerCase().includes(termo)
                || item.label.toLowerCase().includes(termo)
                || item.tags.toLowerCase().includes(termo);
        });

        if (contador) {
            contador.innerText = `${filtrados.length} ícone${filtrados.length === 1 ? '' : 's'} encontrado${filtrados.length === 1 ? '' : 's'}`;
        }

        if (filtrados.length === 0) {
            grid.style.display = 'none';
            if (empty) empty.style.display = 'block';
            return;
        }

        grid.style.display = 'grid';
        if (empty) empty.style.display = 'none';

        const corDestaque = this._seletorIconesOpcoes?.cor || 'var(--luft-primary-600)';

        let html = '';
        filtrados.forEach(item => {
            const selecionado = item.value === this._iconeSelecionadoTemp;
            html += `
                <div 
                    class="luft-icon-picker-card" 
                    data-value="${item.value}"
                    style="
                        display: flex; 
                        flex-direction: column; 
                        align-items: center; 
                        justify-content: center; 
                        padding: 12px 6px; 
                        border-radius: var(--luft-radius-lg); 
                        background: ${selecionado ? 'var(--luft-primary-50, #eff6ff)' : 'var(--luft-bg-card)'}; 
                        border: 2px solid ${selecionado ? corDestaque : 'var(--luft-border-light)'}; 
                        cursor: pointer; 
                        transition: all 0.18s ease; 
                        text-align: center;
                        box-shadow: ${selecionado ? '0 4px 12px rgba(37, 99, 235, 0.15)' : 'none'};
                    "
                    onmouseover="this.style.transform='translateY(-2px)'; this.style.borderColor='${corDestaque}'"
                    onmouseout="if(!this.dataset.selecionado){ this.style.transform='translateY(0)'; this.style.borderColor='var(--luft-border-light)'; }"
                    onclick="LuftBase._selecionarIconeTemp('${item.value}')"
                    title="${item.label} (${item.value})"
                >
                    <i class="${item.value}" style="font-size: 1.85rem; color: ${selecionado ? corDestaque : 'var(--luft-text-main)'}; margin-bottom: 6px; transition: transform 0.15s ease;"></i>
                    <span style="font-size: 0.68rem; font-weight: 600; color: var(--luft-text-main); max-width: 100px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: block;">${item.label}</span>
                    <span style="font-size: 0.6rem; font-family: monospace; color: var(--luft-text-muted); max-width: 100px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: block;">${item.value.replace('ph-bold ph-', '')}</span>
                </div>
            `;
        });
        grid.innerHTML = html;

        // Marca data-selecionado no elemento ativo
        const cardAtivo = grid.querySelector(`[data-value="${this._iconeSelecionadoTemp}"]`);
        if (cardAtivo) {
            cardAtivo.dataset.selecionado = 'true';
        }
    },

    _selecionarIconeTemp: function(valor) {
        this._iconeSelecionadoTemp = valor;
        const previewIcon = document.getElementById('luft-picker-preview-icon');
        const previewClass = document.getElementById('luft-picker-preview-class');
        if (previewIcon) {
            previewIcon.className = valor;
            if (this._seletorIconesOpcoes?.cor) {
                previewIcon.style.color = this._seletorIconesOpcoes.cor;
            }
        }
        if (previewClass) {
            previewClass.innerText = valor;
        }

        // Atualiza estado visual no grid sem re-renderizar tudo
        const grid = document.getElementById('luft-picker-grid');
        if (grid) {
            const corDestaque = this._seletorIconesOpcoes?.cor || 'var(--luft-primary-600)';
            grid.querySelectorAll('.luft-icon-picker-card').forEach(card => {
                const ehAtivo = card.dataset.value === valor;
                card.dataset.selecionado = ehAtivo ? 'true' : '';
                card.style.background = ehAtivo ? 'var(--luft-primary-50, #eff6ff)' : 'var(--luft-bg-card)';
                card.style.borderColor = ehAtivo ? corDestaque : 'var(--luft-border-light)';
                card.style.boxShadow = ehAtivo ? '0 4px 12px rgba(37, 99, 235, 0.15)' : 'none';
                const i = card.querySelector('i');
                if (i) i.style.color = ehAtivo ? corDestaque : 'var(--luft-text-main)';
            });
        }
    },

    _confirmarSelecaoIcone: function() {
        const valor = this._iconeSelecionadoTemp;
        if (!valor) {
            this.fecharModal('luft-modal-seletor-icones');
            return;
        }

        const opts = this._seletorIconesOpcoes || {};
        
        // Atualiza input alvo se especificado
        if (opts.targetInput) {
            const input = typeof opts.targetInput === 'string' ? document.getElementById(opts.targetInput) : opts.targetInput;
            if (input) {
                input.value = valor;
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.dispatchEvent(new Event('change', { bubbles: true }));
            }
        }

        // Atualiza preview alvo se especificado
        if (opts.targetPreview) {
            const prev = typeof opts.targetPreview === 'string' ? document.getElementById(opts.targetPreview) : opts.targetPreview;
            if (prev) {
                prev.className = valor;
                if (opts.cor) prev.style.color = opts.cor;
            }
        }

        // Callback customizado
        if (typeof opts.onSelect === 'function') {
            const meta = this._catalogoIcones.find(i => i.value === valor) || { value: valor, label: valor };
            opts.onSelect(valor, meta);
        }

        this.fecharModal('luft-modal-seletor-icones');
    },

    configurarSeletorIconesDeclarativo: function() {
        document.addEventListener('click', (event) => {
            const btn = event.target.closest('[data-luft-icon-picker]');
            if (!btn) return;

            const inputId = btn.getAttribute('data-luft-icon-picker');
            const previewId = btn.getAttribute('data-luft-icon-preview');
            const corId = btn.getAttribute('data-luft-icon-color');

            const input = inputId ? document.getElementById(inputId) : null;
            const corInput = corId ? document.getElementById(corId) : null;

            LuftBase.abrirSeletorIcones({
                targetInput: input,
                targetPreview: previewId,
                iconeAtual: input ? input.value : '',
                cor: corInput ? corInput.value : null
            });
        });
    },
};

document.addEventListener('DOMContentLoaded', () => {
    LuftBase.init();
    window.LuftBase = LuftBase;
    document.addEventListener('click', (event) => LuftBase._fecharDropdowns(event));
});