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
                    this.carregarHistoricoSessoes();
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

    // ========================================================================
    // EDITOR DE FOTO: recorte circular com arrastar, zoom e giro
    // ========================================================================
    _foto: null,

    _configurarUploadFoto: function() {
        const gatilho = document.getElementById('luft-perfil-avatar-upload-trigger');
        const modal = document.getElementById('luft-foto-modal');
        if (!gatilho || !modal) return;

        // O drawer usa transform, o que faria o position: fixed do modal ficar preso nele.
        if (modal.parentElement !== document.body) document.body.appendChild(modal);

        const el = (id) => document.getElementById(id);
        const canvas = el('luft-foto-canvas');
        const palco = el('luft-foto-palco');
        const entrada = el('luft-foto-input');
        const zoom = el('luft-foto-zoom');
        const TAM = canvas.width;
        const estado = { img: null, rot: 0, zoom: 1, ox: 0, oy: 0, arrasto: null, alterada: false, temFotoAtual: false };
        this._foto = estado;

        const erro = (texto) => {
            const caixa = el('luft-foto-erro');
            caixa.textContent = texto || '';
            caixa.hidden = !texto;
        };

        const dimensoes = () => {
            const girada = estado.rot % 2 === 1;
            return { w: girada ? estado.img.height : estado.img.width, h: girada ? estado.img.width : estado.img.height };
        };
        const escala = () => {
            const d = dimensoes();
            return (TAM / Math.min(d.w, d.h)) * estado.zoom;
        };
        const limitar = () => {
            if (!estado.img) return;
            const d = dimensoes();
            const folgaX = Math.max(0, (d.w * escala() - TAM) / 2);
            const folgaY = Math.max(0, (d.h * escala() - TAM) / 2);
            estado.ox = Math.min(folgaX, Math.max(-folgaX, estado.ox));
            estado.oy = Math.min(folgaY, Math.max(-folgaY, estado.oy));
        };
        const desenhar = () => {
            const ctx = canvas.getContext('2d');
            ctx.clearRect(0, 0, TAM, TAM);
            if (!estado.img) return;
            limitar();
            ctx.save();
            ctx.translate(TAM / 2 + estado.ox, TAM / 2 + estado.oy);
            ctx.rotate((estado.rot * Math.PI) / 2);
            ctx.scale(escala(), escala());
            ctx.drawImage(estado.img, -estado.img.width / 2, -estado.img.height / 2);
            ctx.restore();
            // Escurece o que fica fora do circulo (o que sera cortado).
            ctx.save();
            ctx.beginPath();
            ctx.rect(0, 0, TAM, TAM);
            ctx.arc(TAM / 2, TAM / 2, TAM / 2 - 3, 0, Math.PI * 2, true);
            ctx.fillStyle = 'rgba(15, 23, 42, 0.58)';
            ctx.fill('evenodd');
            ctx.beginPath();
            ctx.arc(TAM / 2, TAM / 2, TAM / 2 - 3, 0, Math.PI * 2);
            ctx.lineWidth = 2;
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.9)';
            ctx.stroke();
            ctx.restore();
        };
        const atualizarTela = () => {
            const comImagem = !!estado.img;
            el('luft-foto-vazio').hidden = comImagem;
            canvas.hidden = !comImagem;
            el('luft-foto-controles').hidden = !comImagem;
            el('luft-foto-dica').hidden = !comImagem;
            el('luft-foto-trocar').hidden = !comImagem;
            el('luft-foto-remover').hidden = !estado.temFotoAtual;
            el('luft-foto-salvar').disabled = !(comImagem && estado.alterada);
            zoom.value = String(Math.round(estado.zoom * 100));
            desenhar();
        };
        const marcarAlterada = () => { estado.alterada = true; atualizarTela(); };

        const carregarImagem = (fonte, alterada) => {
            erro('');
            const imagem = new Image();
            imagem.onload = () => {
                estado.img = imagem;
                estado.rot = 0; estado.zoom = 1; estado.ox = 0; estado.oy = 0;
                estado.alterada = alterada;
                atualizarTela();
                canvas.focus({ preventScroll: true });
            };
            imagem.onerror = () => erro('Não foi possível abrir essa imagem. Use um arquivo PNG, JPEG ou WebP.');
            imagem.src = fonte;
        };
        const carregarArquivo = (arquivo) => {
            if (!arquivo) return;
            if (!/^image\/(png|jpe?g|webp)$/i.test(arquivo.type)) {
                erro('Formato não aceito. Use PNG, JPEG ou WebP.');
                return;
            }
            if (arquivo.size > 8 * 1024 * 1024) {
                erro('A imagem é muito grande (máximo 8 MB).');
                return;
            }
            const leitor = new FileReader();
            leitor.onload = (e) => carregarImagem(e.target.result, true);
            leitor.onerror = () => erro('Não foi possível ler o arquivo.');
            leitor.readAsDataURL(arquivo);
        };

        const exportar = () => {
            const SAIDA = 256;
            const k = SAIDA / TAM;
            const saida = document.createElement('canvas');
            saida.width = SAIDA; saida.height = SAIDA;
            const ctx = saida.getContext('2d');
            ctx.imageSmoothingQuality = 'high';
            ctx.translate(SAIDA / 2 + estado.ox * k, SAIDA / 2 + estado.oy * k);
            ctx.rotate((estado.rot * Math.PI) / 2);
            ctx.scale(escala() * k, escala() * k);
            ctx.drawImage(estado.img, -estado.img.width / 2, -estado.img.height / 2);
            const webp = saida.toDataURL('image/webp', 0.9);
            return webp.startsWith('data:image/webp') ? webp : saida.toDataURL('image/png');
        };

        const aoTeclar = (e) => {
            if (e.key === 'Escape') { e.stopPropagation(); e.preventDefault(); fechar(); }
        };
        const abrir = () => {
            erro('');
            const atual = this._dadosUsuario && this._dadosUsuario.foto_perfil;
            estado.img = null; estado.alterada = false; estado.temFotoAtual = !!atual;
            modal.hidden = false;
            document.addEventListener('keydown', aoTeclar, true);
            if (atual) carregarImagem(atual, false); else atualizarTela();
            modal.querySelector('.luft-foto-card').focus({ preventScroll: true });
        };
        const fechar = () => {
            modal.hidden = true;
            document.removeEventListener('keydown', aoTeclar, true);
            entrada.value = '';
            gatilho.focus({ preventScroll: true });
        };
        this._fecharEditorFoto = fechar;

        gatilho.addEventListener('click', abrir);
        modal.querySelectorAll('[data-foto-fechar]').forEach((b) => b.addEventListener('click', fechar));
        modal.querySelectorAll('[data-foto-escolher]').forEach((b) => b.addEventListener('click', () => entrada.click()));
        entrada.addEventListener('change', (e) => carregarArquivo(e.target.files && e.target.files[0]));

        // Arrastar uma imagem do computador para o palco.
        ['dragenter', 'dragover'].forEach((nome) => palco.addEventListener(nome, (e) => { e.preventDefault(); palco.classList.add('arrastando-arquivo'); }));
        ['dragleave', 'drop'].forEach((nome) => palco.addEventListener(nome, (e) => { e.preventDefault(); palco.classList.remove('arrastando-arquivo'); }));
        palco.addEventListener('drop', (e) => carregarArquivo(e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]));

        // Posicionar: arrastar com mouse/toque, setas do teclado e roda do mouse para o zoom.
        canvas.addEventListener('pointerdown', (e) => {
            if (!estado.img) return;
            canvas.setPointerCapture(e.pointerId);
            estado.arrasto = { x: e.clientX, y: e.clientY, ox: estado.ox, oy: estado.oy };
            canvas.classList.add('segurando');
        });
        canvas.addEventListener('pointermove', (e) => {
            if (!estado.arrasto) return;
            const razao = TAM / canvas.getBoundingClientRect().width;
            estado.ox = estado.arrasto.ox + (e.clientX - estado.arrasto.x) * razao;
            estado.oy = estado.arrasto.oy + (e.clientY - estado.arrasto.y) * razao;
            estado.alterada = true;
            atualizarTela();
        });
        const soltar = () => { estado.arrasto = null; canvas.classList.remove('segurando'); };
        canvas.addEventListener('pointerup', soltar);
        canvas.addEventListener('pointercancel', soltar);
        canvas.addEventListener('wheel', (e) => {
            if (!estado.img) return;
            e.preventDefault();
            estado.zoom = Math.min(3, Math.max(1, estado.zoom + (e.deltaY < 0 ? 0.08 : -0.08)));
            marcarAlterada();
        }, { passive: false });
        canvas.addEventListener('keydown', (e) => {
            const passo = e.shiftKey ? 20 : 6;
            const mover = { ArrowLeft: [-passo, 0], ArrowRight: [passo, 0], ArrowUp: [0, -passo], ArrowDown: [0, passo] }[e.key];
            if (!mover || !estado.img) return;
            e.preventDefault();
            estado.ox += mover[0]; estado.oy += mover[1];
            marcarAlterada();
        });

        zoom.addEventListener('input', () => { estado.zoom = Number(zoom.value) / 100; marcarAlterada(); });
        el('luft-foto-girar-esq').addEventListener('click', () => { estado.rot = (estado.rot + 3) % 4; marcarAlterada(); });
        el('luft-foto-girar-dir').addEventListener('click', () => { estado.rot = (estado.rot + 1) % 4; marcarAlterada(); });
        el('luft-foto-centralizar').addEventListener('click', () => { estado.zoom = 1; estado.ox = 0; estado.oy = 0; marcarAlterada(); });

        // Remover: confirmacao no proprio botao (sem janela do navegador).
        const remover = el('luft-foto-remover');
        let confirmando = null;
        const rotuloRemover = remover.querySelector('span');
        const reiniciarRemover = () => { clearTimeout(confirmando); confirmando = null; rotuloRemover.textContent = 'Remover foto'; };
        remover.addEventListener('click', async () => {
            if (!confirmando) {
                rotuloRemover.textContent = 'Confirmar remoção';
                confirmando = setTimeout(reiniciarRemover, 4000);
                return;
            }
            reiniciarRemover();
            remover.disabled = true;
            const ok = await this.removerFoto();
            remover.disabled = false;
            if (ok) fechar(); else erro('Não foi possível remover a foto agora.');
        });

        const salvar = el('luft-foto-salvar');
        salvar.addEventListener('click', async () => {
            if (!estado.img) return;
            salvar.disabled = true;
            erro('');
            const ok = await this._enviarFotoServidor(exportar());
            if (ok) fechar(); else { salvar.disabled = false; erro('Não foi possível salvar a foto. Tente novamente.'); }
        });
    },

    _enviarFotoServidor: async function(fotoBase64) {
        try {
            const resp = await fetch((window.LUFT_RAIZ || '') + '/_luftbase/perfil/foto', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': this._obterCsrfToken() },
                body: JSON.stringify({ foto: fotoBase64 })
            });
            const dados = await resp.json().catch(() => ({}));
            if (resp.ok && dados.status === 'success') {
                if (this._dadosUsuario) this._dadosUsuario.foto_perfil = dados.foto_perfil;
                this._atualizarAvataresNaInterface(dados.foto_perfil);
                this._notificar('Foto de perfil atualizada com sucesso!', 'sucesso');
                return true;
            }
        } catch (erro) {
            console.error('Erro ao enviar foto:', erro);
        }
        return false;
    },

    removerFoto: async function() {
        try {
            const resp = await fetch((window.LUFT_RAIZ || '') + '/_luftbase/perfil/foto', {
                method: 'DELETE',
                headers: { 'X-CSRF-Token': this._obterCsrfToken() }
            });
            const dados = await resp.json().catch(() => ({}));
            if (resp.ok && dados.status === 'success') {
                if (this._dadosUsuario) this._dadosUsuario.foto_perfil = null;
                this._atualizarAvataresNaInterface(null);
                this._notificar('Foto de perfil removida.', 'sucesso');
                return true;
            }
        } catch (erro) {
            console.error('Erro ao remover foto:', erro);
        }
        return false;
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
            ...(document.getElementById('campo-perfil-idioma') ? { idioma: document.getElementById('campo-perfil-idioma').value } : {})
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

    _esc: function(valor) {
        return String(valor ?? '').replace(/[&<>"']/g, (c) => (
            { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
        ));
    },

    _iconeDispositivo: function(dispositivo) {
        if (dispositivo === 'mobile') return 'ph-bold ph-device-mobile';
        if (dispositivo === 'tablet') return 'ph-bold ph-device-tablet';
        return 'ph-bold ph-desktop';
    },

    _formatarDataHora: function(iso) {
        if (!iso) return '';
        const d = new Date(iso);
        if (isNaN(d.getTime())) return '';
        return `${d.toLocaleDateString()} ${d.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})}`;
    },

    carregarHistoricoSessoes: async function() {
        const container = document.getElementById('luft-perfil-historico-lista');
        if (!container) return;
        const motivos = { LOGOUT_VOLUNTARIO: 'Saiu da conta', TIMEOUT_INATIVIDADE: 'Expirou por inatividade', ROTACAO_SESSAO: 'Sessão renovada', REVOGADA_ADMIN: 'Encerrada à força', REVOGADA_USUARIO: 'Encerrada por você' };
        try {
            const resp = await fetch((window.LUFT_RAIZ || '') + '/_luftbase/perfil/sessoes/historico', {
                headers: { 'Accept': 'application/json' }
            });
            if (!resp.ok) return;
            const itens = (await resp.json()).historico || [];
            if (itens.length === 0) {
                container.innerHTML = '<div class="luft-sessoes-carregando">Nenhum acesso registrado ainda.</div>';
                return;
            }
            container.innerHTML = itens.map(s => {
                const ativa = s.status === 'ATIVA';
                const fim = ativa ? 'Em andamento' : (this._formatarDataHora(s.encerrada_em || s.ultima_atividade) || 'Encerrada');
                const motivo = ativa ? '' : ` (${this._esc(motivos[s.motivo_encerramento] || s.motivo_encerramento || 'Encerrada')})`;
                return `
                    <div class="luft-sessao-item ${s.is_atual ? 'is-atual' : ''}">
                        <div class="luft-sessao-device">
                            <i class="${this._iconeDispositivo(s.dispositivo)} luft-sessao-icon"></i>
                            <div class="luft-sessao-info">
                                <div class="d-flex align-items-center gap-2">
                                    <span class="luft-sessao-title">${this._esc(s.descricao || 'Navegador desconhecido')}</span>
                                    ${ativa ? '<span class="luft-badge-sessao-atual"><i class="ph-bold ph-check-circle"></i> Ativa</span>' : ''}
                                </div>
                                <span class="luft-sessao-meta">IP ${this._esc(s.ip_origem || 'Rede Interna')} &bull; Início: ${this._formatarDataHora(s.criada_em)} &bull; Fim: ${fim}${motivo}</span>
                            </div>
                        </div>
                    </div>`;
            }).join('');
        } catch (erro) {
            console.error('Erro ao listar histórico:', erro);
            container.innerHTML = '<div class="luft-sessoes-carregando text-danger">Falha ao carregar o histórico.</div>';
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
                const icone = this._iconeDispositivo(s.dispositivo);
                const tempoStr = this._formatarDataHora(s.ultima_atividade) || 'Ativo';

                return `
                    <div class="luft-sessao-item ${s.is_atual ? 'is-atual' : ''}">
                        <div class="luft-sessao-device">
                            <i class="${icone} luft-sessao-icon"></i>
                            <div class="luft-sessao-info">
                                <div class="d-flex align-items-center gap-2">
                                    <span class="luft-sessao-title">${this._esc(s.descricao || 'Navegador desconhecido')}</span>
                                    ${s.is_atual ? '<span class="luft-badge-sessao-atual"><i class="ph-bold ph-check-circle"></i> Esta sessão</span>' : ''}
                                </div>
                                <span class="luft-sessao-meta">IP ${this._esc(s.ip_origem || 'Rede Interna')} &bull; Última atividade: ${tempoStr}</span>
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
                void this.carregarHistoricoSessoes();
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
