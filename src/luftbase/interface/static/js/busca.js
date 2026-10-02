/**
 * Busca global da barra superior.
 *
 * - Menu: pesquisa, no navegador, os itens do menu lateral (ja filtrados por permissao no servidor).
 * - Provedores: pergunta ao servidor (`data-busca-url`), que consulta o que a aplicacao registrou
 *   (CTCs, cadastros...). Resultados chegam agrupados e so de quem tem permissao.
 * Atalhos: Ctrl+K (ou /) foca a busca; setas navegam; Enter abre; Esc fecha.
 */
const LuftBusca = {
    ATRASO_MS: 250,
    MINIMO_REMOTO: 2,

    iniciar() {
        this.entrada = document.querySelector('.luft-search-input');
        if (!this.entrada) return;
        this.caixa = this.entrada.closest('.luft-search-box');
        this.urlRemota = this.entrada.dataset.buscaUrl || '';
        this.indice = this._indexarMenu();
        this.itens = [];
        this.ativo = -1;
        this.contador = 0;
        this.remotos = [];
        this.carregando = false;

        this.entrada.setAttribute('autocomplete', 'off');
        this.entrada.setAttribute('role', 'combobox');
        this.entrada.setAttribute('aria-expanded', 'false');
        this.entrada.setAttribute('aria-controls', 'luft-busca-lista');
        this.entrada.setAttribute('aria-autocomplete', 'list');
        this.entrada.setAttribute('aria-label', 'Buscar no sistema');

        const dica = document.createElement('kbd');
        dica.className = 'luft-search-kbd';
        dica.textContent = /Mac/i.test(navigator.platform) ? '⌘ K' : 'Ctrl K';
        this.caixa.appendChild(dica);

        this.painel = document.createElement('div');
        this.painel.id = 'luft-busca-lista';
        this.painel.className = 'luft-busca-painel';
        this.painel.setAttribute('role', 'listbox');
        this.painel.hidden = true;
        this.caixa.appendChild(this.painel);

        this.entrada.addEventListener('input', () => this._aoDigitar());
        this.entrada.addEventListener('focus', () => this._abrir());
        this.entrada.addEventListener('keydown', (e) => this._aoTeclar(e));
        document.addEventListener('keydown', (e) => this._atalhoGlobal(e));
        document.addEventListener('mousedown', (e) => {
            if (!this.caixa.contains(e.target)) this._fechar();
        });
    },

    // --- Menu lateral -------------------------------------------------------------------

    _normalizar(texto) {
        return String(texto || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
    },

    _indexarMenu() {
        const vistos = new Set();
        const lista = [];
        document.querySelectorAll('#luft-sidebar a.luft-nav-link[href]').forEach((a) => {
            const href = a.getAttribute('href') || '';
            if (!href || href === '#' || href.startsWith('javascript:')) return;
            const titulo = (a.querySelector('.luft-nav-text') || a).textContent.trim();
            if (!titulo) return;
            const grupo = a.closest('.luft-nav-wrapper');
            const rotuloGrupo = grupo ? (grupo.querySelector(':scope > .luft-nav-link .luft-nav-text') || {}).textContent : '';
            const chave = href + '|' + titulo;
            if (vistos.has(chave)) return;
            vistos.add(chave);
            const icone = a.querySelector('i');
            lista.push({
                titulo,
                subtitulo: (rotuloGrupo || '').trim() || null,
                url: href,
                icone: icone ? icone.className : 'ph-bold ph-arrow-right',
                alvo: this._normalizar(titulo + ' ' + (rotuloGrupo || '')),
                inicio: this._normalizar(titulo),
            });
        });
        return lista;
    },

    _filtrarMenu(termo) {
        const partes = this._normalizar(termo).split(/\s+/).filter(Boolean);
        if (!partes.length) return this.indice.slice(0, 8);
        return this.indice
            .filter((i) => partes.every((p) => i.alvo.includes(p)))
            .map((i) => ({ i, nota: (i.inicio.startsWith(partes[0]) ? 0 : i.inicio.includes(' ' + partes[0]) ? 1 : 2) }))
            .sort((a, b) => a.nota - b.nota)
            .slice(0, 6)
            .map((x) => x.i);
    },

    // --- Eventos --------------------------------------------------------------------------

    _atalhoGlobal(e) {
        const alvo = e.target;
        const digitando = alvo && (alvo.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(alvo.tagName));
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
            e.preventDefault();
            this.entrada.focus();
            this.entrada.select();
        } else if (e.key === '/' && !digitando && !e.ctrlKey && !e.metaKey && !e.altKey) {
            e.preventDefault();
            this.entrada.focus();
        }
    },

    _aoTeclar(e) {
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
            e.preventDefault();
            if (this.painel.hidden) this._abrir();
            if (!this.itens.length) return;
            const passo = e.key === 'ArrowDown' ? 1 : -1;
            this._ativar((this.ativo + passo + this.itens.length) % this.itens.length);
        } else if (e.key === 'Enter') {
            const item = this.itens[this.ativo >= 0 ? this.ativo : 0];
            if (item) {
                e.preventDefault();
                this._ir(item);
            }
        } else if (e.key === 'Escape') {
            this._fechar();
            this.entrada.blur();
        }
    },

    _aoDigitar() {
        const termo = this.entrada.value.trim();
        clearTimeout(this._tempo);
        this.remotos = [];
        this.carregando = false;
        if (this._abortar) this._abortar.abort();
        this._abrir();
        if (this.urlRemota && termo.length >= this.MINIMO_REMOTO) {
            this.carregando = true;
            this._desenhar();
            this._tempo = setTimeout(() => this._buscarRemoto(termo), this.ATRASO_MS);
        }
    },

    async _buscarRemoto(termo) {
        const numero = ++this.contador;
        this._abortar = new AbortController();
        try {
            const resposta = await fetch(`${this.urlRemota}?q=${encodeURIComponent(termo)}`, {
                credentials: 'same-origin',
                headers: { Accept: 'application/json' },
                signal: this._abortar.signal,
                __luftDesabilitarMensagens: true,
                __luftDesabilitarLatencia: true,
            });
            if (!resposta.ok) throw new Error('HTTP ' + resposta.status);
            const dados = await resposta.json();
            if (numero !== this.contador) return;
            this.remotos = Array.isArray(dados.grupos) ? dados.grupos : [];
        } catch (erro) {
            if (erro && erro.name === 'AbortError') return;
            this.remotos = [];
        }
        if (numero === this.contador) {
            this.carregando = false;
            this._desenhar();
        }
    },

    // --- Painel -----------------------------------------------------------------------------

    _abrir() {
        this.painel.hidden = false;
        this.entrada.setAttribute('aria-expanded', 'true');
        this._desenhar();
    },

    _fechar() {
        this.painel.hidden = true;
        this.entrada.setAttribute('aria-expanded', 'false');
    },

    _destacar(texto, termo) {
        const frag = document.createDocumentFragment();
        const partes = this._normalizar(termo).split(/\s+/).filter((p) => p.length > 0);
        const normal = this._normalizar(texto);
        let pos = -1;
        let tam = 0;
        for (const p of partes) {
            const i = normal.indexOf(p);
            if (i >= 0 && (pos < 0 || i < pos)) { pos = i; tam = p.length; }
        }
        if (pos < 0 || normal.length !== texto.length) {
            frag.appendChild(document.createTextNode(texto));
            return frag;
        }
        frag.appendChild(document.createTextNode(texto.slice(0, pos)));
        const marca = document.createElement('mark');
        marca.textContent = texto.slice(pos, pos + tam);
        frag.appendChild(marca);
        frag.appendChild(document.createTextNode(texto.slice(pos + tam)));
        return frag;
    },

    _desenhar() {
        const termo = this.entrada.value.trim();
        const grupos = [];
        const menu = this._filtrarMenu(termo);
        if (menu.length) grupos.push({ titulo: termo ? 'Navegação' : 'Ir para', itens: menu });
        // O que ja apareceu em "Navegacao" (mesmo destino) nao se repete nos grupos do servidor.
        const jaMostrados = new Set(menu.map((i) => i.url));
        this.remotos.forEach((g) => {
            const itens = g.itens.filter((i) => !jaMostrados.has(i.url)).map((i) => ({ ...i }));
            if (itens.length) grupos.push({ titulo: g.titulo, itens });
        });

        this.painel.replaceChildren();
        this.itens = [];
        grupos.forEach((grupo) => {
            const cabecalho = document.createElement('div');
            cabecalho.className = 'luft-busca-grupo';
            cabecalho.textContent = grupo.titulo;
            this.painel.appendChild(cabecalho);
            grupo.itens.forEach((item) => this.painel.appendChild(this._linha(item, termo)));
        });

        if (this.carregando) {
            const estado = document.createElement('div');
            estado.className = 'luft-busca-status';
            estado.textContent = 'Buscando…';
            this.painel.appendChild(estado);
        } else if (!this.itens.length) {
            const vazio = document.createElement('div');
            vazio.className = 'luft-busca-vazio';
            vazio.textContent = termo ? `Nada encontrado para “${termo}”.` : 'Digite para buscar.';
            this.painel.appendChild(vazio);
        }
        const rodape = document.createElement('div');
        rodape.className = 'luft-busca-rodape';
        rodape.textContent = '↑↓ navegar · Enter abrir · Esc fechar';
        this.painel.appendChild(rodape);
        this._ativar(this.itens.length ? 0 : -1);
    },

    _linha(item, termo) {
        const linha = document.createElement('a');
        linha.className = 'luft-busca-item';
        linha.href = item.url;
        linha.setAttribute('role', 'option');
        linha.id = 'luft-busca-item-' + this.itens.length;
        const icone = document.createElement('i');
        icone.className = item.icone || 'ph-bold ph-arrow-right';
        const texto = document.createElement('span');
        texto.className = 'luft-busca-texto';
        const titulo = document.createElement('span');
        titulo.className = 'luft-busca-titulo';
        titulo.appendChild(this._destacar(item.titulo, termo));
        texto.appendChild(titulo);
        if (item.subtitulo) {
            const sub = document.createElement('span');
            sub.className = 'luft-busca-sub';
            sub.textContent = item.subtitulo;
            texto.appendChild(sub);
        }
        linha.append(icone, texto);
        const indice = this.itens.length;
        linha.addEventListener('mousemove', () => this._ativar(indice));
        linha.addEventListener('click', (e) => {
            // clique normal navega pelo href; Ctrl/Cmd/botao do meio abrem em nova aba sem interferir
            if (e.ctrlKey || e.metaKey || e.shiftKey || e.button === 1) return;
            this._fechar();
        });
        this.itens.push(item);
        item.elemento = linha;
        return linha;
    },

    _ativar(indice) {
        this.ativo = indice;
        this.itens.forEach((item, i) => item.elemento.setAttribute('aria-selected', String(i === indice)));
        const atual = this.itens[indice];
        if (atual) {
            this.entrada.setAttribute('aria-activedescendant', atual.elemento.id);
            atual.elemento.scrollIntoView({ block: 'nearest' });
        } else {
            this.entrada.removeAttribute('aria-activedescendant');
        }
    },

    _ir(item) {
        this._fechar();
        window.location.assign(item.url);
    },
};

document.addEventListener('DOMContentLoaded', () => LuftBusca.iniciar());
