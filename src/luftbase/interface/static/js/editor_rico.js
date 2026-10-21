/**
 * Editor de texto rico (estilo e-mail) dos comunicados e notas de atualização.
 *
 * Gera HTML. O servidor é quem manda: ele sanitiza de novo ao salvar e ao exibir, então nada daqui
 * é confiável por si só. A limpeza feita no navegador (`limparHtml`) só evita que o editor se encha
 * de lixo quando alguém cola de um e-mail ou do Word.
 */
class LuftEditorRico {
    static TAMANHOS = [['Pequeno', '12px'], ['Normal', '15px'], ['Médio', '20px'], ['Grande', '28px'], ['Enorme', '40px']];
    static ESTILOS = [['Parágrafo', 'P'], ['Título', 'H2'], ['Subtítulo', 'H3'], ['Seção', 'H4']];
    static DESTAQUES = [['info', 'Informação'], ['sucesso', 'Sucesso'], ['alerta', 'Alerta'], ['perigo', 'Perigo']];
    static MAX_IMAGEM = 5 * 1024 * 1024;
    static LARGURA_MAX = 1600;

    static _TAGS = new Set(['P', 'DIV', 'SPAN', 'BR', 'HR', 'H2', 'H3', 'H4', 'STRONG', 'EM', 'U', 'S', 'SUB', 'SUP', 'UL', 'OL', 'LI',
        'BLOCKQUOTE', 'A', 'IMG', 'CODE', 'PRE', 'TABLE', 'THEAD', 'TBODY', 'TR', 'TH', 'TD']);
    static _EQUIV = { B: 'STRONG', I: 'EM', STRIKE: 'S', DEL: 'S', H1: 'H2', H5: 'H4', H6: 'H4' };
    static _DESCARTAR = new Set(['SCRIPT', 'STYLE', 'IFRAME', 'OBJECT', 'EMBED', 'TEMPLATE', 'NOSCRIPT', 'SVG', 'MATH', 'HEAD', 'TITLE', 'META', 'LINK']);

    /**
     * @param {HTMLElement} raiz  contêiner vazio onde o editor é montado
     * @param {{urlImagens: string, csrf: () => string, aoMudar?: () => void, aviso?: (t: string, m: string, tipo: string) => void}} opcoes
     */
    constructor(raiz, opcoes) {
        this.raiz = raiz;
        this.opcoes = opcoes;
        this._selecao = null;
        this._imagem = null;
        this._pendentes = 0;
        this._montar();
    }

    // ------------------------------------------------------------------ montagem
    _montar() {
        this.raiz.classList.add('pub-ed');
        this.raiz.innerHTML = '';
        this.barra = this._el('div', 'pub-ed-barra');
        this.barra.setAttribute('role', 'toolbar');
        this.barra.setAttribute('aria-label', 'Formatação do texto');
        this.contexto = this._el('div', 'pub-ed-contexto');
        this.contexto.hidden = true;
        this.area = this._el('div', 'pub-ed-area pub-corpo');
        this.area.contentEditable = 'true';
        this.area.setAttribute('role', 'textbox');
        this.area.setAttribute('aria-multiline', 'true');
        this.area.setAttribute('aria-label', 'Mensagem');
        this.area.dataset.vazio = 'Escreva a mensagem aqui. Use a barra acima para dar forma ao texto, inserir imagens, listas e destaques.';
        this.rodape = this._el('div', 'pub-ed-rodape');
        this.contador = this._el('span', 'pub-ed-contador');
        this.estado = this._el('span', 'pub-ed-estado');
        this.rodape.append(this.contador, this.estado);
        this.arquivo = this._el('input');
        this.arquivo.type = 'file';
        this.arquivo.accept = 'image/png,image/jpeg,image/gif,image/webp';
        this.arquivo.multiple = true;
        this.arquivo.hidden = true;
        this.arquivo.addEventListener('change', () => {
            Array.from(this.arquivo.files || []).forEach(f => this.enviarImagem(f));
            this.arquivo.value = '';
        });
        this.raiz.append(this.barra, this.contexto, this.area, this.rodape, this.arquivo);
        this._montarBarra();
        this._ligarEventos();
        this._atualizarRodape();
    }

    _el(tag, classe = '') {
        const no = document.createElement(tag);
        if (classe) no.className = classe;
        return no;
    }

    _grupo() {
        const g = this._el('div', 'pub-ed-grupo');
        this.barra.appendChild(g);
        return g;
    }

    _botao(grupo, icone, titulo, acao, extra = '') {
        const b = this._el('button', `pub-ed-btn ${extra}`.trim());
        b.type = 'button';
        b.title = titulo;
        b.setAttribute('aria-label', titulo);
        b.innerHTML = `<i class="ph-bold ph-${icone}"></i>`;
        // mousedown não pode tirar o foco do texto, senão a seleção se perde.
        b.addEventListener('mousedown', e => e.preventDefault());
        b.addEventListener('click', () => acao(b));
        grupo.appendChild(b);
        return b;
    }

    _selecionar(grupo, titulo, opcoes, aoEscolher, largura = '') {
        const s = this._el('select', 'pub-ed-select');
        s.title = titulo;
        s.setAttribute('aria-label', titulo);
        if (largura) s.style.width = largura;
        const base = this._el('option');
        base.value = '';
        base.textContent = titulo;
        base.disabled = true;
        base.selected = true;
        s.appendChild(base);
        opcoes.forEach(([rotulo, valor]) => {
            const o = this._el('option');
            o.value = valor;
            o.textContent = rotulo;
            s.appendChild(o);
        });
        s.addEventListener('change', () => {
            if (s.value) aoEscolher(s.value);
            s.selectedIndex = 0;
        });
        grupo.appendChild(s);
        return s;
    }

    _cor(grupo, icone, titulo, comando, padrao) {
        const rotulo = this._el('label', 'pub-ed-btn pub-ed-cor');
        rotulo.title = titulo;
        rotulo.innerHTML = `<i class="ph-bold ph-${icone}"></i>`;
        const entrada = this._el('input');
        entrada.type = 'color';
        entrada.value = padrao;
        entrada.setAttribute('aria-label', titulo);
        entrada.addEventListener('input', () => this.comando(comando, entrada.value));
        rotulo.appendChild(entrada);
        grupo.appendChild(rotulo);
    }

    _montarBarra() {
        let g = this._grupo();
        this._botao(g, 'arrow-counter-clockwise', 'Desfazer (Ctrl+Z)', () => this.comando('undo'));
        this._botao(g, 'arrow-clockwise', 'Refazer (Ctrl+Y)', () => this.comando('redo'));

        g = this._grupo();
        this._selecionar(g, 'Estilo', LuftEditorRico.ESTILOS, v => this.comando('formatBlock', v), '104px');
        this._selecionar(g, 'Tamanho', LuftEditorRico.TAMANHOS.map(([r, v]) => [r, v]), v => this.tamanho(v), '92px');

        g = this._grupo();
        this._botao(g, 'text-b', 'Negrito (Ctrl+B)', () => this.comando('bold'));
        this._botao(g, 'text-italic', 'Itálico (Ctrl+I)', () => this.comando('italic'));
        this._botao(g, 'text-underline', 'Sublinhado (Ctrl+U)', () => this.comando('underline'));
        this._botao(g, 'text-strikethrough', 'Tachado', () => this.comando('strikeThrough'));
        this._cor(g, 'text-aa', 'Cor do texto', 'foreColor', '#1d4ed8');
        this._cor(g, 'highlighter', 'Cor de destaque (marca-texto)', 'hiliteColor', '#fde68a');

        g = this._grupo();
        this._botao(g, 'text-align-left', 'Alinhar à esquerda', () => this.comando('justifyLeft'));
        this._botao(g, 'text-align-center', 'Centralizar', () => this.comando('justifyCenter'));
        this._botao(g, 'text-align-right', 'Alinhar à direita', () => this.comando('justifyRight'));
        this._botao(g, 'text-align-justify', 'Justificar', () => this.comando('justifyFull'));

        g = this._grupo();
        this._botao(g, 'list-bullets', 'Lista com marcadores', () => this.comando('insertUnorderedList'));
        this._botao(g, 'list-numbers', 'Lista numerada', () => this.comando('insertOrderedList'));
        this._botao(g, 'quotes', 'Citação', () => this.comando('formatBlock', 'BLOCKQUOTE'));
        this._botao(g, 'minus', 'Linha divisória', () => this.comando('insertHorizontalRule'));

        g = this._grupo();
        this._selecionar(g, 'Destaque', LuftEditorRico.DESTAQUES.map(([v, r]) => [r, v]), v => this.destaque(v), '98px');
        this._botao(g, 'link', 'Inserir link (Ctrl+K)', () => this.abrirLink());
        this._botao(g, 'image', 'Inserir imagem (ou cole / arraste)', () => this.arquivo.click(), 'pub-ed-btn-destaque');
        this._botao(g, 'table', 'Inserir tabela', () => this.inserirTabela());
        this._botao(g, 'eraser', 'Limpar formatação', () => this.limparFormatacao());
    }

    _ligarEventos() {
        const guardar = () => this._guardarSelecao();
        ['keyup', 'mouseup', 'focus', 'blur'].forEach(ev => this.area.addEventListener(ev, guardar));
        this.area.addEventListener('input', () => this._alterou());
        this.area.addEventListener('click', e => this._aoClicar(e));
        this.area.addEventListener('keyup', () => this._atualizarContexto());
        this.area.addEventListener('keydown', e => {
            if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
                e.preventDefault();
                this.abrirLink();
            }
            if (e.key === 'Tab' && this._noItemDeLista()) {
                e.preventDefault();
                this.comando(e.shiftKey ? 'outdent' : 'indent');
            }
        });
        this.area.addEventListener('paste', e => this._aoColar(e));
        this.area.addEventListener('dragover', e => {
            if (e.dataTransfer?.types?.includes('Files')) e.preventDefault();
        });
        this.area.addEventListener('drop', e => {
            const arquivos = Array.from(e.dataTransfer?.files || []).filter(f => f.type.startsWith('image/'));
            if (!arquivos.length) return;
            e.preventDefault();
            this._posicionarNoPonto(e.clientX, e.clientY);
            arquivos.forEach(f => this.enviarImagem(f));
        });
    }

    // ------------------------------------------------------------------ seleção
    _guardarSelecao() {
        const sel = window.getSelection();
        if (sel && sel.rangeCount && this.area.contains(sel.anchorNode)) {
            this._selecao = sel.getRangeAt(0).cloneRange();
        }
    }

    _restaurarSelecao() {
        this.area.focus({ preventScroll: true });
        if (!this._selecao) return;
        const sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(this._selecao);
    }

    _posicionarNoPonto(x, y) {
        let range = null;
        if (document.caretRangeFromPoint) range = document.caretRangeFromPoint(x, y);
        else if (document.caretPositionFromPoint) {
            const p = document.caretPositionFromPoint(x, y);
            if (p) { range = document.createRange(); range.setStart(p.offsetNode, p.offset); }
        }
        if (range && this.area.contains(range.startContainer)) {
            this._selecao = range;
            this._restaurarSelecao();
        }
    }

    _noItemDeLista() {
        const sel = window.getSelection();
        const no = sel?.anchorNode;
        return Boolean(no && this.area.contains(no) && (no.nodeType === 1 ? no : no.parentElement)?.closest('li'));
    }

    // ------------------------------------------------------------------ comandos
    comando(nome, valor = null) {
        this._restaurarSelecao();
        document.execCommand('styleWithCSS', false, true);
        document.execCommand(nome, false, valor);
        this._guardarSelecao();
        this._alterou();
    }

    tamanho(px) {
        this._restaurarSelecao();
        // `fontSize` só aceita 1..7; o 7 vira <font size=7> e é trocado por um span com o tamanho em px.
        document.execCommand('styleWithCSS', false, false);
        document.execCommand('fontSize', false, '7');
        document.execCommand('styleWithCSS', false, true);
        this.area.querySelectorAll('font[size="7"]').forEach(f => {
            const span = document.createElement('span');
            span.style.fontSize = px;
            span.append(...Array.from(f.childNodes));
            span.querySelectorAll('span').forEach(interno => { interno.style.removeProperty('font-size'); });
            f.replaceWith(span);
        });
        this._guardarSelecao();
        this._alterou();
    }

    destaque(tipo) {
        this._restaurarSelecao();
        const sel = window.getSelection();
        const no = sel?.anchorNode;
        const atual = (no?.nodeType === 1 ? no : no?.parentElement)?.closest('.pub-callout');
        if (atual && this.area.contains(atual)) {
            atual.className = `pub-callout pub-${tipo}`;
        } else {
            let corpo = '<p>Escreva o destaque aqui</p>';
            if (sel && sel.rangeCount && !sel.isCollapsed) {
                const caixa = document.createElement('div');
                caixa.appendChild(sel.getRangeAt(0).cloneContents());
                if (caixa.textContent.trim()) corpo = caixa.innerHTML;
            }
            document.execCommand('insertHTML', false, `<div class="pub-callout pub-${tipo}">${corpo}</div><p><br></p>`);
        }
        this._guardarSelecao();
        this._alterou();
    }

    limparFormatacao() {
        this._restaurarSelecao();
        document.execCommand('removeFormat');
        document.execCommand('unlink');
        document.execCommand('formatBlock', false, 'P');
        this._guardarSelecao();
        this._alterou();
    }

    inserirTabela() {
        const celulas = n => Array.from({ length: n }, () => '<td><br></td>').join('');
        const cab = Array.from({ length: 3 }, (_, i) => `<th>Coluna ${i + 1}</th>`).join('');
        const html = `<table style="width: 100%"><tbody><tr>${cab}</tr><tr>${celulas(3)}</tr><tr>${celulas(3)}</tr></tbody></table><p><br></p>`;
        this._restaurarSelecao();
        document.execCommand('insertHTML', false, html);
        this._guardarSelecao();
        this._alterou();
    }

    // ------------------------------------------------------------------ link
    abrirLink() {
        this._guardarSelecao();
        const sel = window.getSelection();
        const ancora = (sel?.anchorNode?.nodeType === 1 ? sel.anchorNode : sel?.anchorNode?.parentElement)?.closest('a');
        this._contexto('link', ancora ? ancora.getAttribute('href') : '');
    }

    _aplicarLink(url) {
        let destino = (url || '').trim();
        if (!destino) return;
        if (!/^(https?:\/\/|mailto:)/i.test(destino)) destino = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(destino) ? `mailto:${destino}` : `https://${destino}`;
        this._restaurarSelecao();
        const sel = window.getSelection();
        if (sel && sel.isCollapsed) {
            document.execCommand('insertHTML', false, `<a href="${destino.replace(/"/g, '&quot;')}">${destino.replace(/</g, '&lt;')}</a>`);
        } else {
            document.execCommand('createLink', false, destino);
        }
        this._ocultarContexto();
        this._alterou();
    }

    // ------------------------------------------------------------------ painel contextual (link, imagem, tabela)
    _contexto(modo, valor = '') {
        this.contexto.innerHTML = '';
        this.contexto.hidden = false;
        this.contexto.dataset.modo = modo;
        const botao = (texto, icone, acao, classe = 'pub-ed-ctx-btn') => {
            const b = this._el('button', classe);
            b.type = 'button';
            b.innerHTML = `<i class="ph-bold ph-${icone}"></i> ${texto}`;
            b.addEventListener('mousedown', e => e.preventDefault());
            b.addEventListener('click', acao);
            this.contexto.appendChild(b);
            return b;
        };
        const rotulo = texto => {
            const s = this._el('span', 'pub-ed-ctx-rotulo');
            s.textContent = texto;
            this.contexto.appendChild(s);
        };
        if (modo === 'link') {
            rotulo('Link');
            const entrada = this._el('input', 'pub-ed-ctx-input');
            entrada.type = 'text';
            entrada.placeholder = 'https://…';
            entrada.value = valor;
            entrada.addEventListener('keydown', e => {
                if (e.key === 'Enter') { e.preventDefault(); this._aplicarLink(entrada.value); }
                if (e.key === 'Escape') this._ocultarContexto();
            });
            this.contexto.appendChild(entrada);
            botao('Aplicar', 'check', () => this._aplicarLink(entrada.value));
            botao('Remover link', 'link-break', () => { this.comando('unlink'); this._ocultarContexto(); });
            botao('Fechar', 'x', () => this._ocultarContexto());
            entrada.focus();
        } else if (modo === 'imagem') {
            rotulo('Imagem');
            [['25%', 25], ['50%', 50], ['75%', 75], ['100%', 100]].forEach(([t, n]) => botao(t, 'arrows-out-line-horizontal', () => this._larguraImagem(n)));
            const alt = this._el('input', 'pub-ed-ctx-input');
            alt.type = 'text';
            alt.placeholder = 'Descrição da imagem (acessibilidade)';
            alt.value = this._imagem?.getAttribute('alt') || '';
            alt.addEventListener('input', () => { this._imagem?.setAttribute('alt', alt.value); this._alterou(); });
            this.contexto.appendChild(alt);
            botao('Remover', 'trash', () => { this._imagem?.remove(); this._desmarcarImagem(); this._ocultarContexto(); this._alterou(); }, 'pub-ed-ctx-btn perigo');
        } else if (modo === 'tabela') {
            rotulo('Tabela');
            botao('Linha', 'rows', () => this._tabela('+linha'));
            botao('Coluna', 'columns', () => this._tabela('+coluna'));
            botao('Linha', 'minus-circle', () => this._tabela('-linha'), 'pub-ed-ctx-btn perigo');
            botao('Coluna', 'minus-circle', () => this._tabela('-coluna'), 'pub-ed-ctx-btn perigo');
            botao('Excluir tabela', 'trash', () => this._tabela('excluir'), 'pub-ed-ctx-btn perigo');
        }
    }

    _ocultarContexto() {
        this.contexto.hidden = true;
        this.contexto.innerHTML = '';
        delete this.contexto.dataset.modo;
    }

    _atualizarContexto() {
        if (this.contexto.dataset.modo === 'link' || this._imagem) return;
        const sel = window.getSelection();
        const no = sel?.anchorNode;
        const el = no?.nodeType === 1 ? no : no?.parentElement;
        if (el && this.area.contains(el) && el.closest('td,th')) {
            if (this.contexto.dataset.modo !== 'tabela') this._contexto('tabela');
        } else if (this.contexto.dataset.modo === 'tabela') {
            this._ocultarContexto();
        }
    }

    _tabela(acao) {
        const sel = window.getSelection();
        const no = this._selecao?.startContainer || sel?.anchorNode;
        const celula = (no?.nodeType === 1 ? no : no?.parentElement)?.closest('td,th');
        const tabela = celula?.closest('table');
        if (!celula || !tabela) return;
        const linha = celula.parentElement;
        const indice = Array.from(linha.children).indexOf(celula);
        if (acao === 'excluir') { tabela.remove(); this._ocultarContexto(); }
        else if (acao === '+linha') {
            const nova = linha.cloneNode(true);
            nova.querySelectorAll('th,td').forEach(c => { const td = document.createElement('td'); td.innerHTML = '<br>'; c.replaceWith(td); });
            linha.after(nova);
        } else if (acao === '-linha') {
            if (tabela.rows.length > 1) linha.remove();
        } else if (acao === '+coluna') {
            Array.from(tabela.rows).forEach(r => {
                const ref = r.children[indice];
                const nova = document.createElement(ref?.tagName === 'TH' ? 'th' : 'td');
                nova.innerHTML = nova.tagName === 'TH' ? 'Coluna' : '<br>';
                ref ? ref.after(nova) : r.appendChild(nova);
            });
        } else if (acao === '-coluna') {
            if (linha.children.length > 1) Array.from(tabela.rows).forEach(r => r.children[indice]?.remove());
        }
        this._alterou();
    }

    // ------------------------------------------------------------------ imagens
    _aoClicar(e) {
        const alvo = e.target;
        if (alvo && alvo.tagName === 'IMG') {
            this._desmarcarImagem();
            this._imagem = alvo;
            alvo.classList.add('pub-sel');
            this._contexto('imagem');
        } else {
            this._desmarcarImagem();
            this._atualizarContexto();
            if (this.contexto.dataset.modo === 'imagem') this._ocultarContexto();
        }
    }

    _desmarcarImagem() {
        this.area.querySelectorAll('img.pub-sel').forEach(i => i.classList.remove('pub-sel'));
        this._imagem = null;
    }

    _larguraImagem(percentual) {
        if (!this._imagem) return;
        this._imagem.style.width = `${percentual}%`;
        this._alterou();
    }

    async _reduzir(arquivo) {
        if (!['image/png', 'image/jpeg', 'image/webp'].includes(arquivo.type)) return arquivo;
        try {
            const bitmap = await createImageBitmap(arquivo);
            if (bitmap.width <= LuftEditorRico.LARGURA_MAX) { bitmap.close?.(); return arquivo; }
            const escala = LuftEditorRico.LARGURA_MAX / bitmap.width;
            const tela = document.createElement('canvas');
            tela.width = LuftEditorRico.LARGURA_MAX;
            tela.height = Math.round(bitmap.height * escala);
            tela.getContext('2d').drawImage(bitmap, 0, 0, tela.width, tela.height);
            bitmap.close?.();
            const blob = await new Promise(ok => tela.toBlob(ok, arquivo.type, 0.9));
            return blob ? new File([blob], arquivo.name, { type: arquivo.type }) : arquivo;
        } catch (_erro) {
            return arquivo;
        }
    }

    async enviarImagem(arquivo) {
        if (!arquivo || !arquivo.type.startsWith('image/')) return;
        this._pendentes += 1;
        this._mostrarEstado(`Enviando ${arquivo.name || 'imagem'}…`);
        try {
            const pronto = await this._reduzir(arquivo);
            if (pronto.size > LuftEditorRico.MAX_IMAGEM) throw new Error('A imagem pode ter no máximo 5 MB.');
            const corpo = new FormData();
            corpo.append('arquivo', pronto, pronto.name || 'imagem');
            const resposta = await fetch(this.opcoes.urlImagens, {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest', 'X-CSRF-Token': this.opcoes.csrf() },
                body: corpo,
            });
            let dados = {};
            try { dados = await resposta.json(); } catch (_e) { /* não JSON */ }
            if (!resposta.ok || dados.status === 'error') throw new Error(dados.mensagem || `Não foi possível enviar a imagem (HTTP ${resposta.status}).`);
            const url = dados.dados.url;
            const alt = (arquivo.name || '').replace(/\.[^.]+$/, '').replace(/"/g, '');
            this._restaurarSelecao();
            document.execCommand('insertHTML', false, `<img src="${url}" alt="${alt}"><p><br></p>`);
            this._guardarSelecao();
            this._alterou();
        } catch (erro) {
            this.opcoes.aviso?.('Imagem não enviada', erro.message, 'error');
        } finally {
            this._pendentes -= 1;
            this._mostrarEstado(this._pendentes ? 'Enviando imagem…' : '');
        }
    }

    // ------------------------------------------------------------------ colar
    _aoColar(e) {
        const dados = e.clipboardData;
        if (!dados) return;
        const imagens = Array.from(dados.files || []).filter(f => f.type.startsWith('image/'));
        if (imagens.length) {
            e.preventDefault();
            imagens.forEach(f => this.enviarImagem(f));
            return;
        }
        const html = dados.getData('text/html');
        e.preventDefault();
        if (html) document.execCommand('insertHTML', false, this.limparHtml(html));
        else document.execCommand('insertText', false, dados.getData('text/plain'));
        this._alterou();
    }

    /** Mantém só o que o editor sabe representar (espelha, de forma enxuta, a lista do servidor). */
    limparHtml(html) {
        const doc = new DOMParser().parseFromString(html, 'text/html');
        const permitido = /^(color|background-color|font-size|text-align|font-weight|font-style|text-decoration)$/;
        const visitar = no => {
            Array.from(no.childNodes).forEach(filho => {
                if (filho.nodeType === 8) { filho.remove(); return; }
                if (filho.nodeType !== 1) return;
                const tag = filho.tagName;
                if (LuftEditorRico._DESCARTAR.has(tag)) { filho.remove(); return; }
                visitar(filho);
                const destino = LuftEditorRico._EQUIV[tag] || tag;
                if (!LuftEditorRico._TAGS.has(destino)) { filho.replaceWith(...Array.from(filho.childNodes)); return; }
                const novo = destino === tag ? filho : document.createElement(destino.toLowerCase());
                if (novo !== filho) { novo.append(...Array.from(filho.childNodes)); filho.replaceWith(novo); }
                const estilo = (filho.getAttribute('style') || '').split(';').map(t => t.split(':')).filter(p => p.length === 2 && permitido.test(p[0].trim().toLowerCase())).map(p => `${p[0].trim()}: ${p[1].trim()}`).join('; ');
                const href = filho.getAttribute('href');
                const src = filho.getAttribute('src');
                const alt = filho.getAttribute('alt');
                Array.from(novo.attributes).forEach(a => novo.removeAttribute(a.name));
                if (estilo) novo.setAttribute('style', estilo);
                if (destino === 'A' && /^(https?:|mailto:)/i.test(href || '')) novo.setAttribute('href', href);
                if (destino === 'IMG') {
                    if (/^https:/i.test(src || '')) { novo.setAttribute('src', src); if (alt) novo.setAttribute('alt', alt); } else novo.remove();
                }
            });
        };
        visitar(doc.body);
        return doc.body.innerHTML;
    }

    // ------------------------------------------------------------------ estado e saída
    _alterou() {
        this._atualizarRodape();
        this.opcoes.aoMudar?.();
    }

    _mostrarEstado(texto) {
        this.estado.textContent = texto;
    }

    _atualizarRodape() {
        const texto = this._texto();
        const palavras = texto ? texto.split(/\s+/).length : 0;
        const imagens = this.area.querySelectorAll('img').length;
        this.contador.textContent = `${palavras} palavra${palavras === 1 ? '' : 's'}${imagens ? ` · ${imagens} imagem${imagens === 1 ? '' : 'ns'}` : ''}`;
        this.area.classList.toggle('pub-ed-vazio', !texto && !imagens);
    }

    /** `innerText` ignora o que esta com visibility:hidden (modal fechado); nesse caso vale o textContent. */
    _texto() {
        return (this.area.innerText || this.area.textContent || '').trim();
    }

    vazio() {
        return !this._texto() && !this.area.querySelector('img');
    }

    html() {
        const copia = this.area.cloneNode(true);
        copia.querySelectorAll('.pub-sel').forEach(i => i.classList.remove('pub-sel'));
        copia.querySelectorAll('font').forEach(f => f.replaceWith(...Array.from(f.childNodes)));
        return copia.innerHTML.trim();
    }

    definirHtml(html) {
        this.area.innerHTML = html || '';
        this._selecao = null;
        this._desmarcarImagem();
        this._ocultarContexto();
        this._atualizarRodape();
    }

    focar() {
        this._atualizarRodape();
        this.area.focus();
    }

    ocupado() {
        return this._pendentes > 0;
    }
}

window.LuftEditorRico = LuftEditorRico;
