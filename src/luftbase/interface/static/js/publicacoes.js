/** Administração de comunicados e notas de atualização do LuftBase. */
const LuftPublicacoesPainel = {
    _config: null,

    init() {
        const no = document.getElementById('publicacoes-config');
        if (!no) return;
        try {
            this._config = JSON.parse(no.textContent || '{}');
        } catch (erro) {
            console.error('[LuftPublicacoes] Configuração inválida.', erro);
            return;
        }

        const form = document.getElementById('formPublicacao');
        if (form) {
            // Corrigir um campo apaga o aviso dele na hora e atualiza o resumo da entrega.
            ['input', 'change'].forEach(evento => form.addEventListener(evento, e => {
                const alvo = e.target;
                if (alvo?.id) this._limparErro(alvo.id);
                if (alvo?.name === 'publicacaoGrupo') this._limparErro('publicacaoGruposCampo');
                if (alvo?.id !== 'publicacaoGrupoBusca') this.atualizarResumo();
            }));
        }
        document.getElementById('publicacoesBusca')?.addEventListener('input', () => this.filtrar());
        document.getElementById('publicacoesFiltroStatus')?.addEventListener('change', () => this.filtrar());
    },

    abrirNovo() {
        const form = document.getElementById('formPublicacao');
        if (!form) return;
        form.reset();
        document.getElementById('publicacaoId').value = '';
        document.getElementById('publicacaoPrioridade').value = 'NORMAL';
        document.getElementById('publicacaoAudiencia').value = 'GERAL';
        document.getElementById('publicacaoNotificar').checked = true;
        // O navegador pode restaurar datas digitadas antes; zera de forma explícita.
        document.getElementById('publicacaoInicio').value = '';
        document.getElementById('publicacaoExpiracao').value = '';
        document.querySelectorAll('[name="publicacaoGrupo"]').forEach(item => { item.checked = false; });
        const itens = document.getElementById('publicacaoItens');
        if (itens) {
            itens.innerHTML = '';
            this.adicionarItem();
        }
        this._prepararFormulario();
        window.LuftBase.abrirModal('modalPublicacao');
    },

    /** Zera erros, filtro de grupos e resumo sempre que o modal é aberto. */
    _prepararFormulario() {
        this._limparErros();
        const busca = document.getElementById('publicacaoGrupoBusca');
        if (busca) busca.value = '';
        this.filtrarGrupos();
        this.alternarAudiencia();
        this.atualizarResumo();
    },

    /** Define um atalho de data: 'inicio' ou 'expiracao', em dias a partir de agora (null = limpar). */
    definirData(campo, dias) {
        const alvo = document.getElementById(campo === 'inicio' ? 'publicacaoInicio' : 'publicacaoExpiracao');
        if (!alvo) return;
        if (dias === null) {
            alvo.value = '';
        } else {
            const data = new Date(Date.now() + dias * 86400000);
            alvo.value = this._paraInputLocal(data);
        }
        this._limparErro(alvo.id);
        this.atualizarResumo();
    },

    filtrarGrupos() {
        const termo = (document.getElementById('publicacaoGrupoBusca')?.value || '').trim().toLocaleLowerCase('pt-BR');
        document.querySelectorAll('.publicacao-groups label').forEach(rotulo => {
            rotulo.hidden = Boolean(termo) && !(rotulo.textContent || '').toLocaleLowerCase('pt-BR').includes(termo);
        });
        this.atualizarResumo();
    },

    /** Marca ou desmarca somente os grupos visíveis no filtro atual. */
    marcarGrupos(marcar) {
        document.querySelectorAll('.publicacao-groups label').forEach(rotulo => {
            if (rotulo.hidden) return;
            const caixa = rotulo.querySelector('[name="publicacaoGrupo"]');
            if (caixa) caixa.checked = marcar;
        });
        this._limparErro('publicacaoGruposCampo');
        this.atualizarResumo();
    },

    atualizarResumo() {
        const alvo = document.getElementById('publicacaoResumoEntrega');
        if (!alvo) return;
        const sistema = document.getElementById('publicacaoSistema');
        const idSistema = Number(sistema?.value || 0);
        const nomeSistema = (sistema?.selectedOptions?.[0]?.textContent || '').replace(/\s*—\s*GLOBAL\s*$/i, '').trim();
        const onde = idSistema === 0 ? 'todas as aplicações' : `o sistema ${nomeSistema}`;

        const segmentada = document.getElementById('publicacaoAudiencia')?.value === 'GRUPOS';
        const marcados = document.querySelectorAll('[name="publicacaoGrupo"]:checked').length;
        let quem = 'todos os usuários';
        if (segmentada) quem = marcados ? `${marcados} grupo${marcados > 1 ? 's' : ''} selecionado${marcados > 1 ? 's' : ''}` : 'nenhum grupo selecionado ainda';

        const inicio = document.getElementById('publicacaoInicio')?.value;
        const fim = document.getElementById('publicacaoExpiracao')?.value;
        const quando = inicio ? `a partir de ${this._formatarData(inicio)}` : 'assim que for publicado';
        const ate = fim ? `até ${this._formatarData(fim)}` : 'sem data para expirar';
        const notifica = document.getElementById('publicacaoNotificar')?.checked ? 'com notificação' : 'sem notificação';

        alvo.innerHTML = '';
        const titulo = document.createElement('strong');
        titulo.textContent = 'Resumo da entrega';
        const texto = document.createElement('span');
        texto.textContent = `Aparece em ${onde}, para ${quem}, ${quando}, ${ate}, ${notifica}.`;
        alvo.append(titulo, texto);
    },

    editar(id) {
        const publicacao = (this._config.publicacoes || []).find(item => Number(item.id) === Number(id));
        if (!publicacao) return;
        document.getElementById('publicacaoId').value = publicacao.id;
        document.getElementById('publicacaoTitulo').value = publicacao.titulo || '';
        document.getElementById('publicacaoResumo').value = publicacao.resumo || '';
        document.getElementById('publicacaoConteudo').value = publicacao.conteudo || '';
        document.getElementById('publicacaoPrioridade').value = publicacao.prioridade || 'NORMAL';
        document.getElementById('publicacaoAudiencia').value = publicacao.tipo_audiencia || 'GERAL';
        document.getElementById('publicacaoSistema').value = String(publicacao.id_sistema);
        document.getElementById('publicacaoNotificar').checked = Boolean(publicacao.notificar);
        document.getElementById('publicacaoFixado').checked = Boolean(publicacao.fixado);
        document.getElementById('publicacaoInicio').value = this._paraInputData(publicacao.exibir_a_partir_de);
        document.getElementById('publicacaoExpiracao').value = this._paraInputData(publicacao.expira_em);
        const versao = document.getElementById('publicacaoVersao');
        if (versao) versao.value = publicacao.versao || '';

        const grupos = new Set((publicacao.ids_grupos || []).map(Number));
        document.querySelectorAll('[name="publicacaoGrupo"]').forEach(item => {
            item.checked = grupos.has(Number(item.value));
        });

        const itens = document.getElementById('publicacaoItens');
        if (itens) {
            itens.innerHTML = '';
            (publicacao.itens_atualizacao || []).forEach(item => this.adicionarItem(item));
            if (!(publicacao.itens_atualizacao || []).length) this.adicionarItem();
        }
        this._prepararFormulario();
        window.LuftBase.abrirModal('modalPublicacao');
    },

    alternarAudiencia() {
        const segmentada = document.getElementById('publicacaoAudiencia')?.value === 'GRUPOS';
        const campo = document.getElementById('publicacaoGruposCampo');
        if (campo) campo.hidden = !segmentada;
        if (!segmentada) this._limparErro('publicacaoGruposCampo');
        this.atualizarResumo();
    },

    adicionarItem(item = {}) {
        const container = document.getElementById('publicacaoItens');
        if (!container) return;
        const linha = document.createElement('div');
        linha.className = 'publicacao-item-row';

        const tipo = document.createElement('select');
        tipo.className = 'form-select item-tipo';
        ['NOVO', 'MELHORIA', 'CORRECAO', 'SEGURANCA', 'TECNICO'].forEach(valor => {
            const opcao = document.createElement('option');
            opcao.value = valor;
            opcao.textContent = this._rotuloTipoItem(valor);
            opcao.selected = (item.tipo || 'MELHORIA') === valor;
            tipo.appendChild(opcao);
        });

        const titulo = document.createElement('input');
        titulo.type = 'text';
        titulo.className = 'form-control item-titulo';
        titulo.maxLength = 200;
        titulo.placeholder = 'Título da mudança';
        titulo.value = item.titulo || '';

        const descricao = document.createElement('input');
        descricao.type = 'text';
        descricao.className = 'form-control item-descricao';
        descricao.placeholder = 'Descrição opcional';
        descricao.value = item.descricao || '';

        const remover = document.createElement('button');
        remover.type = 'button';
        remover.className = 'btn btn-outline text-danger';
        remover.title = 'Remover item';
        remover.innerHTML = '<i class="ph-bold ph-trash"></i>';
        remover.addEventListener('click', () => linha.remove());
        linha.append(tipo, titulo, descricao, remover);
        container.appendChild(linha);
    },

    async salvar(evento) {
        evento.preventDefault();
        const publicarAgora = evento.submitter?.dataset.acao === 'publicar';
        const id = document.getElementById('publicacaoId').value;
        const base = this._endpointBase();
        const botoes = Array.from(document.querySelectorAll('#formPublicacao [type="submit"]'));

        const payload = this._coletarPayload();
        const erros = this._validar(payload);
        if (Object.keys(erros).length) {
            this._mostrarErros(erros);
            return;
        }
        if (publicarAgora && !window.confirm('Salvar e publicar agora? As notificações serão geradas para a audiência definida e não será possível editar depois.')) return;

        this._limparErros();
        botoes.forEach(b => this._ocupado(b, true, publicarAgora ? 'Publicando...' : 'Salvando...'));
        try {
            const resposta = await this._requisicao(id ? `${base}/${id}` : base, id ? 'PUT' : 'POST', payload);
            const idPublicacao = id || resposta.dados?.id_publicacao;
            if (publicarAgora) {
                if (!idPublicacao) throw new Error('O rascunho foi salvo, mas não foi possível identificá-lo para publicar. Publique pela lista.');
                try {
                    const pub = await this._requisicao(`${base}/${idPublicacao}/publicar`, 'POST');
                    const agendado = pub.dados?.status === 'AGENDADO';
                    this._toast(agendado ? 'Publicação agendada' : 'Publicação enviada', agendado ? 'A notificação aparecerá na data programada.' : 'A audiência já pode visualizar o conteúdo.', 'success');
                } catch (erroPublicar) {
                    // O rascunho existe: a lista recarrega para o usuário tentar publicar de novo.
                    this._toast('Rascunho salvo, mas não publicado', erroPublicar.message, 'warning');
                }
            } else {
                this._toast('Rascunho salvo', 'Ele ainda não foi entregue. Use "Publicar" na lista quando estiver pronto.', 'success');
            }
            setTimeout(() => window.location.reload(), 600);
        } catch (erro) {
            // O modal permanece aberto com tudo preenchido; o motivo fica visível no topo.
            this._mostrarErros({ _geral: erro.message });
            this._toast('Não foi possível salvar', erro.message, 'error');
            botoes.forEach(b => this._ocupado(b, false, b.dataset.acao === 'publicar' ? 'Salvar e publicar' : 'Salvar rascunho'));
        }
    },

    // ------------------------------------------------------------------
    // Validação e mensagens de erro por campo
    // ------------------------------------------------------------------
    _CAMPOS: {
        titulo: { id: 'publicacaoTitulo', rotulo: 'Título' },
        versao: { id: 'publicacaoVersao', rotulo: 'Versão' },
        conteudo: { id: 'publicacaoConteudo', rotulo: 'Conteúdo' },
        resumo: { id: 'publicacaoResumo', rotulo: 'Resumo' },
        grupos: { id: 'publicacaoGruposCampo', rotulo: 'Grupos destinatários' },
        inicio: { id: 'publicacaoInicio', rotulo: 'Exibir a partir de' },
        expiracao: { id: 'publicacaoExpiracao', rotulo: 'Expirar em' },
    },

    _validar(payload) {
        const erros = {};
        if (!payload.titulo) erros.titulo = 'Informe o título.';
        else if (payload.titulo.length > 200) erros.titulo = `O título aceita até 200 caracteres (atual: ${payload.titulo.length}).`;

        if (this._config.tipo !== 'COMUNICADO' && !payload.versao) erros.versao = 'Informe a versão (ex.: 2.4.0).';
        if (!payload.conteudo) erros.conteudo = 'Escreva o conteúdo completo da publicação.';
        if (payload.resumo.length > 500) erros.resumo = `O resumo aceita até 500 caracteres (atual: ${payload.resumo.length}).`;

        if (payload.tipo_audiencia === 'GRUPOS' && !payload.ids_grupos.length) {
            erros.grupos = 'Marque ao menos um grupo, ou mude a audiência para "Geral".';
        }

        const inicio = payload.exibir_a_partir_de ? new Date(payload.exibir_a_partir_de) : null;
        const fim = payload.expira_em ? new Date(payload.expira_em) : null;
        if (fim && fim <= new Date()) erros.expiracao = 'Essa data de expiração já passou, então a publicação nunca apareceria. Escolha uma data futura ou deixe vazio.';
        else if (inicio && fim && fim <= inicio) erros.expiracao = 'A expiração precisa ser depois de "Exibir a partir de".';
        return erros;
    },

    _mostrarErros(erros) {
        this._limparErros();
        const resumo = document.getElementById('publicacaoErros');
        const lista = [];
        let primeiro = null;
        Object.entries(erros).forEach(([chave, mensagem]) => {
            const campo = this._CAMPOS[chave];
            if (!campo) { lista.push({ rotulo: null, mensagem }); return; }
            const alvo = document.getElementById(campo.id);
            const grupo = alvo?.closest('.publicacao-field') || alvo;
            if (alvo) alvo.classList.add('campo-invalido');
            if (grupo) {
                const aviso = document.createElement('div');
                aviso.className = 'publicacao-erro-campo';
                aviso.dataset.erroDe = campo.id;
                aviso.innerHTML = '<i class="ph-bold ph-x-circle"></i>';
                const texto = document.createElement('span');
                texto.textContent = mensagem;
                aviso.appendChild(texto);
                grupo.appendChild(aviso);
            }
            lista.push({ rotulo: campo.rotulo, mensagem, id: campo.id });
            if (!primeiro && alvo) primeiro = alvo;
        });

        if (resumo) {
            resumo.innerHTML = '';
            const titulo = document.createElement('strong');
            const qtd = lista.length;
            titulo.textContent = qtd > 1 ? `Corrija ${qtd} pontos antes de salvar:` : 'Não foi possível salvar:';
            const ul = document.createElement('ul');
            lista.forEach(item => {
                const li = document.createElement('li');
                if (item.rotulo) {
                    const a = document.createElement('a');
                    a.href = '#';
                    a.textContent = item.rotulo;
                    a.addEventListener('click', e => { e.preventDefault(); this._focar(item.id); });
                    li.append(a, `: ${item.mensagem}`);
                } else {
                    li.textContent = item.mensagem;
                }
                ul.appendChild(li);
            });
            resumo.append(titulo, ul);
            resumo.hidden = false;
            resumo.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
        if (primeiro) this._focar(primeiro.id);
    },

    _focar(id) {
        const alvo = document.getElementById(id);
        if (!alvo) return;
        alvo.scrollIntoView({ behavior: 'smooth', block: 'center' });
        if (typeof alvo.focus === 'function' && alvo.tagName !== 'DIV') alvo.focus({ preventScroll: true });
    },

    _limparErro(id) {
        document.getElementById(id)?.classList.remove('campo-invalido');
        document.querySelectorAll(`[data-erro-de="${id}"]`).forEach(no => no.remove());
    },

    _limparErros() {
        document.querySelectorAll('#formPublicacao .campo-invalido').forEach(no => no.classList.remove('campo-invalido'));
        document.querySelectorAll('#formPublicacao .publicacao-erro-campo').forEach(no => no.remove());
        const resumo = document.getElementById('publicacaoErros');
        if (resumo) { resumo.hidden = true; resumo.innerHTML = ''; }
    },

    async publicar(id) {
        if (!window.confirm('Publicar agora? As notificações serão geradas automaticamente para a audiência definida.')) return;
        try {
            const resposta = await this._requisicao(`${this._endpointBase()}/${id}/publicar`, 'POST');
            const agendado = resposta.dados?.status === 'AGENDADO';
            this._toast(agendado ? 'Publicação agendada' : 'Publicação enviada', agendado ? 'A notificação aparecerá na data programada.' : 'A audiência já pode visualizar o conteúdo.', 'success');
            setTimeout(() => window.location.reload(), 450);
        } catch (erro) {
            this._toast('Falha ao publicar', erro.message, 'error');
        }
    },

    async arquivar(id) {
        if (!window.confirm('Arquivar esta publicação? As notificações vinculadas deixarão de ser exibidas.')) return;
        try {
            await this._requisicao(`${this._endpointBase()}/${id}/arquivar`, 'POST');
            this._toast('Publicação arquivada', 'O item e suas notificações foram encerrados.', 'success');
            setTimeout(() => window.location.reload(), 450);
        } catch (erro) {
            this._toast('Falha ao arquivar', erro.message, 'error');
        }
    },

    filtrar() {
        const busca = (document.getElementById('publicacoesBusca')?.value || '').trim().toLocaleLowerCase('pt-BR');
        const status = document.getElementById('publicacoesFiltroStatus')?.value || '';
        let visiveis = 0;
        document.querySelectorAll('.publicacao-card').forEach(card => {
            const combinaBusca = !busca || (card.dataset.busca || '').includes(busca);
            const combinaStatus = !status || card.dataset.status === status;
            card.hidden = !(combinaBusca && combinaStatus);
            if (!card.hidden) visiveis += 1;
        });
        const vazio = document.getElementById('publicacoesSemResultado');
        if (vazio) vazio.hidden = visiveis > 0 || document.querySelectorAll('.publicacao-card').length === 0;
    },

    _coletarPayload() {
        const audiencia = document.getElementById('publicacaoAudiencia').value;
        const payload = {
            titulo: document.getElementById('publicacaoTitulo').value.trim(),
            resumo: document.getElementById('publicacaoResumo').value.trim(),
            conteudo: document.getElementById('publicacaoConteudo').value.trim(),
            prioridade: document.getElementById('publicacaoPrioridade').value,
            tipo_audiencia: audiencia,
            ids_grupos: audiencia === 'GRUPOS' ? Array.from(document.querySelectorAll('[name="publicacaoGrupo"]:checked')).map(item => Number(item.value)) : [],
            id_sistema: Number(document.getElementById('publicacaoSistema').value || this._config.sistema_atual_id || 0),
            versao: document.getElementById('publicacaoVersao')?.value.trim() || null,
            notificar: document.getElementById('publicacaoNotificar').checked,
            fixado: document.getElementById('publicacaoFixado').checked,
            exibir_a_partir_de: document.getElementById('publicacaoInicio').value || null,
            expira_em: document.getElementById('publicacaoExpiracao').value || null,
            itens_atualizacao: [],
        };
        document.querySelectorAll('.publicacao-item-row').forEach((linha, ordem) => {
            const titulo = linha.querySelector('.item-titulo').value.trim();
            if (!titulo) return;
            payload.itens_atualizacao.push({
                tipo: linha.querySelector('.item-tipo').value,
                titulo,
                descricao: linha.querySelector('.item-descricao').value.trim(),
                ordem,
            });
        });
        return payload;
    },

    async _requisicao(url, metodo, corpo = null) {
        const token = document.querySelector('meta[name="luft-csrf-token"]')?.content || '';
        const opcoes = {
            method: metodo,
            credentials: 'same-origin',
            headers: {
                'Accept': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRF-Token': token,
            },
        };
        if (corpo !== null) {
            opcoes.headers['Content-Type'] = 'application/json';
            opcoes.body = JSON.stringify(corpo);
        }
        const resposta = await fetch(url, opcoes);
        let dados = {};
        try { dados = await resposta.json(); } catch (_erro) { /* resposta não JSON */ }
        if (!resposta.ok || dados.status === 'error') {
            throw new Error(dados.mensagem || dados.message || this._mensagemHttp(resposta.status));
        }
        return dados;
    },

    _mensagemHttp(status) {
        if (status === 401) return 'Sua sessão expirou. Entre novamente e repita a operação.';
        if (status === 403) return 'Você não tem permissão para esta operação, ou a página ficou desatualizada. Recarregue com Ctrl+F5 e tente de novo.';
        if (status === 404) return 'O item não foi encontrado. Ele pode ter sido removido ou pertencer a outro sistema.';
        if (status >= 500) return 'O servidor não conseguiu concluir a operação. Os detalhes estão no log do servidor.';
        return `Erro inesperado na operação (HTTP ${status}).`;
    },

    _endpointBase() {
        return this._config.tipo === 'COMUNICADO' ? this._config.endpoints.comunicados : this._config.endpoints.atualizacoes;
    },

    _paraInputLocal(data) {
        const dois = n => String(n).padStart(2, '0');
        return `${data.getFullYear()}-${dois(data.getMonth() + 1)}-${dois(data.getDate())}T${dois(data.getHours())}:${dois(data.getMinutes())}`;
    },

    _formatarData(valorLocal) {
        const data = new Date(valorLocal);
        if (Number.isNaN(data.getTime())) return valorLocal;
        return data.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
    },

    _paraInputData(valor) {
        return valor ? String(valor).slice(0, 16) : '';
    },

    _rotuloTipoItem(valor) {
        return { NOVO: 'Novo', MELHORIA: 'Melhoria', CORRECAO: 'Correção', SEGURANCA: 'Segurança', TECNICO: 'Técnico' }[valor] || valor;
    },

    _ocupado(botao, ocupado, texto) {
        if (!botao) return;
        botao.disabled = ocupado;
        const icone = botao.dataset.acao === 'publicar' ? 'ph-paper-plane-tilt' : 'ph-floppy-disk';
        botao.innerHTML = ocupado ? `<i class="ph-bold ph-spinner ph-spin"></i> ${texto}` : `<i class="ph-bold ${icone}"></i> ${texto}`;
    },

    _toast(titulo, mensagem, tipo) {
        const lb = window.LuftBase;
        if (lb?.toast) lb.toast(titulo, mensagem, tipo);
        else if (lb?.notificar) lb.notificar(mensagem, tipo === 'error' ? 'danger' : tipo, titulo);
        else if (tipo === 'error') window.alert(`${titulo}: ${mensagem}`);
    },
};

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => LuftPublicacoesPainel.init());
else LuftPublicacoesPainel.init();

