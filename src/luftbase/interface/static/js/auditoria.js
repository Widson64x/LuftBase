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
        arquivo: '',
        fonte: 'luftbase',
        situacao: 'abertos',
        situacaoFila: 'pendentes',
        chaveOpcoes: null,
        controle: null,
        sequencia: 0,
        atualizadoEm: null
    };
    const $ = (id) => document.getElementById(id);
    const numero = new Intl.NumberFormat('pt-BR');
    const dataHora = new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeStyle: 'medium' });
    const abasLocais = new Set(['fisicos']);
    const csrf = () => document.querySelector('meta[name="luft-csrf-token"]')?.getAttribute('content') || '';
    const NOMES_SITUACAO = { ABERTO: 'Aberto', SILENCIADO: 'Silenciado', RESOLVIDO: 'Resolvido' };
    const CLASSES_SITUACAO = { ABERTO: 'error', SILENCIADO: 'warning', RESOLVIDO: 'ok' };
    const NOMES_FILA = { PENDENTE: 'Na fila', ENVIANDO: 'Enviando', ENVIADO: 'Enviado', FALHOU: 'Falhou', CANCELADO: 'Cancelado' };
    const CLASSES_FILA = { PENDENTE: 'warning', ENVIANDO: 'warning', ENVIADO: 'ok', FALHOU: 'error', CANCELADO: 'neutral' };

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
        window.luftDrill?.parametros().forEach((valor, chave) => p.set(chave, valor));
        if (incluirPagina) {
            p.set('pagina', estado.pagina);
            p.set('tamanho', estado.tamanho);
        }
        return p;
    }

    window.luftAuditoriaParametros = parametros;
    window.luftAuditoriaAtualizar = () => { estado.pagina = 1; return atualizar(); };
    window.luftAuditoriaAba = (nome) => raiz.querySelector(`[data-log-tab="${nome}"]`)?.click();

    function parametrosLocais() {
        const p = new URLSearchParams({ limite: '200', fonte: estado.fonte });
        const termo = $('auditTermo').value.trim();
        if (termo) p.set('termo', termo);
        const nivel = $('auditNivelLog')?.value;
        if (nivel) p.set('nivel', nivel);
        if (estado.arquivo) p.set('arquivo', estado.arquivo);
        return p;
    }

    async function obter(url, sinal) {
        const resposta = await fetch(url, { headers: { Accept: 'application/json' }, signal: sinal });
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

    // Mostra qual das duas fontes de log (LuftBase ou Aplicação) está ativa e desliga a que não tem arquivo.
    function atualizarFontes(fontes, ativa) {
        raiz.querySelectorAll('[data-fonte]').forEach(botao => {
            const fonte = (fontes || []).find(item => item.id === botao.dataset.fonte);
            botao.classList.toggle('active', botao.dataset.fonte === ativa);
            botao.disabled = fonte ? !fonte.disponivel && botao.dataset.fonte !== ativa : false;
            botao.title = fonte && !fonte.disponivel ? `Ainda não há ${fonte.arquivo || 'arquivo'} nesta instância.` : botao.title;
        });
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

    const acoesKpi = {
        requisicoes: { drill: {}, ir: 'registros', aba: 'acessos' },
        usuarios: { drill: {}, ir: 'pessoas' },
        erros_servidor: { drill: { resultado: 'servidor' }, ir: 'registros', aba: 'acessos' },
        acessos_negados: { drill: { resultado: 'negado' }, ir: 'registros', aba: 'acessos' },
        duracao_media_ms: { drill: {}, ir: 'desempenho' },
        detalhes: { drill: {}, ir: 'registros', aba: 'detalhes' },
        alteracoes: { drill: {}, ir: 'registros', aba: 'alteracoes' },
        detalhes_criticos: { drill: {}, ir: 'seguranca' },
    };

    function ligarKpis() {
        Object.entries(acoesKpi).forEach(([chave, acao]) => {
            const cartao = raiz.querySelector(`.audit-kpi [data-kpi="${chave}"]`)?.closest('.audit-kpi');
            window.luftDrill?.tornarClicavel(cartao, acao, 'Clique para ver os registros · Shift+clique só filtra os gráficos');
        });
    }

    function renderizarKpis(dados) {
        Object.entries(dados).forEach(([chave, valor]) => {
            const el = raiz.querySelector(`[data-kpi="${chave}"]`);
            if (el) el.textContent = numero.format(valor || 0);
        });
        ligarKpis();
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
            const passo = itens.length > 1 ? new Date(itens[1].intervalo) - new Date(itens[0].intervalo) : 3600000;
            const inicioBarra = item.intervalo.slice(0, 19);
            const fimBarra = new Date(new Date(item.intervalo).getTime() + passo);
            const pad = (n) => String(n).padStart(2, '0');
            const fimTexto = `${fimBarra.getFullYear()}-${pad(fimBarra.getMonth() + 1)}-${pad(fimBarra.getDate())}T${pad(fimBarra.getHours())}:${pad(fimBarra.getMinutes())}:${pad(fimBarra.getSeconds())}`;
            const dia = passo >= 86400000;
            const partes = item.intervalo.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2})/) || [];
            const rotulo = dia ? `${partes[3]}/${partes[2]}` : `${partes[3]}/${partes[2]} ${partes[4]}h`;
            window.luftDrill?.tornarClicavel(barra, { periodo: { inicio: inicioBarra, fim: fimTexto, rotulo }, ir: 'registros', aba: 'acessos' }, 'Clique para ver os registros deste intervalo');
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
            const chaves = { rotas: 'rota', usuarios: 'login', grupos: 'grupo', sistemas: 'sistema_id' };
            if (item.chave !== null && item.chave !== undefined) {
                window.luftDrill?.tornarClicavel(linha, { drill: { [chaves[estado.ranking]]: String(item.chave) }, ir: 'registros', aba: 'acessos' }, 'Clique para ver os registros');
            }
            linha.innerHTML = `<span title="${escapar(item.rotulo)}">${indice + 1}. ${escapar(item.rotulo)}</span><strong>${numero.format(item.total)}</strong><div class="audit-rank-track"><i style="width:${item.total / maximo * 100}%"></i></div>`;
            alvo.appendChild(linha);
        });
    }

    // As listas de usuários, grupos e sistemas pesam: só vão de novo quando muda o período ou o sistema.
    function chaveDasOpcoes() {
        return [$('auditPeriodo').value, $('auditInicio').value, $('auditFim').value, $('auditSistema').value].join('|');
    }

    function aplicarAlertas(contagens) {
        const abertos = contagens ? contagens.abertos : null;
        const kpi = raiz.querySelector('[data-kpi="alertas_abertos"]');
        if (kpi) kpi.textContent = abertos == null ? '—' : numero.format(abertos);
        const sufixo = raiz.querySelector('[data-kpi-suffix="alertas"]');
        if (sufixo && contagens) sufixo.textContent = contagens.silenciados ? `${numero.format(contagens.silenciados)} silenciado(s)` : 'avisando agora';
        [['auditNavAlertas', abertos], ['auditTabAlertas', abertos]].forEach(([id, valor]) => {
            const el = $(id);
            if (!el) return;
            el.hidden = !valor;
            el.textContent = numero.format(valor || 0);
        });
        raiz.querySelectorAll('#auditAlertaSituacoes [data-situacao]').forEach(botao => {
            const total = contagens?.[botao.dataset.situacao];
            botao.querySelector('b').textContent = total == null ? '–' : numero.format(total);
        });
    }

    function aplicarFila(contagens) {
        const aba = $('auditAbaFila');
        if (!aba) return;
        aba.hidden = !contagens; // sem permissao ou tabela ainda nao migrada: a aba nem aparece
        const marca = $('auditTabFila');
        const alerta = contagens ? (contagens.falhas || 0) : 0;
        marca.hidden = !alerta;
        marca.textContent = numero.format(alerta);
        raiz.querySelectorAll('#auditFilaSituacoes [data-situacao-fila]').forEach(botao => {
            const total = contagens?.[botao.dataset.situacaoFila];
            botao.querySelector('b').textContent = total == null ? '–' : numero.format(total);
        });
    }

    async function carregarResumo(sinal, fresco) {
        const p = parametros();
        const chave = chaveDasOpcoes();
        const pedirOpcoes = fresco || estado.chaveOpcoes !== chave;
        if (!pedirOpcoes) p.set('opcoes', '0');
        if (fresco) p.set('fresco', '1');
        const dados = await obter(`${raiz.dataset.resumoUrl}?${p}`, sinal);
        renderizarKpis(dados.indicadores);
        aplicarAlertas(dados.alertas);
        aplicarFila(dados.fila_email);
        renderizarSerie(dados.serie || []);
        estado.rankings = dados.rankings || {};
        renderizarRanking();
        if (dados.opcoes) {
            preencherSelect('auditSistema', dados.opcoes.sistemas || [], { valor: 'todos', texto: 'Todos' });
            preencherSelect('auditUsuario', dados.opcoes.usuarios || [], { valor: '', texto: 'Todos' });
            preencherSelect('auditGrupo', dados.opcoes.grupos || [], { valor: '', texto: 'Todos' });
            estado.chaveOpcoes = chaveDasOpcoes();
        }
        estado.atualizadoEm = Date.now();
        mostrarFrescor();
    }

    function mostrarFrescor() {
        if (!estado.atualizadoEm) return;
        const s = Math.max(0, Math.round((Date.now() - estado.atualizadoEm) / 1000));
        const texto = s < 5 ? 'agora' : s < 60 ? `há ${s} s` : `há ${Math.floor(s / 60)} min`;
        $('auditAtualizadoEm').innerHTML = `<i class="ph-bold ph-check-circle"></i> Atualizado ${texto}`;
    }

    const colunas = {
        acessos: [['id_log', 'ID Log'], ['data_hora', 'Data'], ['sistema', 'Sistema'], ['usuario', 'Usuário'], ['grupo', 'Grupo'], ['metodo', 'Método'], ['rota', 'Rota'], ['status', 'Status'], ['duracao_ms', 'Duração']],
        detalhes: [['id_log', 'ID Log'], ['data_hora', 'Data'], ['sistema', 'Sistema'], ['usuario', 'Usuário'], ['grupo', 'Grupo'], ['acao', 'Ação'], ['recurso', 'Recurso'], ['descricao', 'Descrição'], ['severidade', 'Severidade']],
        alteracoes: [['id_log', 'ID Log'], ['data_hora', 'Data'], ['sistema', 'Sistema'], ['usuario', 'Usuário'], ['acao', 'Ação'], ['recurso', 'Recurso'], ['tipo_alteracao', 'Tipo'], ['campos_alterados', 'Campos']],
        fisicos: [['data_hora', 'Data'], ['nivel', 'Nível'], ['acao', 'Origem'], ['login_usuario', 'Usuário'], ['mensagem', 'Mensagem']],
        fila: [['criado_em', 'Entrou na fila'], ['status', 'Situação'], ['resumo_destinatarios', 'Para'], ['assunto', 'Assunto'], ['origem', 'Origem'], ['tentativas', 'Tentativas'], ['ultimo_erro', 'Último erro'], ['acoes', '']],
        alertas: [['ultima_ocorrencia', 'Última ocorrência'], ['situacao', 'Situação'], ['rotulo', 'Regra'], ['sistema', 'Sistema'], ['login', 'Pessoa'], ['rota', 'Rota'], ['ocorrencias', 'Vezes'], ['ip', 'IP'], ['acoes', '']],
        sessoes: [['criada_em', 'Início'], ['usuario', 'Pessoa'], ['sistema', 'Sistema'], ['navegador', 'Navegador'], ['sistema_operacional', 'SO'], ['ip', 'IP'], ['situacao', 'Situação'], ['duracao_segundos', 'Duração'], ['acoes', '']]
    };

    function valorCelula(chave, item) {
        const valor = item[chave];
        if (chave === 'id_log') return valor == null ? '—' : `<span class="audit-id">#${escapar(valor)}</span>`;
        if (estado.aba === 'fila') {
            if (chave === 'criado_em') return formatarData(valor);
            if (chave === 'status') return `<span class="audit-status ${CLASSES_FILA[valor] || 'neutral'}">${escapar(NOMES_FILA[valor] || valor)}</span>`;
            if (chave === 'tentativas') return `<span class="audit-id">${numero.format(valor || 0)}/${numero.format(item.maximo_tentativas || 0)}</span>`;
            if (chave === 'acoes') {
                if (item.status === 'PENDENTE') return '<button type="button" class="audit-linha-btn perigo" data-fila-acao="cancelar"><i class="ph-bold ph-x-circle"></i> Cancelar</button>';
                if (item.status === 'FALHOU' || item.status === 'CANCELADO') return '<button type="button" class="audit-linha-btn" data-fila-acao="reenviar"><i class="ph-bold ph-arrow-clockwise"></i> Reenviar</button>';
                return '';
            }
        }
        if (estado.aba === 'alertas') {
            if (chave === 'ultima_ocorrencia') return formatarData(valor);
            if (chave === 'situacao') return `<span class="audit-status ${CLASSES_SITUACAO[valor] || 'neutral'}">${escapar(NOMES_SITUACAO[valor] || valor)}</span>`;
            if (chave === 'ocorrencias') return `<span class="audit-id">${numero.format(valor || 0)}×</span>`;
            if (chave === 'acoes') {
                if (valor === undefined && item.situacao === 'RESOLVIDO') return '';
                if (item.situacao === 'SILENCIADO') return '<button type="button" class="audit-linha-btn" data-silenciar="0"><i class="ph-bold ph-bell-ringing"></i> Reativar</button>';
                if (item.situacao === 'ABERTO') {
                    return [1, 8, 24].map(h => `<button type="button" class="audit-linha-btn" data-silenciar="${h}" title="Silenciar por ${h} h"><i class="ph-bold ph-bell-slash"></i> ${h} h</button>`).join('');
                }
                return '';
            }
        }
        if (chave === 'acoes') {
            if (item.atual) return '<span class="audit-voce">sua sessão</span>';
            return estado.podeRevogar && item.ativa
                ? `<button type="button" class="audit-linha-btn perigo" data-ref="${escapar(item.ref)}" data-rotulo="${escapar(item.usuario)}"><i class="ph-bold ph-sign-out"></i> Encerrar</button>`
                : '';
        }
        if (chave === 'data_hora' || chave === 'criada_em') return formatarData(valor);
        if (chave === 'duracao_segundos') return valor == null ? '—' : (valor < 60 ? `${valor} s` : valor < 3600 ? `${Math.round(valor / 60)} min` : `${Math.floor(valor / 3600)} h ${Math.round((valor % 3600) / 60)} min`);
        if (chave === 'situacao') {
            const nomes = window.luftDrill?.MOTIVOS || {};
            const classe = valor === 'Em andamento' ? 'ok' : valor === 'Expirou' ? 'warning' : 'neutral';
            return `<span class="audit-status ${classe}">${escapar(nomes[valor] || valor)}</span>`;
        }
        if (estado.aba === 'fisicos' && chave === 'nivel') {
            const nivel = String(valor || '').toUpperCase();
            const classe = ['ERROR', 'CRITICAL'].includes(nivel) ? 'error' : ['WARNING', 'WARN'].includes(nivel) ? 'warning' : nivel === 'INFO' ? 'ok' : 'neutral';
            return `<span class="audit-status ${classe}">${escapar(nivel)}</span>`;
        }
        if (estado.aba === 'fisicos' && chave === 'acao') return valor ? `<span class="audit-origem">${escapar(valor)}</span>` : '—';
        if (estado.aba === 'fisicos' && chave === 'mensagem') {
            const linhas = String(valor || '').split('\n');
            const extra = linhas.length > 1 ? `<small>+${linhas.length - 1} linha(s)</small>` : '';
            return `<span class="audit-msg">${escapar(linhas[0])}${extra}</span>`;
        }
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
            if (estado.aba === 'fila') {
                tr.querySelectorAll('[data-fila-acao]').forEach(botao => botao.addEventListener('click', (ev) => {
                    ev.stopPropagation();
                    acaoFila(item, botao.dataset.filaAcao, botao);
                }));
                tr.addEventListener('click', () => mostrarNoDrawer(item));
            } else if (estado.aba === 'alertas') {
                tr.querySelectorAll('[data-silenciar]').forEach(botao => botao.addEventListener('click', (ev) => {
                    ev.stopPropagation();
                    silenciarAlerta(item, Number(botao.dataset.silenciar), botao);
                }));
                tr.addEventListener('click', () => mostrarNoDrawer(item));
            } else if (estado.aba === 'sessoes') {
                tr.querySelector('[data-ref]')?.addEventListener('click', (ev) => {
                    ev.stopPropagation(); // o botão não deve abrir a gaveta de detalhes
                    window.luftControle?.encerrarSessao(item.ref, item.usuario);
                });
                tr.addEventListener('click', () => mostrarNoDrawer(item));
            } else if (abasLocais.has(estado.aba)) {
                tr.addEventListener('click', () => mostrarNoDrawer(item)); // a mensagem inteira (inclusive várias linhas)
            } else {
                const tipo = estado.aba === 'acessos' ? 'acesso' : estado.aba === 'detalhes' ? 'detalhe' : 'alteracao';
                tr.addEventListener('click', () => abrirDetalhe(tipo, item.id));
            }
            corpo.appendChild(tr);
        });
    }

    async function silenciarAlerta(item, horas, botao) {
        botao.disabled = true;
        try {
            const url = raiz.dataset.silenciarAlertaUrl.replace('999999', item.id_alerta);
            const resposta = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', Accept: 'application/json', 'X-CSRF-Token': csrf() },
                body: JSON.stringify({ horas })
            });
            const dados = await resposta.json().catch(() => ({}));
            if (!resposta.ok || dados.status !== 'success') throw new Error(dados.message || `Falha HTTP ${resposta.status}`);
            window.luftControle?.avisar(dados.message || 'Pronto.', 'ok');
            await atualizar({ silencioso: true, fresco: true });
        } catch (e) {
            botao.disabled = false;
            window.luftControle?.avisar(e.message || 'Não foi possível alterar o alerta.', 'erro');
        }
    }

    function parametrosAlertas() {
        const p = new URLSearchParams({ situacao: estado.situacao, pagina: estado.pagina, tamanho: estado.tamanho });
        const termo = $('auditTermo').value.trim();
        if (termo) p.set('termo', termo);
        const sistema = $('auditSistema').value;
        if (sistema && sistema !== 'todos') p.set('sistema_id', sistema);
        return p;
    }

    async function acaoFila(item, acao, botao) {
        botao.disabled = true;
        try {
            const url = raiz.dataset.acaoFilaEmailUrl.replace('999999', item.id_email).replace('ACAO', acao);
            const resposta = await fetch(url, {
                method: 'POST',
                headers: { Accept: 'application/json', 'X-CSRF-Token': csrf() }
            });
            const dados = await resposta.json().catch(() => ({}));
            if (!resposta.ok || dados.status !== 'success') throw new Error(dados.message || `Falha HTTP ${resposta.status}`);
            window.luftControle?.avisar(dados.message || 'Pronto.', 'ok');
            await atualizar({ silencioso: true, fresco: true });
        } catch (e) {
            botao.disabled = false;
            window.luftControle?.avisar(e.message || 'Não foi possível alterar o e-mail.', 'erro');
        }
    }

    function parametrosFila() {
        const p = new URLSearchParams({ situacao: estado.situacaoFila, pagina: estado.pagina, tamanho: estado.tamanho });
        const termo = $('auditTermo').value.trim();
        if (termo) p.set('termo', termo);
        return p;
    }

    async function carregarLogs(sinal) {
        let dados;
        if (estado.aba === 'fila') {
            dados = await obter(`${raiz.dataset.filaEmailUrl}?${parametrosFila()}`, sinal);
            aplicarFila(dados.contagens);
        } else if (estado.aba === 'alertas') {
            dados = await obter(`${raiz.dataset.alertasUrl}?${parametrosAlertas()}`, sinal);
            aplicarAlertas(dados.contagens);
        } else if (estado.aba === 'fisicos') {
            dados = await obter(`${raiz.dataset.fisicosUrl}?${parametrosLocais()}`, sinal);
            atualizarFontes(dados.fontes, dados.fonte || estado.fonte);
            preencherArquivos(dados.arquivos || []);
            $('auditArquivo').disabled = false;
        } else {
            const urls = {
                acessos: raiz.dataset.acessosUrl,
                detalhes: raiz.dataset.detalhesUrl,
                alteracoes: raiz.dataset.alteracoesUrl,
                sessoes: raiz.dataset.sessoesUrl
            };
            dados = await obter(`${urls[estado.aba]}?${parametros(true)}`, sinal);
            estado.podeRevogar = !!dados.capacidades?.revogar_sessoes;
        }
        const itens = dados.itens || [];
        estado.total = dados.total || 0;
        renderizarTabela(itens);

        const local = abasLocais.has(estado.aba);
        const paginas = Math.max(Math.ceil(estado.total / estado.tamanho), 1);
        $('auditTotalLinhas').textContent = `${numero.format(estado.total)} registros`;
        $('auditPaginaInfo').textContent = local ? 'Fonte local desta instância' : `Página ${estado.pagina} de ${paginas}`;
        $('auditAlertaSituacoes').hidden = estado.aba !== 'alertas';
        $('auditFilaSituacoes').hidden = estado.aba !== 'fila';
        $('auditPaginaAnterior').disabled = local || estado.pagina <= 1;
        $('auditProximaPagina').disabled = local || estado.pagina >= paginas;
        // Fonte, nível e arquivo só fazem sentido na aba que lê os arquivos de log do servidor.
        ['auditFonteContainer', 'auditNivelContainer', 'auditArquivoContainer'].forEach(id => { $(id).hidden = estado.aba !== 'fisicos'; });
        if ($('auditBtnExportar')) $('auditBtnExportar').hidden = local || ['sessoes', 'alertas', 'fila'].includes(estado.aba);
    }

    // Uma consulta nova cancela a anterior: quem muda três filtros seguidos só vê (e só paga) a última.
    async function atualizar({ silencioso = false, fresco = false } = {}) {
        estado.controle?.abort();
        const controle = new AbortController();
        estado.controle = controle;
        const minha = ++estado.sequencia;
        if (!silencioso) carregando(true);
        erro();
        try {
            await Promise.all([carregarResumo(controle.signal, fresco), carregarLogs(controle.signal)]);
            if (minha !== estado.sequencia) return;
            raiz.dataset.auditoriaPronta = 'true'; // quem carregar depois (outros scripts) sabe que já houve a 1ª carga
            document.dispatchEvent(new CustomEvent('luft:auditoria:atualizada'));
        } catch (e) {
            if (e.name === 'AbortError' || minha !== estado.sequencia) return;
            console.error(e);
            erro(e.message || 'Não foi possível consultar a auditoria.');
        } finally {
            if (minha === estado.sequencia) carregando(false);
        }
    }

    // ---- filtros que se aplicam sozinhos ----------------------------------------------------------
    let adiar = null;
    function aplicarDepois(espera = 350) {
        clearTimeout(adiar);
        adiar = setTimeout(() => { estado.pagina = 1; atualizar(); }, espera);
    }

    function contarExtras() {
        const ativos = [...raiz.querySelectorAll('.audit-field-extra select')].filter(s => s.value).length;
        const marca = $('auditMaisContagem');
        marca.hidden = !ativos;
        marca.textContent = ativos;
        if (ativos) $('auditFiltros').classList.add('mais');
        $('auditBtnMais').setAttribute('aria-expanded', $('auditFiltros').classList.contains('mais') ? 'true' : 'false');
    }

    function limparFiltros() {
        $('auditPeriodo').value = '24';
        ['auditInicio', 'auditFim', 'auditTermo'].forEach(id => { $(id).value = ''; });
        ['auditSistema', 'auditUsuario', 'auditGrupo', 'auditResultado', 'auditSeveridade'].forEach(id => { $(id).selectedIndex = 0; });
        document.querySelectorAll('.audit-custom-date').forEach(el => { el.hidden = true; });
        window.luftDrill?.limpar?.();
        contarExtras();
        estado.pagina = 1;
        atualizar();
    }

    // ---- tempo real: atualiza sozinho, sem spinner, só com a aba visível ----------------------------
    let cronometro = null;
    function tempoReal(ligado) {
        clearInterval(cronometro);
        cronometro = null;
        try { localStorage.setItem('luftAuditoriaTempoReal', ligado ? '1' : '0'); } catch (e) { /* tudo bem */ }
        if (!ligado) return;
        cronometro = setInterval(() => {
            if (document.hidden || $('auditDrawer').classList.contains('open')) return;
            atualizar({ silencioso: true });
        }, 30000);
    }

    function mostrarNoDrawer(dados) {
        const corpo = $('auditDrawerCorpo');
        corpo.replaceChildren();
        Object.entries(dados).filter(([chave]) => !['tipo', 'id', 'ref', 'ativa', 'atual', 'codigo_usuario'].includes(chave)).forEach(([chave, valor]) => {
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
    }

    async function abrirDetalhe(tipo, id) {
        const url = raiz.dataset.registroUrl.replace('TIPO', tipo).replace('999999', id);
        try {
            mostrarNoDrawer(await obter(url));
        } catch (e) {
            erro(e.message || 'Não foi possível abrir o registro.');
        }
    }

    function fecharDrawer() {
        $('auditDrawer').classList.remove('open');
        $('auditDrawer').setAttribute('aria-hidden', 'true');
        $('auditDrawerBackdrop').hidden = true;
    }

    $('auditPeriodo').addEventListener('change', () => {
        document.querySelectorAll('.audit-custom-date').forEach(el => { el.hidden = $('auditPeriodo').value !== 'custom'; });
        if ($('auditPeriodo').value !== 'custom') aplicarDepois(0);
    });
    ['auditInicio', 'auditFim'].forEach(id => $(id).addEventListener('change', () => { if ($('auditInicio').value && $('auditFim').value) aplicarDepois(); }));
    ['auditSistema', 'auditUsuario', 'auditGrupo', 'auditResultado', 'auditSeveridade'].forEach(id => $(id).addEventListener('change', () => { contarExtras(); aplicarDepois(0); }));
    $('auditTermo').addEventListener('input', () => aplicarDepois(500));
    $('auditBtnFiltrar').addEventListener('click', () => { clearTimeout(adiar); estado.pagina = 1; atualizar({ fresco: true }); });
    $('auditBtnAtualizar').addEventListener('click', () => atualizar({ fresco: true }));
    $('auditBtnLimpar').addEventListener('click', limparFiltros);
    $('auditBtnMais').addEventListener('click', () => { $('auditFiltros').classList.toggle('mais'); contarExtras(); });
    $('auditTempoReal').addEventListener('change', () => tempoReal($('auditTempoReal').checked));
    raiz.querySelectorAll('#auditAlertaSituacoes [data-situacao]').forEach(botao => botao.addEventListener('click', () => {
        estado.situacao = botao.dataset.situacao;
        estado.pagina = 1;
        raiz.querySelectorAll('#auditAlertaSituacoes [data-situacao]').forEach(x => x.classList.toggle('active', x === botao));
        carregarLogs().catch(e => erro(e.message));
    }));
    raiz.querySelectorAll('#auditFilaSituacoes [data-situacao-fila]').forEach(botao => botao.addEventListener('click', () => {
        estado.situacaoFila = botao.dataset.situacaoFila;
        estado.pagina = 1;
        raiz.querySelectorAll('#auditFilaSituacoes [data-situacao-fila]').forEach(x => x.classList.toggle('active', x === botao));
        carregarLogs().catch(e => erro(e.message));
    }));
    $('auditTermo').addEventListener('keydown', ev => { if (ev.key === 'Enter') { ev.preventDefault(); clearTimeout(adiar); estado.pagina = 1; atualizar(); } });
    setInterval(mostrarFrescor, 5000);
    $('auditPaginaAnterior').addEventListener('click', () => { if (estado.pagina > 1) { estado.pagina--; carregarLogs(); } });
    $('auditProximaPagina').addEventListener('click', () => { estado.pagina++; carregarLogs(); });
    $('auditArquivo').addEventListener('change', () => { estado.arquivo = $('auditArquivo').value; carregarLogs().catch(e => erro(e.message)); });
    $('auditNivelLog').addEventListener('change', () => { carregarLogs().catch(e => erro(e.message)); });
    raiz.querySelectorAll('[data-fonte]').forEach(botao => botao.addEventListener('click', () => {
        if (botao.disabled || estado.fonte === botao.dataset.fonte) return;
        estado.fonte = botao.dataset.fonte;
        estado.arquivo = ''; // cada fonte tem os seus arquivos
        carregarLogs().catch(e => erro(e.message));
    }));
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
    try {
        if (localStorage.getItem('luftAuditoriaTempoReal') === '1') { $('auditTempoReal').checked = true; tempoReal(true); }
    } catch (e) { /* sem armazenamento: começa desligado */ }
    contarExtras();
    atualizar();
})();
