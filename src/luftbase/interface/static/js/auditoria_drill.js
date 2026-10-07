/* Auditoria: estado dos recortes (drill-down) e barra de filtros ativos, no estilo de um BI.
 *
 * Clique em um gráfico ou tabela => vira um filtro e leva aos registros correspondentes.
 * Shift + clique => só filtra (todos os gráficos se recalculam, sem trocar de seção).
 * Os filtros que já existem como campos do formulário (resultado, severidade, sistema, usuário) continuam
 * sendo os próprios campos: o clique só os preenche, então há uma única fonte de verdade.
 */
(() => {
    'use strict';

    if (window.luftDrill) return;

    const $ = (id) => document.getElementById(id);
    const esc = (valor) => String(valor == null ? '—' : valor).replace(/[&<>"']/g, (c) => (
        { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    ));

    // Filtros guardados aqui (os que o servidor entende e que não têm campo no formulário).
    const PROPRIOS = ['rota', 'metodo', 'ip', 'login', 'grupo', 'navegador', 'hora', 'dia_semana', 'motivo'];
    // Filtros que são campos do formulário: chave -> id do campo, e o valor "sem filtro".
    const CAMPOS = { resultado: ['auditResultado', ''], severidade: ['auditSeveridade', ''], sistema_id: ['auditSistema', 'todos'], usuario_id: ['auditUsuario', ''] };
    const ROTULOS = {
        rota: 'Rota', metodo: 'Método', ip: 'IP', login: 'Pessoa', grupo: 'Grupo', navegador: 'Navegador', hora: 'Hora',
        dia_semana: 'Dia', motivo: 'Término da sessão', resultado: 'Resultado', severidade: 'Severidade',
        sistema_id: 'Sistema', usuario_id: 'Usuário', periodo: 'Período',
    };
    const DIAS = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo'];
    const MOTIVOS = {
        LOGOUT_VOLUNTARIO: 'Saiu da conta', TIMEOUT_INATIVIDADE: 'Inatividade', ROTACAO_SESSAO: 'Sessão renovada',
        REVOGADA_ADMIN: 'Encerrada por admin', REVOGADA_USUARIO: 'Encerrada pela pessoa', LIMPEZA_VISITANTE: 'Visitante',
        ATIVA: 'Em andamento', EXPIRADA: 'Expirou',
    };
    const RESULTADOS = {
        sucesso: 'Sucesso (2xx/3xx)', redirecionamento: 'Redirecionamento (3xx)', cliente: 'Erro do cliente (4xx)',
        servidor: 'Erro do servidor (5xx)', negado: 'Acesso negado',
    };

    const estado = { valores: {}, periodo: null };
    const ouvintes = [];

    function texto(chave, valor) {
        if (chave === 'hora') return `${String(valor).padStart(2, '0')}h`;
        if (chave === 'dia_semana') return DIAS[Number(valor)] || valor;
        if (chave === 'motivo') return MOTIVOS[valor] || valor;
        if (chave === 'resultado') return RESULTADOS[valor] || valor;
        return valor;
    }

    function campo(chave) {
        const par = CAMPOS[chave];
        return par ? $(par[0]) : null;
    }

    /** Lista de filtros ativos (dos recortes e dos campos do formulário), prontos para virar chips. */
    function ativos() {
        const lista = [];
        PROPRIOS.forEach((chave) => {
            if (estado.valores[chave] !== undefined) lista.push({ chave, rotulo: ROTULOS[chave], valor: texto(chave, estado.valores[chave]) });
        });
        Object.entries(CAMPOS).forEach(([chave, [id, vazio]]) => {
            const el = $(id);
            if (el && el.value !== vazio) lista.push({ chave, rotulo: ROTULOS[chave], valor: chave === 'resultado' ? texto(chave, el.value) : (el.selectedOptions[0]?.textContent || el.value) });
        });
        if (estado.periodo) lista.push({ chave: 'periodo', rotulo: ROTULOS.periodo, valor: estado.periodo.rotulo });
        return lista;
    }

    /** Parâmetros que entram na consulta (além dos campos do formulário, que a tela principal já envia). */
    function parametros() {
        const p = new URLSearchParams();
        PROPRIOS.forEach((chave) => { if (estado.valores[chave] !== undefined) p.set(chave, estado.valores[chave]); });
        if (estado.periodo) {
            p.set('inicio', estado.periodo.inicio);
            p.set('fim', estado.periodo.fim);
        }
        return p;
    }

    function desenhar() {
        const barra = $('auditChips');
        if (!barra) return;
        const lista = ativos();
        barra.hidden = lista.length === 0;
        $('auditChipsLista').innerHTML = lista.map((f) =>
            `<span class="audit-chip"><small>${esc(f.rotulo)}</small><b>${esc(f.valor)}</b><button type="button" data-remover="${esc(f.chave)}" aria-label="Remover filtro ${esc(f.rotulo)}"><i class="ph-bold ph-x"></i></button></span>`).join('');
    }

    function mudou(opcoes = {}) {
        desenhar();
        ouvintes.forEach((fn) => fn(opcoes));
        if (opcoes.atualizar !== false && window.luftAuditoriaAtualizar) window.luftAuditoriaAtualizar();
    }

    /** Aplica recortes. Clicar de novo no mesmo valor remove o filtro (alternar). */
    function definir(mapa, opcoes = {}) {
        const { periodo, ...demais } = mapa;
        Object.entries(demais).forEach(([chave, valor]) => {
            if (valor === undefined || valor === null || valor === '') return;
            const el = campo(chave);
            if (el) {
                const novo = String(valor);
                if (![...el.options].some((o) => o.value === novo)) return; // ex.: sistema fora da lista do filtro
                el.value = (el.value === novo && opcoes.alternar) ? CAMPOS[chave][1] : novo;
            } else if (PROPRIOS.includes(chave)) {
                if (estado.valores[chave] === valor && opcoes.alternar) delete estado.valores[chave];
                else estado.valores[chave] = valor;
            }
        });
        if (periodo) estado.periodo = periodo;
        mudou(opcoes);
    }

    function remover(chave) {
        if (chave === 'periodo') estado.periodo = null;
        else if (CAMPOS[chave]) { const el = campo(chave); if (el) el.value = CAMPOS[chave][1]; }
        else delete estado.valores[chave];
        mudou();
    }

    function limpar() {
        estado.valores = {};
        estado.periodo = null;
        Object.entries(CAMPOS).forEach(([chave]) => { const el = campo(chave); if (el) el.value = CAMPOS[chave][1]; });
        mudou();
    }

    /**
     * Clique "drill-through": aplica o recorte e leva aos registros (ou à seção indicada).
     * Com Shift, só filtra e fica onde está.
     */
    function ir(acao, evento) {
        const ficar = !!(evento && (evento.shiftKey || evento.ctrlKey || evento.metaKey));
        const { drill = {}, periodo, ir: secao, aba } = acao;
        // Shift+clique alterna o filtro (clicar de novo remove); o clique normal sempre aplica.
        definir(periodo ? { ...drill, periodo } : drill, { alternar: ficar });
        if (ficar) return;
        if (secao && window.luftAuditoriaVisao) window.luftAuditoriaVisao(secao);
        if (aba && window.luftAuditoriaAba) window.luftAuditoriaAba(aba);
    }

    /** Marca um elemento como clicável (mouse e teclado) e liga a ação. */
    function tornarClicavel(el, acao, dica) {
        if (!el || el.dataset.drill === 'true') return;
        el.dataset.drill = 'true';
        el.classList.add('audit-clicavel');
        el.tabIndex = 0;
        el.setAttribute('role', 'button');
        if (dica) el.title = el.title ? `${el.title}\n${dica}` : dica;
        const executar = (ev) => ir(typeof acao === 'function' ? acao() : acao, ev);
        el.addEventListener('click', executar);
        el.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); executar(ev); } });
    }

    document.addEventListener('click', (ev) => {
        const remove = ev.target.closest?.('[data-remover]');
        if (remove) remover(remove.dataset.remover);
        else if (ev.target.closest?.('#auditChipsLimpar')) limpar();
        else if (ev.target.closest?.('#auditChipsVer') && window.luftAuditoriaVisao) {
            window.luftAuditoriaVisao('registros');
            if (window.luftAuditoriaAba) window.luftAuditoriaAba('acessos');
        }
    });

    // Mudar um campo do formulário também atualiza a barra de filtros.
    document.addEventListener('change', (ev) => {
        if (ev.target.closest?.('.audit-filters')) desenhar();
    });

    window.luftDrill = {
        definir, remover, limpar, ir, tornarClicavel, parametros, ativos, desenhar,
        aoMudar: (fn) => ouvintes.push(fn),
        valor: (chave) => (chave === 'periodo' ? estado.periodo : estado.valores[chave]),
        texto, DIAS, MOTIVOS,
    };
})();
