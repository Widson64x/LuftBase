/* Aba Integracoes do Painel de Controle. Somente leitura: nunca recebe valores secretos. */
(function () {
    'use strict';

    const raiz = document.getElementById('integRaiz');
    if (!raiz) return;

    const URL_DADOS = raiz.dataset.urlDados;
    const URL_VERSAO = raiz.dataset.urlVersao;
    const URL_LOGOS = raiz.dataset.urlLogos || '';
    const ROTULOS_AMBIENTE = { producao: 'Produção', homologacao: 'Homologação', desenvolvimento: 'Desenvolvimento' };
    const ROTULOS_STATUS = { ok: 'Operacional', alerta: 'Atenção', falha: 'Com problema', inativo: 'Inativo' };

    let cartoes = [];
    let filtro = 'Todos';
    let carregado = false;
    let versaoGithub = null;

    const esc = (valor) => String(valor ?? '').replace(/[&<>"']/g, (c) => (
        { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    ));

    async function buscarJson(url) {
        const resposta = await fetch(url, { headers: { Accept: 'application/json' }, credentials: 'same-origin' });
        const corpo = await resposta.json().catch(() => ({}));
        if (!resposta.ok || corpo.status === 'error') throw new Error(corpo.message || 'Falha ao consultar o servidor.');
        return corpo.data;
    }

    function selo(versao) {
        if (!versao) return '';
        const rotulos = {
            atualizada: ['ph-bold ph-check-circle', 'Atualizado'],
            desatualizada: ['ph-bold ph-arrow-circle-up', `Nova versão ${esc(versao.ultima)}`],
            a_frente: ['ph-bold ph-flask', 'Mais novo que o GitHub'],
            indisponivel: ['ph-bold ph-question', 'Não verificado'],
        };
        const [icone, texto] = rotulos[versao.situacao] || rotulos.indisponivel;
        return `<span class="integ-selo-versao ${esc(versao.situacao)}"><i class="${icone}"></i> ${texto}</span>`;
    }

    /** Nomes de arquivo vem do servidor; so letras, numeros, hifen e ponto (nada de caminho ou aspas). */
    function arquivoSeguro(nome) {
        return typeof nome === 'string' && /^[a-z0-9][a-z0-9._-]*$/i.test(nome) ? nome : '';
    }

    /**
     * Logo do cartao: imagem colorida (`imagem`), SVG monocromatico pintado com a cor da ferramenta (`logo`,
     * via mascara CSS) ou, sem nenhum dos dois, o icone padrao.
     */
    function html_logo(c, grande) {
        const imagem = arquivoSeguro(c.imagem);
        const logo = arquivoSeguro(c.logo);
        const classe = `integ-logo ${grande ? 'grande' : ''}`;
        if (imagem) {
            return `<div class="${classe} com-imagem"><img src="${esc(URL_LOGOS + imagem)}" alt="" loading="lazy"></div>`;
        }
        if (logo) {
            return `<div class="${classe} com-logo" style="--cor:${esc(c.cor)}"><span class="integ-logo-mascara" style="--logo:url('${esc(URL_LOGOS + logo + '.svg')}')"></span></div>`;
        }
        return `<div class="${classe}" style="--cor:${esc(c.cor)}"><i class="${esc(c.icone)}"></i></div>`;
    }

    function html_cartao(c, indice) {
        const previa = c.fatos.slice(0, 3).map((f) => `<li><span>${esc(f.rotulo)}</span><span>${esc(f.valor)}</span></li>`).join('');
        const extra = c.id === 'luftbase' ? selo(versaoGithub) : '';
        return `
        <button type="button" class="integ-card" data-id="${esc(c.id)}" style="--cor:${esc(c.cor)}; animation-delay:${indice * 45}ms">
            <div class="integ-topo">
                ${html_logo(c, false)}
                <div><div class="integ-nome">${esc(c.nome)}</div><div class="integ-cat">${esc(c.categoria)}</div></div>
            </div>
            <div class="integ-status"><span class="integ-ponto ${esc(c.status)}"></span><span>${esc(c.resumo)}</span>${extra}</div>
            <ul class="integ-fatos">${previa}</ul>
            <span class="integ-ver-mais">Ver detalhes <i class="ph-bold ph-arrow-right"></i></span>
        </button>`;
    }

    function desenharFiltros() {
        const categorias = ['Todos', ...new Set(cartoes.map((c) => c.categoria))];
        document.getElementById('integFiltros').innerHTML = categorias
            .map((nome) => `<button type="button" class="integ-filtro ${nome === filtro ? 'ativo' : ''}" data-filtro="${esc(nome)}">${esc(nome)}</button>`)
            .join('');
    }

    function desenharGrade() {
        const visiveis = cartoes.filter((c) => filtro === 'Todos' || c.categoria === filtro);
        document.getElementById('integGrade').innerHTML = visiveis.map(html_cartao).join('');
    }

    function desenharResumo(dados) {
        const total = cartoes.length;
        const saudaveis = cartoes.filter((c) => c.status === 'ok').length;
        const problemas = cartoes.filter((c) => c.status === 'falha').length;
        const ambiente = dados.ambiente;
        document.getElementById('integAmbiente').className = `integ-chip amb-${esc(ambiente)}`;
        document.getElementById('integAmbiente').innerHTML = `<i class="ph-bold ph-globe-hemisphere-west"></i> ${esc(ROTULOS_AMBIENTE[ambiente] || ambiente)}`;
        document.getElementById('integResumo').textContent = problemas
            ? `${saudaveis} de ${total} integrações operacionais · ${problemas} com problema`
            : `${saudaveis} de ${total} integrações operacionais`;
    }

    async function carregar() {
        const grade = document.getElementById('integGrade');
        grade.innerHTML = '<div class="integ-esqueleto"></div>'.repeat(6);
        try {
            const dados = await buscarJson(URL_DADOS);
            cartoes = dados.cartoes;
            carregado = true;
            desenharResumo(dados);
            desenharFiltros();
            desenharGrade();
            verificarVersao(false);
        } catch (erro) {
            grade.innerHTML = `<div class="integ-aviso" style="grid-column:1/-1"><i class="ph-bold ph-warning"></i> ${esc(erro.message)}</div>`;
        }
    }

    async function verificarVersao(forcar) {
        const botao = document.getElementById('integBtnVersao');
        if (botao) botao.disabled = true;
        try {
            versaoGithub = await buscarJson(URL_VERSAO + (forcar ? '?forcar=1' : ''));
        } catch (erro) {
            versaoGithub = { situacao: 'indisponivel', instalada: '', ultima: null, detalhe: erro.message };
        }
        document.getElementById('integVersaoSelo').innerHTML = selo(versaoGithub);
        if (carregado) desenharGrade();
        const aberto = document.getElementById('integModal');
        if (aberto && aberto.dataset.cartao === 'luftbase') abrirDetalhe('luftbase');
        if (botao) botao.disabled = false;
    }

    function html_segredo(s) {
        const campos = s.campos.map((campo) => (campo.visivel
            ? `<span class="integ-campo"><em>${esc(campo.nome)}</em> ${esc(campo.valor)}</span>`
            : `<span class="integ-campo oculto" title="Valor protegido: não é enviado ao navegador"><i class="ph-bold ph-lock-simple"></i> ${esc(campo.nome)}</span>`
        )).join('');
        const estado = s.erro
            ? `<span style="color:var(--luft-danger-500)"><i class="ph-bold ph-prohibit"></i> ${esc(s.erro)}</span>`
            : s.existe
                ? '<span style="color:var(--luft-success-600)"><i class="ph-bold ph-check-circle"></i> Encontrado</span>'
                : '<span style="color:var(--luft-danger-500)"><i class="ph-bold ph-x-circle"></i> Não existe no Vault</span>';
        const meta = s.existe
            ? `<div class="integ-meta">${s.versao ? `<span>Versão ${esc(s.versao)}</span>` : ''}${s.atualizado_em ? `<span>Atualizado em ${esc(new Date(s.atualizado_em).toLocaleString('pt-BR'))}</span>` : ''}<span>${s.campos.length} campos</span></div>`
            : '';
        const uso = (s.usado_por && s.usado_por.length) ? `<div class="integ-uso">Usado por: ${s.usado_por.map(esc).join(', ')}</div>` : '';
        return `
        <div class="integ-segredo">
            <div class="integ-segredo-topo">
                <div><div class="integ-caminho">${esc(s.caminho)}</div><div style="margin-top:6px;font-size:.78rem">${estado}</div></div>
                <button type="button" class="integ-copiar" data-copiar="${esc(s.caminho)}" title="Copiar caminho"><i class="ph-bold ph-copy"></i></button>
            </div>
            ${meta}
            ${campos ? `<div class="integ-campos">${campos}</div>` : ''}
            ${uso}
        </div>`;
    }

    function html_versao_luftbase() {
        const v = versaoGithub;
        if (!v) return '<div class="integ-aviso">Verificando a versão no GitHub…</div>';
        const aviso = {
            desatualizada: 'Há uma versão mais nova publicada. Atualize a linha <code>luft-base @ git+…@v…</code> do requirements.txt da aplicação.',
            a_frente: 'A versão instalada é mais nova que a última tag publicada no GitHub.',
            indisponivel: `Não foi possível comparar com o GitHub${v.detalhe ? ` (${esc(v.detalhe)})` : ''}.`,
            atualizada: 'Esta aplicação usa a versão mais recente publicada.',
        }[v.situacao];
        return `
        <div class="integ-versao-box">
            <div><div class="rot">Instalada</div><div class="num">${esc(v.instalada)}</div></div>
            <div><div class="rot">Última no GitHub</div><div class="num">${esc(v.ultima || '—')}</div></div>
            <div>${selo(v)}</div>
            <button type="button" class="btn btn-outline btn-sm" id="integBtnRever"><i class="ph-bold ph-arrows-clockwise"></i> Verificar agora</button>
        </div>
        <p style="font-size:.8rem;color:var(--luft-text-muted);margin:10px 0 0">${aviso}
            ${v.repositorio ? `<a href="${esc(v.url)}" target="_blank" rel="noopener noreferrer">Ver tags no GitHub</a>` : ''}</p>`;
    }

    function abrirDetalhe(id) {
        const c = cartoes.find((item) => item.id === id);
        if (!c) return;
        const modal = document.getElementById('integModal');
        modal.dataset.cartao = id;
        modal.querySelector('.luft-modal-title').innerHTML = `<i class="${esc(c.icone)}" style="color:${esc(c.cor)}"></i> ${esc(c.nome)}`;
        const fatos = c.fatos.map((f) => `<tr><td>${esc(f.rotulo)}</td><td>${esc(f.valor)}</td></tr>`).join('');
        const segredos = c.segredos.length
            ? `<div class="integ-sec-titulo">${c.id === 'vault' ? 'Todos os segredos em uso por esta aplicação' : 'Segredos no Vault'}</div>${c.segredos.map(html_segredo).join('')}
               <p style="font-size:.74rem;color:var(--luft-text-muted)"><i class="ph-bold ph-lock-simple"></i> Senhas, tokens e chaves nunca saem do servidor: aqui aparecem apenas os caminhos e os nomes dos campos.</p>`
            : '';
        document.getElementById('integModalCorpo').innerHTML = `
            <div class="integ-modal-cab">
                ${html_logo(c, true)}
                <div>
                    <h4>${esc(c.nome)}</h4>
                    <p>${esc(c.descricao)}</p>
                    <div class="integ-status" style="margin-top:8px"><span class="integ-ponto ${esc(c.status)}"></span><strong>${esc(ROTULOS_STATUS[c.status] || c.status)}</strong> · ${esc(c.resumo)}</div>
                </div>
            </div>
            ${c.id === 'luftbase' ? `<div class="integ-sec-titulo">Versão e atualização</div>${html_versao_luftbase()}` : ''}
            <div class="integ-sec-titulo">${c.id === 'componentes' ? 'Versões instaladas' : 'Visão geral'}</div>
            <table class="integ-tabela"><tbody>${fatos}</tbody></table>
            ${segredos}`;
        LuftBase.abrirModal('integModal');
    }

    raiz.addEventListener('click', (evento) => {
        const cartao = evento.target.closest('.integ-card');
        if (cartao) return abrirDetalhe(cartao.dataset.id);
        const f = evento.target.closest('.integ-filtro');
        if (f) { filtro = f.dataset.filtro; desenharFiltros(); desenharGrade(); }
    });

    document.getElementById('integModal').addEventListener('click', async (evento) => {
        const copiar = evento.target.closest('[data-copiar]');
        if (copiar) {
            try { await navigator.clipboard.writeText(copiar.dataset.copiar); copiar.innerHTML = '<i class="ph-bold ph-check"></i>'; } catch (e) { /* sem permissao de area de transferencia */ }
            setTimeout(() => { copiar.innerHTML = '<i class="ph-bold ph-copy"></i>'; }, 1200);
        }
        if (evento.target.closest('#integBtnRever')) verificarVersao(true);
    });

    document.getElementById('integBtnAtualizar').addEventListener('click', () => carregar());
    document.getElementById('integBtnVersao').addEventListener('click', () => verificarVersao(true));

    // Carrega so quando a aba e aberta (evita consultar o Vault em todo acesso ao painel).
    function aoAbrirAba() { if (!carregado) carregar(); }
    document.querySelectorAll('.painel-wrapper .luft-tab-btn').forEach((botao) => {
        if ((botao.getAttribute('onclick') || '').includes('tab-integracoes')) botao.addEventListener('click', aoAbrirAba);
    });
    if (document.getElementById('tab-integracoes').classList.contains('ativo')) aoAbrirAba();
    new MutationObserver(() => { if (document.getElementById('tab-integracoes').classList.contains('ativo')) aoAbrirAba(); })
        .observe(document.getElementById('tab-integracoes'), { attributes: true, attributeFilter: ['class'] });
})();
