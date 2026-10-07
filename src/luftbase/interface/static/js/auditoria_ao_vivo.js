/* Auditoria > Ao vivo: quem está online, o que faz, navegadores e atividade recente. */
(() => {
    'use strict';

    const raiz = document.getElementById('luftAuditoria');
    const painel = document.getElementById('auditLive');
    if (!raiz || !painel || painel.dataset.inicializado === 'true') return;
    painel.dataset.inicializado = 'true';

    const INTERVALO_MS = 10000;
    const $ = (id) => document.getElementById(id);
    const numero = new Intl.NumberFormat('pt-BR');
    const estado = { pausado: false, vistos: new Set(), primeira: true, temporizador: null, carregando: false };

    const esc = (valor) => String(valor == null ? '—' : valor).replace(/[&<>"']/g, (c) => (
        { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    ));

    function duracao(segundos) {
        const s = Math.max(0, Math.round(Number(segundos) || 0));
        if (s < 60) return `${s} s`;
        if (s < 3600) return `${Math.floor(s / 60)} min`;
        const h = Math.floor(s / 3600);
        const m = Math.floor((s % 3600) / 60);
        return m ? `${h} h ${m} min` : `${h} h`;
    }

    const iniciais = (nome) => String(nome || '?').trim().split(/\s+/).slice(0, 2).map((p) => p[0]).join('').toUpperCase() || '?';
    const iconeDispositivo = (d) => (d === 'mobile' ? 'ph-device-mobile' : d === 'tablet' ? 'ph-device-tablet' : 'ph-desktop');
    const classeStatus = (s) => (s >= 500 ? 'srv' : s >= 400 ? 'cli' : '');
    const hora = (iso) => {
        const d = new Date(iso);
        return Number.isNaN(d.getTime()) ? '—' : d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    };

    function definirKpi(chave, valor) {
        const el = painel.querySelector(`[data-live="${chave}"]`);
        if (el) el.textContent = numero.format(valor || 0);
    }

    function renderizarKpis(k) {
        ['usuarios_online', 'sessoes_ativas', 'requisicoes_por_minuto', 'tempo_medio_ms', 'erros_15min'].forEach((c) => definirKpi(c, k[c]));
        painel.querySelector('[data-alerta="erros_15min"]')?.classList.toggle('tem', (k.erros_15min || 0) > 0);
        const selo = $('auditNavOnline');
        if (selo) selo.textContent = numero.format(k.usuarios_online || 0);
    }

    function renderizarOnline(lista) {
        const alvo = $('auditLiveOnline');
        if (!lista.length) {
            alvo.innerHTML = '<div class="audit-empty">Ninguém conectado agora.</div>';
            return;
        }
        alvo.innerHTML = lista.map((p) => {
            const fazendo = p.fazendo
                ? `<div class="audit-live-acao"><code>${esc(p.fazendo.metodo)}</code> ${esc(p.fazendo.rota)} <span class="mudo">· há ${duracao(p.fazendo.ha_segundos)}</span></div>`
                : '<div class="audit-live-acao mudo">Sem ação registrada nos últimos 15 min</div>';
            const situacao = p.estado === 'ativo' ? 'Ativo agora' : p.estado === 'recente' ? `Visto há ${duracao(p.inativo_segundos)}` : `Ocioso há ${duracao(p.inativo_segundos)}`;
            return `<div class="audit-live-pessoa" data-estado="${esc(p.estado)}">
                <div class="audit-live-avatar">${esc(iniciais(p.nome))}</div>
                <div><strong>${esc(p.nome)} <span class="mudo" style="font-weight:500">@${esc(p.login)}</span></strong>
                    <small><i class="ph-bold ${iconeDispositivo(p.dispositivo)}"></i> ${esc(p.navegador)} · IP ${esc(p.ip || '—')} · ${esc(p.sistema)}</small>${fazendo}</div>
                <div class="audit-live-dir"><b>${esc(situacao)}</b>conectado há ${duracao(p.conectado_segundos)}</div>
            </div>`;
        }).join('');
    }

    function barras(itens, vazio) {
        if (!itens.length) return `<div class="audit-empty">${vazio}</div>`;
        return itens.map((i) => `<div class="audit-live-barra"><span>${esc(i.nome)}</span><div class="trilho"><span style="width:${Math.max(i.percentual, 3)}%"></span></div><em>${numero.format(i.total)}</em></div>`).join('');
    }

    function renderizarRankings(d) {
        $('auditLiveNavegadores').innerHTML = barras(d.navegadores, 'Sem sessões em atividade.');
        $('auditLiveSistemas').innerHTML = `<div class="audit-live-sep">Sistema operacional</div>${barras(d.sistemas_operacionais, 'Sem dados.')}`
            + `<div class="audit-live-sep">Dispositivo</div>${barras(d.dispositivos.map((x) => ({ ...x, nome: { desktop: 'Computador', mobile: 'Celular', tablet: 'Tablet' }[x.nome] || x.nome })), 'Sem dados.')}`;
    }

    function renderizarFeed(itens) {
        const alvo = $('auditLiveFeed');
        if (!itens.length) {
            alvo.innerHTML = '<div class="audit-empty">Nenhuma ação nos últimos 15 minutos.</div>';
            return;
        }
        const chaveDe = (a) => `${a.data_hora}|${a.login}|${a.metodo}|${a.rota}`;
        alvo.innerHTML = itens.map((a) => {
            const chave = chaveDe(a);
            const nova = !estado.primeira && !estado.vistos.has(chave);
            return `<div class="audit-live-linha ${nova ? 'nova' : ''}">
                <span class="quando">${esc(hora(a.data_hora))}</span><strong>${esc(a.login)}</strong>
                <span class="rota" title="${esc(a.rota)}"><code>${esc(a.metodo)}</code> ${esc(a.rota)}</span>
                <span class="audit-live-status ${classeStatus(a.status)}">${esc(a.status)}</span><span class="dur mudo">${a.duracao_ms == null ? '' : `${numero.format(a.duracao_ms)} ms`}</span></div>`;
        }).join('');
        estado.vistos = new Set(itens.map(chaveDe));
        estado.primeira = false;
    }

    async function carregar() {
        if (estado.carregando) return;
        estado.carregando = true;
        try {
            const p = new URLSearchParams();
            const sistema = $('auditSistema')?.value;
            if (sistema && sistema !== 'todos') p.set('sistema_id', sistema);
            const resposta = await fetch(`${raiz.dataset.tempoRealUrl}?${p}`, { headers: { Accept: 'application/json' }, cache: 'no-store' });
            const dados = await resposta.json().catch(() => ({}));
            if (!resposta.ok || dados.status !== 'success') throw new Error(dados.message || `HTTP ${resposta.status}`);
            const d = dados.data;
            renderizarKpis(d.kpis);
            renderizarOnline(d.online);
            renderizarRankings(d);
            renderizarFeed(d.atividade);
            painel.classList.remove('falha');
            $('auditLiveSub').textContent = `Atualizado às ${hora(d.gerado_em)}`;
        } catch (erro) {
            painel.classList.add('falha');
            $('auditLiveSub').textContent = 'Sem conexão com o servidor; tentando de novo…';
        } finally {
            estado.carregando = false;
        }
    }

    // Só consulta com a aba do navegador visível e o painel realmente à vista (outras abas ficam quietas).
    // Com a seção escondida, só atualiza o contador da aba (a cada 3 ciclos), para não pesar.
    let tique = 0;
    function ciclo() {
        if (estado.pausado || document.hidden) return;
        tique += 1;
        if (painel.offsetParent === null && tique % 3 !== 0) return;
        carregar();
    }

    function definirPausa(pausar) {
        estado.pausado = pausar;
        painel.classList.toggle('pausado', pausar);
        const botao = $('auditLivePausar');
        botao.innerHTML = pausar ? '<i class="ph-bold ph-play"></i> Retomar' : '<i class="ph-bold ph-pause"></i> Pausar';
        if (pausar) $('auditLiveSub').textContent = 'Pausado';
        else carregar();
    }

    $('auditLivePausar').addEventListener('click', () => definirPausa(!estado.pausado));
    $('auditLiveRecolher').addEventListener('click', (ev) => {
        const corpo = $('auditLiveCorpo');
        corpo.hidden = !corpo.hidden;
        ev.currentTarget.setAttribute('aria-expanded', String(!corpo.hidden));
        ev.currentTarget.innerHTML = `<i class="ph-bold ph-caret-${corpo.hidden ? 'down' : 'up'}"></i>`;
    });
    $('auditSistema')?.addEventListener('change', () => { estado.primeira = true; carregar(); });
    document.addEventListener('visibilitychange', () => { if (!document.hidden) ciclo(); });

    carregar();
    estado.temporizador = setInterval(ciclo, INTERVALO_MS);
})();
