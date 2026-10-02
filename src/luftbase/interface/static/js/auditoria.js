(() => {
    'use strict';

    const raiz = document.getElementById('luftAuditoria');
    if (!raiz || raiz.dataset.inicializado === 'true') return;
    raiz.dataset.inicializado = 'true';

    const estado = {
        pagina: 1,
        tamanho: 50,
        aba: 'acessos',
        rankings: {},
        ranking: 'rotas',
        total: 0,
        arquivo: ''
    };
    const $ = (id) => document.getElementById(id);
    const numero = new Intl.NumberFormat('pt-BR');
    const dataHora = new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeStyle: 'medium' });
    const abasLocais = new Set(['temporarios', 'fisicos']);

    function escapar(valor) {
        const el = document.createElement('span');
        el.textContent = valor == null ? '—' : String(valor);
        return el.innerHTML;
    }

    function formatarData(valor) {
        if (!valor) return '—';
        const data = new Date(valor);
        return Number.isNaN(data.getTime()) ? escapar(valor) : escapar(dataHora.format(data));
    }

    function parametros(incluirPagina = false) {
        const p = new URLSearchParams();
        const periodo = $('auditPeriodo').value;
        const fim = new Date();
        if (periodo === 'custom') {
            if ($('auditInicio').value) p.set('inicio', $('auditInicio').value);
            if ($('auditFim').value) p.set('fim', $('auditFim').value);
        } else {
            p.set('inicio', new Date(fim.getTime() - Number(periodo) * 3600000).toISOString());
            p.set('fim', fim.toISOString());
        }
        [['sistema_id', 'auditSistema'], ['usuario_id', 'auditUsuario'], ['grupo_id', 'auditGrupo'], ['resultado', 'auditResultado'], ['severidade', 'auditSeveridade'], ['termo', 'auditTermo']].forEach(([chave, id]) => {
            const valor = $(id)?.value?.trim();
            if (valor) p.set(chave, valor);
        });
        if (incluirPagina) {
            p.set('pagina', estado.pagina);
            p.set('tamanho', estado.tamanho);
        }
        return p;
    }

    function parametrosLocais() {
        const p = new URLSearchParams({ limite: '200' });
        const termo = $('auditTermo').value.trim();
        if (termo) p.set('termo', termo);
        if ($('auditUsuario').value) p.set('usuario_id', $('auditUsuario').value);
        if ($('auditGrupo').value) p.set('grupo_id', $('auditGrupo').value);
        if (estado.arquivo && estado.aba === 'fisicos') p.set('arquivo', estado.arquivo);
        return p;
    }

    async function obter(url) {
        const resposta = await fetch(url, { headers: { Accept: 'application/json' } });
        const dados = await resposta.json().catch(() => ({}));
        if (!resposta.ok || dados.status !== 'success') {
            throw new Error(dados.message || `Falha HTTP ${resposta.status}`);
        }
        return dados.data || dados;
    }

    function carregando(ativo) { $('auditLoading').hidden = !ativo; }
    function erro(mensagem = '') { $('auditErro').hidden = !mensagem; $('auditErro').textContent = mensagem; }

    function preencherSelect(id, itens, primeiro) {
        const select = $(id);
        const atual = select.value;
        select.replaceChildren();
        const inicial = document.createElement('option');
        inicial.value = primeiro.valor;
        inicial.textContent = primeiro.texto;
        select.appendChild(inicial);
        itens.forEach(item => {
            const op = document.createElement('option');
            op.value = item.id;
            op.textContent = item.nome;
            select.appendChild(op);
        });
        if ([...select.options].some(op => op.value === atual)) select.value = atual;
    }

    function preencherArquivos(arquivos) {
        const select = $('auditArquivo');
        const anterior = estado.arquivo;
        select.replaceChildren();
        arquivos.forEach(item => {
            const op = document.createElement('option');
            op.value = item.nome;
            op.textContent = `${item.nome}${item.atual ? ' (atual)' : ''}`;
            select.appendChild(op);
        });
        if ([...select.options].some(op => op.value === anterior)) select.value = anterior;
        estado.arquivo = select.value || '';
    }

    function renderizarKpis(dados) {
        Object.entries(dados).forEach(([chave, valor]) => {
            const el = raiz.querySelector(`[data-kpi="${chave}"]`);
            if (el) el.textContent = numero.format(valor || 0);
        });
        const taxa = raiz.querySelector('[data-kpi-suffix="taxa_erro"]');
        if (taxa) taxa.textContent = `${Number(dados.taxa_erro || 0).toLocaleString('pt-BR')}% das requisições`;
    }

    function renderizarSerie(itens) {
        const alvo = $('auditTimeline');
        alvo.replaceChildren();
        if (!itens.length) {
            alvo.innerHTML = '<div class="audit-empty">Sem dados no período.</div>';
            return;
        }
        const maximo = Math.max(...itens.map(item => item.total), 1);
        itens.forEach(item => {
            const barra = document.createElement('div');
            barra.className = 'audit-bar';
            barra.style.height = `${Math.max(item.total / maximo * 100, 2)}%`;
            barra.style.setProperty('--erro', `${item.total ? item.erros / item.total * 100 : 0}%`);
            barra.style.setProperty('--negado', `${item.total ? item.negados / item.total * 100 : 0}%`);
            barra.title = `${formatarData(item.intervalo)}\n${item.total} requisições · ${item.erros} erros · ${item.negados} negados`;
            alvo.appendChild(barra);
        });
    }

    function renderizarRanking() {
        const itens = estado.rankings[estado.ranking] || [];
        const alvo = $('auditRanking');
        alvo.replaceChildren();
        if (!itens.length) {
            alvo.innerHTML = '<div class="audit-empty">Sem dados no período.</div>';
            return;
        }
        const maximo = Math.max(...itens.map(item => item.total), 1);
        itens.forEach((item, indice) => {
            const linha = document.createElement('div');
            linha.className = 'audit-rank-row';
            linha.innerHTML = `<span title="${escapar(item.rotulo)}">${indice + 1}. ${escapar(item.rotulo)}</span><strong>${numero.format(item.total)}</strong><div class="audit-rank-track"><i style="width:${item.total / maximo * 100}%"></i></div>`;
            alvo.appendChild(linha);
        });
    }

    async function carregarResumo() {
        const dados = await obter(`${raiz.dataset.resumoUrl}?${parametros()}`);
        renderizarKpis(dados.indicadores);
        renderizarSerie(dados.serie || []);
        estado.rankings = dados.rankings || {};
        renderizarRanking();
        preencherSelect('auditSistema', dados.opcoes?.sistemas || [], { valor: 'todos', texto: 'Todos' });
        preencherSelect('auditUsuario', dados.opcoes?.usuarios || [], { valor: '', texto: 'Todos' });
        preencherSelect('auditGrupo', dados.opcoes?.grupos || [], { valor: '', texto: 'Todos' });
        $('auditAtualizadoEm').innerHTML = `<i class="ph-bold ph-check-circle"></i> Atualizado às ${new Date().toLocaleTimeString('pt-BR')}`;
    }

    const colunas = {
        acessos: [['id_log', 'ID Log'], ['data_hora', 'Data'], ['sistema', 'Sistema'], ['usuario', 'Usuário'], ['grupo', 'Grupo'], ['metodo', 'Método'], ['rota', 'Rota'], ['status', 'Status'], ['duracao_ms', 'Duração']],
        detalhes: [['id_log', 'ID Log'], ['data_hora', 'Data'], ['sistema', 'Sistema'], ['usuario', 'Usuário'], ['grupo', 'Grupo'], ['acao', 'Ação'], ['recurso', 'Recurso'], ['descricao', 'Descrição'], ['severidade', 'Severidade']],
        alteracoes: [['id_log', 'ID Log'], ['data_hora', 'Data'], ['sistema', 'Sistema'], ['usuario', 'Usuário'], ['acao', 'Ação'], ['recurso', 'Recurso'], ['tipo_alteracao', 'Tipo'], ['campos_alterados', 'Campos']],
        temporarios: [['data_hora', 'Data'], ['nivel', 'Nível'], ['login_usuario', 'Usuário'], ['acao', 'Ação'], ['recurso', 'Recurso'], ['mensagem', 'Mensagem']],
        fisicos: [['data_hora', 'Data'], ['arquivo', 'Arquivo'], ['nivel', 'Nível'], ['login_usuario', 'Usuário'], ['acao', 'Ação'], ['mensagem', 'Mensagem']]
    };

    function valorCelula(chave, item) {
        const valor = item[chave];
        if (chave === 'id_log') return valor == null ? '—' : `<span class="audit-id">#${escapar(valor)}</span>`;
        if (chave === 'data_hora') return formatarData(valor);
        if (chave === 'metodo') return `<span class="audit-method">${escapar(valor)}</span>`;
        if (chave === 'status') {
            const classe = valor >= 500 ? 'error' : valor >= 400 ? 'warning' : 'ok';
            return `<span class="audit-status ${classe}">${escapar(valor)}</span>`;
        }
        if (chave === 'severidade') return `<span class="audit-severity ${escapar(valor)}">${escapar(valor)}</span>`;
        if (chave === 'duracao_ms') return valor == null ? '—' : `${numero.format(valor)} ms`;
        return escapar(valor);
    }

    function renderizarTabela(itens) {
        const defs = colunas[estado.aba];
        $('auditTabelaCabecalho').innerHTML = `<tr>${defs.map(([, titulo]) => `<th>${titulo}</th>`).join('')}</tr>`;
        const corpo = $('auditTabelaCorpo');
        corpo.replaceChildren();
        if (!itens.length) {
            corpo.innerHTML = `<tr><td colspan="${defs.length}"><div class="audit-empty">Nenhum registro encontrado.</div></td></tr>`;
            return;
        }
        itens.forEach(item => {
            const tr = document.createElement('tr');
            tr.innerHTML = defs.map(([chave]) => `<td title="${escapar(item[chave])}">${valorCelula(chave, item)}</td>`).join('');
            if (!abasLocais.has(estado.aba)) {
                const tipo = estado.aba === 'acessos' ? 'acesso' : estado.aba === 'detalhes' ? 'detalhe' : 'alteracao';
                tr.addEventListener('click', () => abrirDetalhe(tipo, item.id));
            }
            corpo.appendChild(tr);
        });
    }

    async function carregarLogs() {
        let dados;
        if (estado.aba === 'temporarios') {
            dados = await obter(`${raiz.dataset.temporariosUrl}?${parametrosLocais()}`);
        } else if (estado.aba === 'fisicos') {
            dados = await obter(`${raiz.dataset.fisicosUrl}?${parametrosLocais()}`);
            preencherArquivos(dados.arquivos || []);
        } else {
            const urls = {
                acessos: raiz.dataset.acessosUrl,
                detalhes: raiz.dataset.detalhesUrl,
                alteracoes: raiz.dataset.alteracoesUrl
            };
            dados = await obter(`${urls[estado.aba]}?${parametros(true)}`);
        }
        const itens = dados.itens || [];
        estado.total = dados.total || 0;
        renderizarTabela(itens);

        const local = abasLocais.has(estado.aba);
        const paginas = Math.max(Math.ceil(estado.total / estado.tamanho), 1);
        $('auditTotalLinhas').textContent = `${numero.format(estado.total)} registros`;
        $('auditPaginaInfo').textContent = local ? 'Fonte local desta instância' : `Página ${estado.pagina} de ${paginas}`;
        $('auditPaginaAnterior').disabled = local || estado.pagina <= 1;
        $('auditProximaPagina').disabled = local || estado.pagina >= paginas;
        $('auditArquivoContainer').hidden = estado.aba !== 'fisicos';
        if ($('auditBtnExportar')) $('auditBtnExportar').hidden = local;
    }

    async function atualizar() {
        carregando(true);
        erro();
        try {
            await Promise.all([carregarResumo(), carregarLogs()]);
        } catch (e) {
            console.error(e);
            erro(e.message || 'Não foi possível consultar a auditoria.');
        } finally {
            carregando(false);
        }
    }

    async function abrirDetalhe(tipo, id) {
        const url = raiz.dataset.registroUrl.replace('TIPO', tipo).replace('999999', id);
        try {
            const dados = await obter(url);
            const corpo = $('auditDrawerCorpo');
            corpo.replaceChildren();
            Object.entries(dados).filter(([chave]) => !['tipo', 'id'].includes(chave)).forEach(([chave, valor]) => {
                const dl = document.createElement('dl');
                dl.className = 'audit-detail-row';
                const dt = document.createElement('dt');
                dt.textContent = chave.replaceAll('_', ' ');
                const dd = document.createElement('dd');
                dd.textContent = valor == null ? '—' : typeof valor === 'object' ? JSON.stringify(valor, null, 2) : String(valor);
                dl.append(dt, dd);
                corpo.appendChild(dl);
            });
            $('auditDrawer').classList.add('open');
            $('auditDrawer').setAttribute('aria-hidden', 'false');
            $('auditDrawerBackdrop').hidden = false;
        } catch (e) {
            erro(e.message || 'Não foi possível abrir o registro.');
        }
    }

    function fecharDrawer() {
        $('auditDrawer').classList.remove('open');
        $('auditDrawer').setAttribute('aria-hidden', 'true');
        $('auditDrawerBackdrop').hidden = true;
    }

    $('auditPeriodo').addEventListener('change', () => document.querySelectorAll('.audit-custom-date').forEach(el => { el.hidden = $('auditPeriodo').value !== 'custom'; }));
    $('auditBtnFiltrar').addEventListener('click', () => { estado.pagina = 1; atualizar(); });
    $('auditBtnAtualizar').addEventListener('click', atualizar);
    $('auditTermo').addEventListener('keydown', ev => { if (ev.key === 'Enter') { ev.preventDefault(); estado.pagina = 1; atualizar(); } });
    $('auditPaginaAnterior').addEventListener('click', () => { if (estado.pagina > 1) { estado.pagina--; carregarLogs(); } });
    $('auditProximaPagina').addEventListener('click', () => { estado.pagina++; carregarLogs(); });
    $('auditArquivo').addEventListener('change', () => { estado.arquivo = $('auditArquivo').value; carregarLogs().catch(e => erro(e.message)); });
    $('auditDrawerFechar').addEventListener('click', fecharDrawer);
    $('auditDrawerBackdrop').addEventListener('click', fecharDrawer);
    raiz.querySelectorAll('[data-ranking]').forEach(btn => btn.addEventListener('click', () => {
        raiz.querySelectorAll('[data-ranking]').forEach(x => x.classList.toggle('active', x === btn));
        estado.ranking = btn.dataset.ranking;
        renderizarRanking();
    }));
    raiz.querySelectorAll('[data-log-tab]').forEach(btn => btn.addEventListener('click', () => {
        raiz.querySelectorAll('[data-log-tab]').forEach(x => x.classList.toggle('active', x === btn));
        estado.aba = btn.dataset.logTab;
        estado.pagina = 1;
        estado.arquivo = '';
        carregarLogs().catch(e => erro(e.message));
    }));
    $('auditBtnExportar')?.addEventListener('click', () => {
        const p = parametros();
        const tipos = { acessos: 'acesso', detalhes: 'detalhe', alteracoes: 'alteracao' };
        p.set('tipo', tipos[estado.aba] || 'acesso');
        window.location.assign(`${raiz.dataset.exportarUrl}?${p}`);
    });
    document.addEventListener('keydown', ev => { if (ev.key === 'Escape') fecharDrawer(); });
    atualizar();
})();
