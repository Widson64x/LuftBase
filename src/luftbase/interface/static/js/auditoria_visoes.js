/* Auditoria & Análise: navegação por seções e visões analíticas (destaques, mapa de calor, desempenho, segurança, sessões). */
(() => {
    'use strict';

    const raiz = document.getElementById('luftAuditoria');
    if (!raiz || raiz.dataset.visoesInicializadas === 'true') return;
    raiz.dataset.visoesInicializadas = 'true';

    const $ = (id) => document.getElementById(id);
    const numero = new Intl.NumberFormat('pt-BR');
    const CHAVE_VISAO = 'luftAuditoriaVisao';

    const esc = (valor) => String(valor == null ? '—' : valor).replace(/[&<>"']/g, (c) => (
        { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    ));

    function quando(iso) {
        const d = iso ? new Date(iso) : null;
        if (!d || Number.isNaN(d.getTime())) return '—';
        return d.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
    }

    function duracao(segundos) {
        if (segundos == null) return '—';
        const s = Math.max(0, Math.round(segundos));
        if (s < 60) return `${s} s`;
        if (s < 3600) return `${Math.floor(s / 60)} min`;
        const h = Math.floor(s / 3600);
        const m = Math.floor((s % 3600) / 60);
        return m ? `${h} h ${m} min` : `${h} h`;
    }

    // ---- navegação entre seções --------------------------------------------------------------
    const botoes = [...raiz.querySelectorAll('#auditNav [data-visao]')];
    const paineis = [...raiz.querySelectorAll('.audit-panel')];

    function mostrar(nome, salvar = true) {
        if (!paineis.some((p) => p.dataset.painel === nome)) nome = 'geral';
        paineis.forEach((p) => { p.hidden = p.dataset.painel !== nome; });
        botoes.forEach((b) => b.classList.toggle('active', b.dataset.visao === nome));
        if (salvar) {
            try { localStorage.setItem(CHAVE_VISAO, nome); } catch (e) { /* sem armazenamento: tudo bem */ }
        }
    }
    botoes.forEach((b) => b.addEventListener('click', () => mostrar(b.dataset.visao)));
    let inicial = 'geral';
    try { inicial = localStorage.getItem(CHAVE_VISAO) || 'geral'; } catch (e) { /* idem */ }
    mostrar(inicial, false);

    // ---- destaques ----------------------------------------------------------------------------
    function renderizarDestaques(lista) {
        $('auditDestaques').innerHTML = lista.map((d) => `
            <div class="audit-destaque" data-tom="${esc(d.tom)}"><i class="ph-bold ph-${esc(d.icone)}"></i>
                <div><strong>${esc(d.titulo)}</strong><span>${esc(d.texto)}</span></div></div>`).join('');
    }

    // ---- comparação com o período anterior nos KPIs ---------------------------------------------
    function renderizarDeltas(comparativo) {
        const ruins = new Set(['erros_servidor', 'duracao_media_ms']); // subir é ruim
        ['requisicoes', 'usuarios', 'erros_servidor', 'duracao_media_ms'].forEach((chave) => {
            const alvo = raiz.querySelector(`.audit-kpi [data-kpi="${chave}"]`);
            if (!alvo) return;
            alvo.parentElement.querySelector('.audit-delta')?.remove();
            const v = comparativo.variacao[chave];
            if (v == null || v === 0) return;
            const subiu = v > 0;
            const tom = ruins.has(chave) ? (subiu ? 'ruim' : 'bom') : 'neutro';
            const el = document.createElement('em');
            el.className = `audit-delta ${tom}`;
            el.title = `Período anterior: ${numero.format(comparativo.anterior[chave])}`;
            el.innerHTML = `<i class="ph-bold ph-${subiu ? 'arrow-up-right' : 'arrow-down-right'}"></i>${Math.abs(v).toLocaleString('pt-BR')}%`;
            alvo.insertAdjacentElement('afterend', el);
        });
    }

    // ---- mapa de calor ---------------------------------------------------------------------------
    function renderizarMapa(mapa) {
        const alvo = $('auditHeat');
        if (!mapa.maximo) {
            alvo.innerHTML = '<div class="audit-empty">Sem dados no período.</div>';
            $('auditHeatResumo').textContent = '';
            return;
        }
        let html = '<div class="audit-heat-grade"><span></span>';
        for (let h = 0; h < 24; h++) html += `<span class="audit-heat-hora">${h % 3 === 0 ? String(h).padStart(2, '0') : ''}</span>`;
        mapa.dias.forEach((dia, d) => {
            html += `<span class="audit-heat-dia">${esc(dia)}</span>`;
            for (let h = 0; h < 24; h++) {
                const v = mapa.matriz[d][h];
                const nivel = v ? Math.max(Math.round((v / mapa.maximo) * 100), 10) : 0;
                html += `<i class="audit-heat-cel" style="--n:${nivel}%" title="${esc(dia)} ${String(h).padStart(2, '0')}h: ${numero.format(v)} requisições"></i>`;
            }
        });
        alvo.innerHTML = `${html}</div>`;
        $('auditHeatResumo').textContent = mapa.hora_pico == null ? '' : `Pico: ${mapa.dia_pico}, ${String(mapa.hora_pico).padStart(2, '0')}h`;
    }

    // ---- saúde das respostas (rosca) ---------------------------------------------------------------
    function renderizarStatus(status) {
        const itens = [
            ['Sucesso (2xx)', status.sucesso, '#10b981'],
            ['Redirecionamento (3xx)', status.redirecionamento, '#3b82f6'],
            ['Erro do cliente (4xx)', status.erro_cliente, '#f59e0b'],
            ['Erro do servidor (5xx)', status.erro_servidor, '#ef4444'],
        ];
        const total = itens.reduce((a, i) => a + i[1], 0);
        let acumulado = 0;
        const fatias = itens.map(([, v, cor]) => {
            const ini = total ? (acumulado / total) * 100 : 0;
            acumulado += v;
            return `${cor} ${ini}% ${total ? (acumulado / total) * 100 : 0}%`;
        });
        $('auditDonut').style.background = total ? `conic-gradient(${fatias.join(', ')})` : 'var(--luft-bg-app)';
        $('auditDonutTotal').textContent = numero.format(total);
        $('auditStatusLegenda').innerHTML = itens.map(([nome, v, cor]) =>
            `<li><b style="background:${cor}"></b><span>${esc(nome)}</span><em>${numero.format(v)}${total ? ` · ${((v / total) * 100).toFixed(1).replace('.', ',')}%` : ''}</em></li>`).join('');
        const falhas = status.erro_cliente + status.erro_servidor;
        $('auditPerfTaxa').textContent = total ? `${((falhas / total) * 100).toFixed(1).replace('.', ',')}%` : '—';
    }

    // ---- tabelas -----------------------------------------------------------------------------------
    function tabela(id, linhas, colunas, vazio) {
        const alvo = $(id);
        alvo.innerHTML = linhas.length
            ? linhas.map((l) => `<tr>${colunas(l)}</tr>`).join('')
            : `<tr><td colspan="9"><div class="audit-empty">${esc(vazio)}</div></td></tr>`;
    }

    const rota = (r, metodo) => `<td title="${esc(r)}"><span class="audit-method">${esc(metodo || '')}</span> ${esc(r)}</td>`;

    function renderizarDesempenho(d) {
        const a = d.comparativo.atual;
        ['duracao_media_ms', 'requisicoes', 'erros_servidor'].forEach((chave) => {
            const el = raiz.querySelector(`[data-perf="${chave}"]`);
            if (el) el.textContent = numero.format(a[chave]);
        });
        tabela('auditRotasLentas', d.rotas_lentas, (r) =>
            `${rota(r.rota, r.metodo)}<td>${numero.format(r.total)}</td><td><b>${numero.format(r.media_ms)} ms</b></td><td>${numero.format(r.max_ms)} ms</td>`,
            'Nenhuma rota com 3 chamadas ou mais no período.');
        tabela('auditRotasErro', d.rotas_com_erro, (r) =>
            `${rota(r.rota, r.metodo)}<td>${numero.format(r.total)}</td><td>${r.erros_5xx ? `<span class="audit-status error">${r.erros_5xx}</span>` : '—'}</td><td>${r.erros_4xx ? `<span class="audit-status warning">${r.erros_4xx}</span>` : '—'}</td>`,
            'Nenhuma falha no período.');
    }

    function renderizarSeguranca(d) {
        $('auditSecNegados').textContent = numero.format(d.negados.total);
        $('auditSecCriticos').textContent = numero.format(d.criticos.length);
        const badge = $('auditNavSeguranca');
        const alertas = d.negados.total + d.criticos.length;
        badge.hidden = alertas === 0;
        badge.textContent = alertas > 99 ? '99+' : String(alertas);
        tabela('auditNegados', d.negados.itens, (n) =>
            `<td>${esc(quando(n.data_hora))}</td><td><b>${esc(n.login)}</b></td>${rota(n.rota)}<td><code>${esc(n.permissao || '—')}</code></td><td>${esc(n.ip)}</td>`,
            'Nenhum acesso negado no período.');
        tabela('auditCriticos', d.criticos, (c) =>
            `<td>${esc(quando(c.data_hora))}</td><td><b>${esc(c.login)}</b></td><td>${esc(c.acao)}</td><td title="${esc(c.descricao)}">${esc(c.descricao)}</td><td><span class="audit-severity ${esc(c.severidade)}">${esc(c.severidade)}</span></td>`,
            'Nenhum evento crítico no período.');
    }

    function barras(itens, vazio, rotulo = (n) => n) {
        if (!itens.length) return `<div class="audit-empty">${esc(vazio)}</div>`;
        return itens.map((i) => `<div class="audit-live-barra"><span>${esc(rotulo(i.nome))}</span><div class="trilho"><span style="width:${Math.max(i.percentual, 3)}%"></span></div><em>${numero.format(i.total)}</em></div>`).join('');
    }

    const nomeDispositivo = (n) => ({ desktop: 'Computador', mobile: 'Celular', tablet: 'Tablet' }[n] || n);
    const nomeMotivo = (n) => ({
        LOGOUT_VOLUNTARIO: 'Saiu da conta', TIMEOUT_INATIVIDADE: 'Inatividade', ROTACAO_SESSAO: 'Sessão renovada',
        REVOGADA_ADMIN: 'Encerrada por admin', REVOGADA_USUARIO: 'Encerrada pela pessoa',
    }[n] || n);

    function renderizarSessoes(d) {
        const s = d.sessoes;
        $('auditSessLogins').textContent = numero.format(s.total);
        $('auditSessUsuarios').textContent = numero.format(s.usuarios_unicos);
        $('auditSessIps').textContent = numero.format(s.ips_unicos);
        $('auditSessDuracao').textContent = duracao(s.duracao_media_segundos);
        $('auditSessNavegadores').innerHTML = barras(s.navegadores, 'Sem logins no período.')
            + (s.sem_navegador ? `<div class="audit-nota"><i class="ph-bold ph-info"></i> ${numero.format(s.sem_navegador)} sessão(ões) sem navegador registrado (anteriores à captura) ficaram fora desta lista.</div>` : '');
        $('auditSessSistemas').innerHTML = `<div class="audit-live-sep">Sistema operacional</div>${barras(s.sistemas_operacionais, 'Sem dados.')}`
            + `<div class="audit-live-sep">Dispositivo</div>${barras(s.dispositivos, 'Sem dados.', nomeDispositivo)}`;
        $('auditSessMotivos').innerHTML = barras(s.motivos, 'Sem sessões.', nomeMotivo);
        tabela('auditSessIpsTabela', s.ips, (i) =>
            `<td class="mono">${esc(i.ip)}${i.local ? ' <span class="audit-status ok" title="A própria máquina do servidor (ou de quem testa)">local</span>' : ''}</td><td>${numero.format(i.sessoes)}</td><td>${i.usuarios > 1 && !i.local ? `<span class="audit-status warning" title="Várias pessoas no mesmo IP">${i.usuarios}</span>` : i.usuarios}</td>`,
            'Sem dados.');
        tabela('auditUsuariosAtivos', d.usuarios_ativos, (u) =>
            `<td><b>${esc(u.login)}</b></td><td>${numero.format(u.requisicoes)}</td><td>${numero.format(u.rotas)}</td><td>${u.sistemas}</td><td>${u.falhas ? `<span class="audit-status warning">${numero.format(u.falhas)}</span>` : '—'}</td><td>${esc(quando(u.ultimo_acesso))}</td>`,
            'Sem atividade no período.');
    }

    // ---- carga ---------------------------------------------------------------------------------------
    let sequencia = 0;
    async function carregar() {
        const minha = ++sequencia; // descarta respostas antigas se o filtro mudar no meio
        try {
            const p = window.luftAuditoriaParametros ? window.luftAuditoriaParametros() : new URLSearchParams();
            const resposta = await fetch(`${raiz.dataset.insightsUrl}?${p}`, { headers: { Accept: 'application/json' } });
            const dados = await resposta.json().catch(() => ({}));
            if (!resposta.ok || dados.status !== 'success') throw new Error(dados.message || `HTTP ${resposta.status}`);
            if (minha !== sequencia) return;
            const d = dados.data;
            const nota = $('auditDesdeNota');
            if (nota) {
                nota.hidden = !d.dados_a_partir_de;
                if (d.dados_a_partir_de) {
                    nota.innerHTML = `<i class="ph-bold ph-funnel-simple"></i> As análises consideram só os dados a partir de <b>${esc(quando(d.dados_a_partir_de))}</b> (configurado em LUFT_AUDITORIA_DADOS_DESDE).`;
                }
            }
            renderizarDestaques(d.destaques);
            renderizarDeltas(d.comparativo);
            renderizarMapa(d.mapa_calor);
            renderizarStatus(d.status);
            renderizarDesempenho(d);
            renderizarSeguranca(d);
            renderizarSessoes(d);
        } catch (erro) {
            console.error('Auditoria: falha ao carregar as visões', erro);
            $('auditDestaques').innerHTML = `<div class="audit-destaque" data-tom="red"><i class="ph-bold ph-warning-octagon"></i><div><strong>Não foi possível montar as análises</strong><span>${esc(erro.message)}</span></div></div>`;
        }
    }

    document.addEventListener('luft:auditoria:atualizada', carregar);
    if (raiz.dataset.auditoriaPronta === 'true') carregar(); // a 1ª carga pode ter terminado antes deste script
})();
