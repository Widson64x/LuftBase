/**
 * ============================================================================
 * LuftPerfil — Módulo de Gerenciamento de Perfil Corporativo
 * Design System LuftBase & Identidade Corporativa
 * ============================================================================
 */

const LuftPerfil = {
    _drawer: null,
    _backdrop: null,
    _dadosUsuario: null,
    _modoSelecionado: 'CLARO',
    _temaSelecionado: 'luft',
    _estadoVisualAoAbrir: null,
    _aparenciaSalva: false,

    init: function() {
        this._drawer = document.getElementById('luft-perfil-drawer');
        this._backdrop = document.getElementById('luft-perfil-backdrop');
        if (!this._drawer || !this._backdrop) return;

        this._configurarGatilhos();
        this._configurarAbas();
        this._configurarModosTema();
        this._configurarUploadFoto();
        this._configurarFormularios();
        this._configurarSessoes();
    },

    _obterCsrfToken: function() {
        const meta = document.querySelector('meta[name="luft-csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    },

    _configurarGatilhos: function() {
        // Vincula a todos os elementos .luft-user, #btn-perfil-usuario e triggers explícitos
        const triggers = document.querySelectorAll('.luft-user, #btn-perfil-usuario, [data-luft-perfil-trigger]');
        triggers.forEach(el => {
            el.style.cursor = 'pointer';
            el.addEventListener('click', (e) => {
                // Não dispara se clicou no botão de tema ou logout dentro de ações
                if (e.target.closest('.luft-btn-action') || e.target.closest('form')) return;
                this.abrir();
            });
            el.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    this.abrir();
                }
            });
        });

        // Fechar no botão X
        const btnFechar = document.getElementById('luft-perfil-close-btn');
        if (btnFechar) {
            btnFechar.addEventListener('click', () => this.fechar());
        }

        // Fechar ao clicar no backdrop
        if (this._backdrop) {
            this._backdrop.addEventListener('click', () => this.fechar());
        }

        // Fechar no Esc
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.estaAberto()) {
                this.fechar();
            }
        });
    },

    _configurarAbas: function() {
        const tabBtns = this._drawer.querySelectorAll('.luft-perfil-tab-btn');
        tabBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                const targetTab = btn.getAttribute('data-tab');
                tabBtns.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');

                const panes = this._drawer.querySelectorAll('.luft-perfil-pane');
                panes.forEach(pane => {
                    pane.classList.toggle('active', pane.id === `luft-perfil-tab-${targetTab}`);
                });

                if (targetTab === 'sessoes') {
                    this.carregarSessoes();
                }
            });
        });
    },

    _configurarModosTema: function() {
        const modeCards = this._drawer.querySelectorAll('.luft-mode-card');
        modeCards.forEach(card => {
            card.addEventListener('click', () => {
                const mode = card.getAttribute('data-mode');
                this._selecionarModoTema(mode);
            });
        });

        this._drawer.querySelectorAll('input[name="perfil_tema_preferido"]').forEach(radio => {
            radio.addEventListener('change', () => this._selecionarTema(radio.value));
        });

        const btnSalvarAparencia = document.getElementById('btn-luft-salvar-aparencia');
        if (btnSalvarAparencia) {
            btnSalvarAparencia.addEventListener('click', () => this.salvarAparencia());
        }
    },

    _selecionarModoTema: function(mode) {
        const estado = window.LuftBase.obterEstadoTema();
        if (estado.bloqueado) return; // modo fixo: os cartoes ja estao desabilitados
        this._modoSelecionado = mode;
        this._atualizarAparencia();
    },

    _selecionarTema: function(temaId) {
        this._temaSelecionado = temaId;
        this._atualizarAparencia();
    },

    /**
     * Reflete tema + modo escolhidos: aplica a previa ao vivo e sincroniza os cartoes.
     * A preferencia de modo do usuario (_modoSelecionado) nunca e alterada pelo bloqueio:
     * em um tema de modo unico ela fica guardada e volta a valer ao trocar de tema.
     */
    _atualizarAparencia: function() {
        window.LuftBase.aplicarTema(this._temaSelecionado, this._modoSelecionado.toLowerCase());
        const estado = window.LuftBase.obterEstadoTema();
        const rotulos = { claro: 'claro', escuro: 'escuro' };

        this._drawer.querySelectorAll('input[name="perfil_tema_preferido"]').forEach(radio => {
            radio.checked = radio.value === this._temaSelecionado;
            radio.closest('.luft-theme-radio-card')?.classList.toggle('selected', radio.checked);
        });

        const efetivoMaiusculo = estado.modoEfetivo.toUpperCase();
        this._drawer.querySelectorAll('.luft-mode-card').forEach(card => {
            const modo = card.getAttribute('data-mode');
            const suportado = modo === 'SISTEMA' ? !estado.bloqueado : estado.modos.includes(modo.toLowerCase());
            card.disabled = !suportado;
            card.classList.toggle('indisponivel', !suportado);
            card.setAttribute('aria-disabled', suportado ? 'false' : 'true');
            // Bloqueado: marca o modo imposto pelo tema; livre: marca a preferencia do usuario.
            const marcado = estado.bloqueado ? modo === efetivoMaiusculo : modo === this._modoSelecionado;
            card.classList.toggle('selected', marcado);
        });

        const aviso = document.getElementById('luft-modo-bloqueado-aviso');
        if (aviso) {
            aviso.hidden = !estado.bloqueado;
            aviso.textContent = estado.bloqueado
                ? `O tema ${estado.nomeTema} oferece apenas o modo ${rotulos[estado.modos[0]] || estado.modos[0]}. Sua escolha de modo foi guardada e volta a valer em temas com claro e escuro.`
                : '';
        }
    },

    _configurarUploadFoto: function() {
        const fileInput = document.getElementById('luft-perfil-file-input');
        const triggerBtn = document.getElementById('luft-perfil-avatar-upload-trigger');
        const btnAlterar = document.getElementById('btn-luft-alterar-foto');
        const btnRemover = document.getElementById('btn-luft-remover-foto');

        const abrirSeletor = () => {
            if (fileInput) fileInput.click();
        };

        if (triggerBtn) triggerBtn.addEventListener('click', abrirSeletor);
        if (btnAlterar) btnAlterar.addEventListener('click', abrirSeletor);

        if (fileInput) {
            fileInput.addEventListener('change', (e) => {
                const arquivo = e.target.files && e.target.files[0];
                if (arquivo) {
                    this._processarEEnviarFoto(arquivo);
                }
            });
        }

        if (btnRemover) {
            btnRemover.addEventListener('click', () => this.removerFoto());
        }
    },

    _processarEEnviarFoto: function(arquivo) {
        if (!arquivo.type.startsWith('image/')) {
            alert('Por favor, selecione um arquivo de imagem válido (PNG, JPEG ou WebP).');
            return;
        }

        const reader = new FileReader();
        reader.onload = (e) => {
            const img = new Image();
            img.onload = () => {
                // Redimensionamento de alta performance via Canvas para tamanho 256x256
                const canvas = document.createElement('canvas');
                const tamanho = 256;
                canvas.width = tamanho;
                canvas.height = tamanho;
                const ctx = canvas.getContext('2d');

                // Corta o centro mantendo proporção quadrada perfeita
                const menorLado = Math.min(img.width, img.height);
                const sx = (img.width - menorLado) / 2;
                const sy = (img.height - menorLado) / 2;

                ctx.drawImage(img, sx, sy, menorLado, menorLado, 0, 0, tamanho, tamanho);
                const fotoBase64 = canvas.toDataURL('image/webp', 0.88);

                this._enviarFotoServidor(fotoBase64);
            };
            img.src = e.target.result;
        };
        reader.readAsDataURL(arquivo);
    },

    _enviarFotoServidor: async function(fotoBase64) {
        try {
            const resp = await fetch((window.LUFT_RAIZ || '') + '/_luftbase/perfil/foto', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': this._obterCsrfToken()
                },
                body: JSON.stringify({ foto: fotoBase64 })
            });
            const dados = await resp.json();
            if (resp.ok && dados.status === 'success') {
                this._atualizarAvataresNaInterface(dados.foto_perfil);
                this._notificar('Foto de perfil atualizada com sucesso!', 'sucesso');
            } else {
                alert(dados.mensagem || 'Falha ao atualizar foto de perfil.');
            }
        } catch (erro) {
            console.error('Erro ao enviar foto:', erro);
            alert('Erro de comunicação ao enviar foto de perfil.');
        }
    },

    removerFoto: async function() {
        if (!confirm('Deseja realmente remover sua foto de perfil?')) return;
        try {
            const resp = await fetch((window.LUFT_RAIZ || '') + '/_luftbase/perfil/foto', {
                method: 'DELETE',
                headers: {
                    'X-CSRF-Token': this._obterCsrfToken()
                }
            });
            const dados = await resp.json();
            if (resp.ok && dados.status === 'success') {
                this._atualizarAvataresNaInterface(null);
                this._notificar('Foto de perfil removida.', 'sucesso');
            } else {
                alert(dados.mensagem || 'Falha ao remover foto.');
            }
        } catch (erro) {
            console.error('Erro ao remover foto:', erro);
            alert('Erro ao remover foto.');
        }
    },

    _atualizarAvataresNaInterface: function(fotoUrl) {
        // Atualiza avatar do drawer
        const drawerImg = document.getElementById('luft-perfil-avatar-img');
        const drawerInitials = document.getElementById('luft-perfil-avatar-initials');
        if (drawerImg && drawerInitials) {
            if (fotoUrl) {
                drawerImg.src = fotoUrl;
                drawerImg.style.display = 'block';
                drawerInitials.style.display = 'none';
            } else {
                drawerImg.src = '';
                drawerImg.style.display = 'none';
                drawerInitials.style.display = 'block';
            }
        }

        // Atualiza avatar da barra lateral / layout
        const sidebarAvatars = document.querySelectorAll('.luft-avatar');
        sidebarAvatars.forEach(box => {
            let img = box.querySelector('img.luft-avatar-img');
            let span = box.querySelector('span:not(.luft-status-dot)');
            if (fotoUrl) {
                if (!img) {
                    img = document.createElement('img');
                    img.className = 'luft-avatar-img';
                    box.insertBefore(img, box.firstChild);
                }
                img.src = fotoUrl;
                img.style.display = 'block';
                if (span) span.style.display = 'none';
            } else {
                if (img) img.style.display = 'none';
                if (span) span.style.display = 'block';
            }
        });
    },

    _configurarFormularios: function() {
        const formDados = document.getElementById('form-luft-perfil-dados');
        if (formDados) {
            formDados.addEventListener('submit', (e) => {
                e.preventDefault();
                this.salvarDados();
            });
        }
    },

    _configurarSessoes: function() {
        const btnRevogar = document.getElementById('btn-luft-revogar-outras-sessoes');
        if (btnRevogar) {
            btnRevogar.addEventListener('click', () => this.revogarOutrasSessoes());
        }
    },

    estaAberto: function() {
        return this._drawer && this._drawer.classList.contains('open');
    },

    abrir: function() {
        if (!this._drawer || !this._backdrop) return;
        this._drawer.classList.add('open');
        this._backdrop.classList.add('open');
        document.body.style.overflow = 'hidden';
        if (window.LuftBase?.obterEstadoTema) {
            const e = window.LuftBase.obterEstadoTema();
            this._estadoVisualAoAbrir = { tema: e.tema, modoPreferido: e.modoPreferido };
        }
        this._aparenciaSalva = false;
        void this.carregarPerfil();
    },

    fechar: function() {
        if (!this._drawer || !this._backdrop) return;
        this._drawer.classList.remove('open');
        this._backdrop.classList.remove('open');
        document.body.style.overflow = '';
        // A previa de tema/modo so vale se foi salva; do contrario volta ao que estava.
        if (!this._aparenciaSalva && this._estadoVisualAoAbrir && window.LuftBase?.aplicarTema) {
            window.LuftBase.aplicarTema(this._estadoVisualAoAbrir.tema, this._estadoVisualAoAbrir.modoPreferido);
        }
        this._estadoVisualAoAbrir = null;
    },

    carregarPerfil: async function() {
        try {
            const resp = await fetch((window.LUFT_RAIZ || '') + '/_luftbase/perfil', {
                headers: { 'Accept': 'application/json' }
            });
            if (!resp.ok) return;
            const u = await resp.json();
            this._dadosUsuario = u;
            this._renderizarDados(u);
        } catch (erro) {
            console.error('Erro ao carregar perfil corporativo:', erro);
        }
    },

    _renderizarDados: function(u) {
        // Hero
        const heroName = document.getElementById('luft-perfil-hero-name');
        const heroRole = document.getElementById('luft-perfil-hero-role');
        const badgeCodigo = document.getElementById('luft-perfil-badge-codigo');
        const badgeLogin = document.getElementById('luft-perfil-badge-login');
        const initials = document.getElementById('luft-perfil-avatar-initials');

        if (heroName) heroName.textContent = u.nome_usuario || u.login_usuario;
        if (heroRole) heroRole.textContent = u.sigla_usuariogrupo || u.cargo_usuario || 'Usuário Corporativo';
        if (badgeCodigo) badgeCodigo.textContent = `#${u.codigo_usuario}`;
        if (badgeLogin) badgeLogin.textContent = u.login_usuario;

        // Iniciais
        if (initials) {
            const partes = (u.nome_usuario || u.login_usuario || 'U').trim().split(/\s+/);
            const inits = (partes[0][0] + (partes.length > 1 ? partes[partes.length - 1][0] : '')).toUpperCase();
            initials.textContent = inits;
        }

        // Foto
        this._atualizarAvataresNaInterface(u.foto_perfil);

        // Campos do Formulário
        const setVal = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.value = val || '';
        };
        const setText = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.textContent = val || '--';
        };

        setVal('campo-perfil-nome', u.nome_usuario);
        setVal('campo-perfil-cargo', u.cargo_usuario);
        setVal('campo-perfil-departamento', u.departamento_usuario);
        setVal('campo-perfil-unidade', u.unidade_filial);
        setVal('campo-perfil-telefone', u.telefone_usuario);
        setVal('campo-perfil-celular', u.celular_usuario);
        setVal('campo-perfil-idioma', u.idioma || 'pt-BR');

        // Campos Imutáveis (LuftInforma)
        setText('campo-perfil-codigo-info', `#${u.codigo_usuario}`);
        setText('campo-perfil-login-info', u.login_usuario);
        setText('campo-perfil-email-info', u.email_usuario || 'Não informado');
        setText('campo-perfil-grupo-info', u.sigla_usuariogrupo || 'Padrão');

        // Telemetria
        setText('luft-telemetria-total-logins', u.total_logins != null ? String(u.total_logins) : '1');
        setText('luft-telemetria-ultimo-ip', u.ultimo_ip || '127.0.0.1');
        if (u.ultimo_acesso) {
            const d = new Date(u.ultimo_acesso);
            setText('luft-telemetria-ultimo-acesso', `${d.toLocaleDateString()} às ${d.toLocaleTimeString()}`);
        }

        // Modo de tema
        this._modoSelecionado = (u.modo_tema || 'SISTEMA').toUpperCase();
        this._temaSelecionado = u.tema_preferido || 'luft';
        this._atualizarAparencia();
    },

    salvarDados: async function() {
        const btnSalvar = document.getElementById('btn-luft-salvar-dados');
        if (btnSalvar) {
            btnSalvar.disabled = true;
            btnSalvar.innerHTML = '<i class="ph-bold ph-spinner ph-spin"></i><span>Salvando...</span>';
        }

        const payload = {
            nome_usuario: document.getElementById('campo-perfil-nome')?.value || '',
            cargo_usuario: document.getElementById('campo-perfil-cargo')?.value || '',
            departamento_usuario: document.getElementById('campo-perfil-departamento')?.value || '',
            unidade_filial: document.getElementById('campo-perfil-unidade')?.value || '',
            telefone_usuario: document.getElementById('campo-perfil-telefone')?.value || '',
            celular_usuario: document.getElementById('campo-perfil-celular')?.value || '',
        };

        try {
            const resp = await fetch((window.LUFT_RAIZ || '') + '/_luftbase/perfil', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': this._obterCsrfToken()
                },
                body: JSON.stringify(payload)
            });
            const dados = await resp.json();
            if (resp.ok && dados.status === 'success') {
                this._notificar('Informações atualizadas com sucesso!', 'sucesso');
                // Atualiza nome na barra lateral
                const sidebarName = document.querySelector('.luft-user-name');
                if (sidebarName && payload.nome_usuario) {
                    sidebarName.textContent = payload.nome_usuario;
                }
                const heroName = document.getElementById('luft-perfil-hero-name');
                if (heroName && payload.nome_usuario) {
                    heroName.textContent = payload.nome_usuario;
                }
            } else {
                alert(dados.mensagem || 'Falha ao salvar dados.');
            }
        } catch (erro) {
            console.error('Erro ao salvar dados:', erro);
            alert('Erro de comunicação ao salvar dados.');
        } finally {
            if (btnSalvar) {
                btnSalvar.disabled = false;
                btnSalvar.innerHTML = '<i class="ph-bold ph-floppy-disk"></i><span>Salvar Informações</span>';
            }
        }
    },

    salvarAparencia: async function() {
        const btn = document.getElementById('btn-luft-salvar-aparencia');
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<i class="ph-bold ph-spinner ph-spin"></i><span>Salvando...</span>';
        }

        const payload = {
            modo_tema: this._modoSelecionado,
            tema_preferido: this._temaSelecionado,
            idioma: document.getElementById('campo-perfil-idioma')?.value || 'pt-BR'
        };

        try {
            const resp = await fetch((window.LUFT_RAIZ || '') + '/_luftbase/perfil', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': this._obterCsrfToken()
                },
                body: JSON.stringify(payload)
            });
            const dados = await resp.json();
            if (resp.ok && dados.status === 'success') {
                this._aparenciaSalva = true;
                this._estadoVisualAoAbrir = null;
                this._notificar('Preferências visuais salvas!', 'sucesso');
            } else {
                alert(dados.mensagem || 'Falha ao salvar preferências de tema.');
            }
        } catch (erro) {
            console.error('Erro ao salvar preferências:', erro);
            alert('Erro de comunicação ao salvar preferências.');
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = '<i class="ph-bold ph-check"></i><span>Salvar Preferências Visuais</span>';
            }
        }
    },

    carregarSessoes: async function() {
        const container = document.getElementById('luft-perfil-sessoes-lista');
        if (!container) return;

        try {
            const resp = await fetch((window.LUFT_RAIZ || '') + '/_luftbase/perfil/sessoes', {
                headers: { 'Accept': 'application/json' }
            });
            if (!resp.ok) return;
            const dados = await resp.json();
            const sessoes = dados.sessoes || [];

            if (sessoes.length === 0) {
                container.innerHTML = '<div class="luft-sessoes-carregando">Nenhuma sessão adicional registrada.</div>';
                return;
            }

            container.innerHTML = sessoes.map(s => {
                const isMobile = s.user_agent && /mobile|android|iphone/i.test(s.user_agent);
                const icone = isMobile ? 'ph-bold ph-device-mobile' : 'ph-bold ph-desktop';
                const d = s.ultima_atividade ? new Date(s.ultima_atividade) : null;
                const tempoStr = d ? `${d.toLocaleDateString()} ${d.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}` : 'Ativo';

                return `
                    <div class="luft-sessao-item ${s.is_atual ? 'is-atual' : ''}">
                        <div class="luft-sessao-device">
                            <i class="${icone} luft-sessao-icon"></i>
                            <div class="luft-sessao-info">
                                <div class="d-flex align-items-center gap-2">
                                    <span class="luft-sessao-title">${s.ip_origem || 'Rede Interna'}</span>
                                    ${s.is_atual ? '<span class="luft-badge-sessao-atual"><i class="ph-bold ph-check-circle"></i> Esta sessão</span>' : ''}
                                </div>
                                <span class="luft-sessao-meta">Última atividade: ${tempoStr} &bull; ${s.id_exibicao || s.id_sessao}</span>
                            </div>
                        </div>
                    </div>
                `;
            }).join('');
        } catch (erro) {
            console.error('Erro ao listar sessões:', erro);
            container.innerHTML = '<div class="luft-sessoes-carregando text-danger">Falha ao carregar sessões.</div>';
        }
    },

    revogarOutrasSessoes: async function() {
        if (!confirm('Deseja encerrar todas as outras sessões ativas desta conta em outros navegadores ou computadores?')) {
            return;
        }

        try {
            const resp = await fetch((window.LUFT_RAIZ || '') + '/_luftbase/perfil/sessoes/revogar-outras', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': this._obterCsrfToken()
                }
            });
            const dados = await resp.json();
            if (resp.ok && dados.status === 'success') {
                this._notificar(dados.mensagem || 'Outras sessões foram revogadas.', 'sucesso');
                void this.carregarSessoes();
            } else {
                alert(dados.mensagem || 'Falha ao revogar sessões.');
            }
        } catch (erro) {
            console.error('Erro ao revogar sessões:', erro);
            alert('Erro de comunicação ao revogar sessões.');
        }
    },

    _notificar: function(msg, tipo) {
        if (typeof window.LuftBase?.exibirAlerta === 'function') {
            window.LuftBase.exibirAlerta(msg, tipo);
        } else {
            console.log(`[LuftPerfil] ${msg}`);
        }
    }
};

// Inicialização automática quando o DOM estiver pronto
document.addEventListener('DOMContentLoaded', () => {
    LuftPerfil.init();
});
