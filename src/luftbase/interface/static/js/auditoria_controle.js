/* Auditoria: controle de sessões (encerrar uma, desconectar uma pessoa, desconectar todos).
 *
 * Toda ação passa por uma janela de confirmação e responde com um aviso. O servidor valida permissão, CSRF
 * e escopo, e deixa o rastro na auditoria; aqui só pedimos e mostramos o resultado.
 */
(() => {
    'use strict';

    const raiz = document.getElementById('luftAuditoria');
    if (!raiz || window.luftControle) return;

    const $ = (id) => document.getElementById(id);
    const csrf = () => document.querySelector('meta[name="luft-csrf-token"]')?.getAttribute('content') || '';

    // ---- aviso (toast) -----------------------------------------------------------------------------
    let temporizadorAviso = null;
    function avisar(texto, tipo = 'ok') {
        const el = $('auditToast');
        if (!el) return;
        el.textContent = texto;
        el.className = `audit-toast ${tipo}`;
        el.hidden = false;
        clearTimeout(temporizadorAviso);
        temporizadorAviso = setTimeout(() => { el.hidden = true; }, 6000);
    }

    // ---- confirmação -------------------------------------------------------------------------------
    function confirmar({ titulo, texto, botao, perigo = true, digitar = null, opcao = null }) {
        const dialogo = $('auditConfirma');
        return new Promise((resolver) => {
            $('auditConfirmaTitulo').textContent = titulo;
            $('auditConfirmaTexto').textContent = texto;
            const campoLinha = $('auditConfirmaCampoLinha');
            const campo = $('auditConfirmaCampo');
            const ok = $('auditConfirmaOk');
            campoLinha.hidden = !digitar;
            $('auditConfirmaOpcaoLinha').hidden = !opcao;
            $('auditConfirmaOpcao').checked = false;
            if (opcao) $('auditConfirmaOpcaoTexto').textContent = opcao;
            campo.value = '';
            if (digitar) $('auditConfirmaDica').textContent = `Digite ${digitar} para confirmar.`;
            ok.textContent = botao;
            ok.classList.toggle('perigo', perigo);
            ok.disabled = !!digitar;

            const validar = () => { ok.disabled = !!digitar && campo.value.trim().toUpperCase() !== digitar; };
            const encerrar = (resultado) => {
                campo.removeEventListener('input', validar);
                ok.onclick = null;
                $('auditConfirmaCancelar').onclick = null;
                dialogo.removeEventListener('cancel', aoCancelar);
                dialogo.close();
                resolver(resultado);
            };
            const aoCancelar = (ev) => { ev.preventDefault(); encerrar(false); };
            campo.addEventListener('input', validar);
            ok.onclick = () => encerrar($('auditConfirmaOpcao').checked ? 'com-opcao' : true);
            $('auditConfirmaCancelar').onclick = () => encerrar(false);
            dialogo.addEventListener('cancel', aoCancelar);
            dialogo.showModal();
            (digitar ? campo : $('auditConfirmaCancelar')).focus();
        });
    }

    // ---- chamadas ---------------------------------------------------------------------------------
    async function enviar(url, corpo) {
        const resposta = await fetch(url, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json', Accept: 'application/json', 'X-CSRF-Token': csrf() },
            body: JSON.stringify(corpo),
        });
        const dados = await resposta.json().catch(() => ({}));
        if (!resposta.ok || dados.status === 'error') {
            throw new Error(dados.message || dados.mensagem || (resposta.status === 403 ? 'Você não tem permissão para esta ação.' : `Falha HTTP ${resposta.status}`));
        }
        return dados;
    }

    function depois(dados) {
        // Se a própria sessão caiu, recarregar leva à tela de entrada (em vez de deixar a tela “morta”).
        if (dados?.data?.propria) { setTimeout(() => window.location.reload(), 900); return; }
        window.luftAuditoriaVivo?.();
        window.luftAuditoriaAtualizar?.();
    }

    async function executar(url, corpo) {
        try {
            const dados = await enviar(url, corpo);
            avisar(dados.message || 'Pronto.', 'ok');
            depois(dados);
        } catch (erro) {
            avisar(erro.message, 'erro');
            depois(); // a lista pode estar velha (a sessão já terminou): atualiza para refletir a realidade
        }
    }

    async function encerrarSessao(ref, rotulo) {
        const sim = await confirmar({
            titulo: 'Encerrar esta sessão?',
            texto: `A sessão de ${rotulo} será encerrada na hora. A pessoa terá de entrar de novo, e as outras sessões dela continuam.`,
            botao: 'Encerrar sessão',
        });
        if (sim) await executar(raiz.dataset.revogarSessaoUrl, { ref });
    }

    async function desconectarPessoa(codigo, nome, proprio = false) {
        const sim = await confirmar(proprio ? {
            titulo: 'Encerrar as minhas outras sessões?',
            texto: 'As suas sessões em outros navegadores ou computadores serão encerradas. Esta, que você está usando, continua.',
            botao: 'Encerrar outras sessões',
        } : {
            titulo: `Desconectar ${nome}?`,
            texto: 'Todas as sessões desta pessoa serão encerradas agora, em qualquer navegador ou computador. Ela poderá entrar de novo normalmente.',
            botao: 'Desconectar',
        });
        if (sim) await executar(raiz.dataset.revogarPessoaUrl, { codigo_usuario: codigo });
    }

    async function desconectarTodos() {
        const sim = await confirmar({
            titulo: 'Desconectar todo mundo?',
            texto: 'Todas as sessões ativas serão encerradas. Por padrão a sua fica de fora. Todos terão de entrar de novo. Use em manutenção ou em caso de incidente.',
            botao: 'Desconectar todos',
            digitar: 'DESCONECTAR',
            opcao: 'Incluir a minha sessão (eu também serei desconectado)',
        });
        if (sim) await executar(raiz.dataset.revogarTodasUrl, { confirmacao: 'DESCONECTAR', incluir_propria: sim === 'com-opcao' });
    }

    window.luftControle = { encerrarSessao, desconectarPessoa, desconectarTodos, avisar };
})();
