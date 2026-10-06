"""Gera as imagens da nota de atualização "Nova base dos sistemas Luft" (PNG, via Chrome sem interface).

    python tools/gerar_imagens_changelog.py            # gera tudo
    python tools/gerar_imagens_changelog.py perfil-sessoes banner   # só algumas

As telas são maquetes com dados fictícios, desenhadas com a identidade visual do LuftBase; as demais
são ilustrações. Para trocar uma delas por um print real, basta salvar o arquivo com o mesmo nome em
`src/luftbase/interface/static/img/changelog/`.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SAIDA = RAIZ / "src" / "luftbase" / "interface" / "static" / "img" / "changelog"
LOGO = (RAIZ / "src" / "luftbase" / "interface" / "static" / "icons" / "luft-logo-150x150-Dark.png").as_uri()
CHROME = next(
    (
        c
        for c in (
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            "/usr/bin/google-chrome",
            "/usr/bin/chromium",
        )
        if Path(c).exists()
    ),
    None,
)

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
:root{--azul:#1d4ed8;--azul2:#2563eb;--ciano:#06b6d4;--tinta:#0f172a;--mudo:#64748b;--linha:#e2e8f0;
--fundo:#f1f5f9;--card:#fff;--verde:#059669;--ambar:#d97706;--verm:#dc2626;--roxo:#7c3aed}
body{font-family:'Segoe UI',system-ui,Arial,sans-serif;color:var(--tinta);background:var(--fundo);overflow:hidden}
i[class*=ph-]{line-height:1}
.arte{position:relative;overflow:hidden;color:#fff}
.g1{background:linear-gradient(135deg,#0b1b4d,#1d4ed8 58%,#06b6d4)}
.g2{background:linear-gradient(135deg,#312e81,#4f46e5 55%,#38bdf8)}
.g3{background:linear-gradient(135deg,#064e3b,#059669 55%,#22d3ee)}
.g4{background:linear-gradient(135deg,#581c87,#7c3aed 55%,#f472b6)}
.g5{background:linear-gradient(135deg,#7c2d12,#ea580c 55%,#facc15)}
.g6{background:linear-gradient(135deg,#0f172a,#1e293b 55%,#334155)}
.aneis:before,.aneis:after{content:"";position:absolute;border:2px solid rgba(255,255,255,.13);border-radius:50%}
.aneis:before{width:520px;height:520px;right:-120px;top:-210px}
.aneis:after{width:320px;height:320px;right:-20px;top:-110px}
.kicker{font-size:15px;letter-spacing:.28em;font-weight:700;text-transform:uppercase;opacity:.8}
h1{font-size:54px;line-height:1.08;font-weight:800;letter-spacing:-.02em}
h2{font-size:34px;font-weight:800;letter-spacing:-.01em}
.sub{font-size:20px;opacity:.88;line-height:1.4}
.vidro{background:rgba(255,255,255,.14);border:1px solid rgba(255,255,255,.32);border-radius:18px}
.card{background:var(--card);border:1px solid var(--linha);border-radius:14px;box-shadow:0 2px 10px rgba(15,23,42,.06)}
.chip{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:999px;font-size:12px;font-weight:700}
.c-verde{background:#d1fae5;color:#047857}.c-azul{background:#dbeafe;color:#1d4ed8}.c-amb{background:#fef3c7;color:#b45309}
.c-verm{background:#fee2e2;color:#b91c1c}.c-cinza{background:#e2e8f0;color:#475569}.c-roxo{background:#ede9fe;color:#6d28d9}
.btn{display:inline-flex;align-items:center;gap:7px;padding:8px 14px;border-radius:9px;font-size:13px;font-weight:700;border:1px solid var(--linha);background:#fff;color:var(--tinta)}
.btn.p{background:var(--azul2);border-color:var(--azul2);color:#fff}.btn.d{color:var(--verm);border-color:#fecaca}
.mono{font-family:Consolas,'Cascadia Mono',monospace}
.mudo{color:var(--mudo)}
.shell{display:flex;height:100%}
.side{width:230px;background:#fff;border-right:1px solid var(--linha);padding:16px 12px;display:flex;flex-direction:column;gap:3px;flex:0 0 auto}
.marca{display:flex;align-items:center;gap:10px;padding:2px 6px 14px;border-bottom:1px solid var(--linha);margin-bottom:10px}
.marca img{width:34px;height:34px}.marca b{font-size:14px}.marca small{display:block;font-size:10px;color:var(--azul2);font-weight:700;letter-spacing:.08em}
.nav{display:flex;align-items:center;gap:10px;padding:9px 10px;border-radius:9px;font-size:13px;font-weight:600;color:#334155}
.nav.on{background:#dbeafe;color:var(--azul)}.nav.sub{margin-left:18px;font-weight:500;font-size:12.5px}
.nav i{font-size:17px}
.usuario{margin-top:auto;display:flex;align-items:center;gap:10px;padding:10px;border:1px solid var(--linha);border-radius:12px}
.av{width:34px;height:34px;border-radius:50%;background:linear-gradient(135deg,#6366f1,#06b6d4);color:#fff;display:grid;place-items:center;font-weight:800;font-size:13px;flex:0 0 auto}
.main{flex:1;display:flex;flex-direction:column;min-width:0}
.topo{display:flex;align-items:center;gap:14px;padding:12px 24px;background:#fff;border-bottom:1px solid var(--linha);font-size:13px}
.crumb{display:flex;align-items:center;gap:8px;color:var(--mudo);font-weight:600}.crumb b{color:var(--tinta)}
.busca{margin-left:auto;display:flex;align-items:center;gap:8px;padding:8px 14px;border:1px solid var(--linha);border-radius:10px;background:var(--fundo);color:var(--mudo);width:260px}
.sino{position:relative;font-size:20px;color:#475569}.sino em{position:absolute;top:-6px;right:-8px;background:var(--verm);color:#fff;font-style:normal;font-size:10px;font-weight:800;border-radius:9px;padding:1px 5px}
.corpo{padding:22px 26px;flex:1;overflow:hidden}
.titulo{font-size:22px;font-weight:800;margin-bottom:4px}.lede{font-size:13px;color:var(--mudo);margin-bottom:16px}
.grid{display:grid;gap:14px}.g2c{grid-template-columns:1fr 1fr}.g3c{grid-template-columns:repeat(3,1fr)}.g4c{grid-template-columns:repeat(4,1fr)}
.p16{padding:16px}.p20{padding:20px}
.lin{display:flex;align-items:center;gap:12px}
.ic{width:42px;height:42px;border-radius:12px;display:grid;place-items:center;font-size:21px;flex:0 0 auto}
.ic.b{background:#dbeafe;color:var(--azul)}.ic.v{background:#d1fae5;color:#047857}.ic.a{background:#fef3c7;color:#b45309}.ic.r{background:#ede9fe;color:#6d28d9}.ic.m{background:#fee2e2;color:#b91c1c}
table{width:100%;border-collapse:collapse;font-size:13px}th{text-align:left;font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--mudo);padding:9px 12px;border-bottom:1px solid var(--linha);background:#f8fafc}
td{padding:11px 12px;border-bottom:1px solid #eef2f7}
.drawer{position:absolute;right:0;top:0;bottom:0;width:480px;background:#fff;box-shadow:-18px 0 50px rgba(15,23,42,.28);display:flex;flex-direction:column}
.veu{position:absolute;inset:0;background:rgba(15,23,42,.38)}
.dh{display:flex;align-items:center;gap:12px;padding:18px 22px;border-bottom:1px solid var(--linha)}
.dh h3{font-size:17px}.dh small{color:var(--mudo);font-size:12px}
.sess{display:flex;gap:12px;align-items:center;padding:12px 14px;border:1px solid var(--linha);border-radius:12px;background:#f8fafc}
.sess.on{background:#ecfdf5;border-color:#a7f3d0}.sess i.d{font-size:24px;color:var(--azul2)}
.sess b{font-size:13.5px}.sess small{display:block;font-size:11.5px;color:var(--mudo);margin-top:2px}
.tabs{display:flex;border-bottom:1px solid var(--linha);padding:0 14px}.tabs div{padding:12px 14px;font-size:12.5px;font-weight:700;color:var(--mudo)}.tabs .on{color:var(--azul);border-bottom:2px solid var(--azul2)}
.sw{width:38px;height:22px;border-radius:11px;background:#cbd5e1;position:relative;flex:0 0 auto}.sw:after{content:"";position:absolute;top:3px;left:3px;width:16px;height:16px;border-radius:50%;background:#fff}
.sw.on{background:var(--verde)}.sw.on:after{left:19px}
.passo{display:flex;align-items:center;gap:10px;font-size:13px;font-weight:700}
.passo i{width:28px;height:28px;border-radius:50%;display:grid;place-items:center;font-style:normal;font-size:13px;background:#e2e8f0;color:#475569}
.passo.on i{background:var(--azul2);color:#fff}.passo.ok i{background:var(--verde);color:#fff}
.barra{height:8px;border-radius:5px;background:#e2e8f0;overflow:hidden}.barra span{display:block;height:100%;background:linear-gradient(90deg,#2563eb,#06b6d4)}
.no{position:absolute;display:flex;flex-direction:column;align-items:center;gap:8px;text-align:center}
.no .bola{width:84px;height:84px;border-radius:24px;display:grid;place-items:center;font-size:40px;background:rgba(255,255,255,.16);border:1px solid rgba(255,255,255,.4)}
.no b{font-size:17px}.no small{font-size:12.5px;opacity:.85}
.fio{position:absolute;height:3px;background:linear-gradient(90deg,rgba(255,255,255,.1),rgba(255,255,255,.8),rgba(255,255,255,.1));border-radius:2px}
.col{display:flex;flex-direction:column;gap:12px}
.rotulo{font-size:11px;font-weight:800;letter-spacing:.1em;text-transform:uppercase;color:var(--mudo)}
.perm{display:flex;align-items:center;justify-content:space-between;padding:9px 12px;border:1px solid var(--linha);border-radius:10px;background:#fff;font-size:12.5px}
.ck{width:18px;height:18px;border-radius:5px;border:2px solid #cbd5e1;display:grid;place-items:center;font-size:12px;color:#fff}.ck.on{background:var(--azul2);border-color:var(--azul2)}
"""

ICONES = (
    '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@phosphor-icons/web@2.1.2/src/bold/style.css">'
    '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@phosphor-icons/web@2.1.2/src/fill/style.css">'
)

IMAGENS: dict[str, tuple[int, int, str]] = {}


def imagem(nome: str, largura: int, altura: int):
    def registrar(funcao):
        IMAGENS[nome] = (largura, altura, funcao())
        return funcao

    return registrar


def i(nome: str, extra: str = "", estilo: str = "") -> str:
    return f'<i class="ph-bold ph-{nome} {extra}" style="{estilo}"></i>'


def shell(corpo: str, *, crumb: str = "Visão Geral", ativo: str = "Visão Geral", extra: str = "", usuario="Maria Souza") -> str:
    def nav(texto, icone, on=False, sub=False):
        return f'<div class="nav {"on" if on else ""} {"sub" if sub else ""}">{i(icone) if icone else ""}{texto}</div>'

    itens = "".join(
        [
            nav("Hub de Sistemas", "squares-four"),
            nav("Visão Geral", "house", ativo == "Visão Geral", True),
            nav("Luft-ConnectAir", "airplane-tilt", ativo == "ConnectAir", True),
            nav("Luft-Integrador", "rocket-launch", ativo == "Integrador", True),
            nav("Painel de Controle", "sliders-horizontal", ativo == "Painel"),
            nav("Comunicados", "megaphone", ativo == "Comunicados"),
            nav("Notas de Atualização", "rocket-launch", ativo == "Notas"),
        ]
    )
    iniciais = "".join(p[0] for p in usuario.split()[:2])
    return f"""<div class="shell" style="position:relative">
<div class="side"><div class="marca"><img src="{LOGO}"><div><b>Luft Healthcare</b><small>LUFT-WORKSPACE</small></div></div>{itens}
<div class="usuario"><div class="av">{iniciais}</div><div><b style="font-size:13px">{usuario}</b><div class="mudo" style="font-size:11px">GRUPO TI</div></div></div></div>
<div class="main"><div class="topo"><div class="crumb">{i("house")}<span>Workspace</span>{i("caret-right")}<b>{crumb}</b></div>
<div class="busca">{i("magnifying-glass")}Buscar em todos os sistemas...</div><div class="sino">{i("bell")}<em>3</em></div><div class="av">{iniciais}</div></div>
<div class="corpo">{corpo}</div></div>{extra}</div>"""


def drawer(titulo: str, sub: str, icone: str, corpo: str, abas: str = "", largura: int = 480) -> str:
    return f"""<div class="veu"></div><div class="drawer" style="width:{largura}px"><div class="dh"><div class="ic b">{i(icone)}</div><div style="flex:1"><h3>{titulo}</h3><small>{sub}</small></div>{i("x", "mudo")}</div>{abas}{corpo}</div>"""


def cartao_sistema(nome: str, desc: str, icone: str, cor: str, selo: str = "OPERACIONAL") -> str:
    return f"""<div class="card p16 col"><div class="lin"><div class="ic {cor}">{i(icone)}</div><div style="flex:1"><b>{nome}</b><div class="mudo" style="font-size:12px">{desc}</div></div><span class="chip c-verde">{selo}</span></div>
<div class="btn p" style="justify-content:center">Abrir sistema {i("arrow-right")}</div></div>"""


# ----------------------------------------------------------------------------- ilustrações

@imagem("banner", 1200, 420)
def _():
    return f"""<div class="arte g1 aneis" style="height:420px;padding:70px 80px">
<div class="lin" style="margin-bottom:34px"><div class="ic" style="width:64px;height:64px;background:rgba(255,255,255,.18);border:1px solid rgba(255,255,255,.4);color:#fff;font-size:32px">{i("rocket-launch")}</div><div class="kicker">Nota de atualização</div></div>
<h1>Uma base nova<br>para os sistemas Luft</h1>
<p class="sub" style="margin-top:20px;max-width:700px">Workspace, ConnectAir e Integrador agora compartilham o LuftBase: login único, permissões claras e um painel de controle completo.</p>
<div class="vidro" style="position:absolute;right:70px;bottom:60px;width:250px;padding:18px"><div class="chip" style="background:#22d3ee;color:#083344">LuftBase</div>
<div style="height:10px;border-radius:5px;background:rgba(255,255,255,.7);margin:16px 0 8px;width:70%"></div><div style="height:8px;border-radius:4px;background:rgba(255,255,255,.35);margin-bottom:8px"></div><div style="height:8px;border-radius:4px;background:rgba(255,255,255,.35);width:80%"></div></div></div>"""


@imagem("antes-depois", 1200, 440)
def _():
    def caixa(titulo, cor, linhas):
        itens = "".join(f'<div class="lin" style="font-size:15px">{i(ic, "", "font-size:20px")}{t}</div>' for ic, t in linhas)
        return f'<div class="card p20 col" style="gap:14px;border-top:5px solid {cor}"><div class="lin"><b style="font-size:20px">{titulo}</b></div>{itens}</div>'

    antes = caixa("Antes", "#94a3b8", [("lock-key", "Um login por sistema"), ("key", "Permissões em modelos diferentes"), ("table", "Parâmetros em planilha"), ("bell-slash", "Avisos espalhados"), ("question", "Difícil saber quem fez o quê")])
    depois = caixa("Agora", "#2563eb", [("lock-key-open", "Login único para todos"), ("shield-check", "Permissões padronizadas"), ("database", "Parâmetros no banco, com histórico"), ("bell-ringing", "Comunicados e notas com notificação"), ("clipboard-text", "Auditoria de cada alteração")])
    return f"""<div style="padding:40px 50px;height:440px;background:#f8fafc"><div class="lin" style="justify-content:center;margin-bottom:28px"><h2>O que muda, em um olhar</h2></div>
<div class="grid" style="grid-template-columns:1fr 70px 1fr;align-items:center">{antes}<div style="text-align:center;font-size:44px;color:#2563eb">{i("arrow-right")}</div>{depois}</div></div>"""


@imagem("arquitetura", 1200, 560)
def _():
    def app(x, nome, ic):
        return f'<div class="no" style="left:{x}px;top:70px"><div class="bola">{i(ic)}</div><b>{nome}</b></div>'

    return f"""<div class="arte g6 aneis" style="height:560px">
<div class="kicker" style="position:absolute;left:60px;top:40px">Como tudo se conecta</div>
{app(170,"Workspace","squares-four")}{app(558,"ConnectAir","airplane-tilt")}{app(946,"Integrador","rocket-launch")}
<div class="vidro" style="position:absolute;left:90px;right:90px;top:240px;height:110px;display:flex;align-items:center;justify-content:center;gap:18px;background:linear-gradient(90deg,rgba(37,99,235,.55),rgba(6,182,212,.55))">
<div class="ic" style="background:rgba(255,255,255,.2);color:#fff;width:56px;height:56px;font-size:30px">{i("stack")}</div><div><b style="font-size:26px">LuftBase</b><div style="font-size:14px;opacity:.9">Identidade · Permissões · Sessões · Notificações · Auditoria · Painel de controle</div></div></div>
<div class="fio" style="left:210px;top:200px;width:1px;height:40px;background:#fff"></div><div class="fio" style="left:598px;top:200px;width:1px;height:40px;background:#fff"></div><div class="fio" style="left:986px;top:200px;width:1px;height:40px;background:#fff"></div>
<div style="position:absolute;left:90px;right:90px;bottom:50px;display:grid;grid-template-columns:repeat(4,1fr);gap:14px">
{''.join(f'<div class="vidro" style="padding:14px;text-align:center"><div style="font-size:26px;margin-bottom:6px">{i(ic)}</div><b style="font-size:14px">{t}</b></div>' for ic,t in [("database","Banco corporativo"),("vault","Cofre de senhas"),("identification-card","Diretório de usuários"),("envelope-simple","E-mail")])}</div></div>"""


@imagem("linha-do-tempo", 1200, 300)
def _():
    marcos = [("compass", "Planejamento", "Um núcleo único para os sistemas web"), ("hammer", "Construção", "LuftBase: identidade, permissões e painel"), ("flask", "Homologação", "Testes com a equipe no ambiente de validação"), ("rocket-launch", "Produção", "Entrada em produção, sistema a sistema")]
    caixas = "".join(
        f'<div style="flex:1;text-align:center;position:relative"><div class="ic {"b v a r".split()[n]}" style="margin:0 auto 12px;width:58px;height:58px;font-size:28px">{i(ic)}</div><b style="font-size:16px">{t}</b><div class="mudo" style="font-size:13px;margin-top:4px;padding:0 14px">{d}</div></div>'
        for n, (ic, t, d) in enumerate(marcos)
    )
    return f"""<div style="padding:40px 40px;height:300px;background:#fff"><div class="lin" style="justify-content:center;margin-bottom:28px"><h2>A jornada da migração</h2></div>
<div style="position:relative;display:flex"><div style="position:absolute;left:12%;right:12%;top:28px;height:4px;background:linear-gradient(90deg,#2563eb,#059669,#d97706,#7c3aed);border-radius:2px"></div>{caixas}</div></div>"""


@imagem("login-unico", 1200, 420)
def _():
    return f"""<div class="arte g2 aneis" style="height:420px">
<div class="no" style="left:90px;top:130px"><div class="bola">{i("user-circle")}</div><b>Você</b><small>entra uma vez</small></div>
<div class="fio" style="left:210px;top:172px;width:230px"></div>
<div class="vidro" style="position:absolute;left:450px;top:120px;width:230px;height:104px;display:flex;align-items:center;justify-content:center;gap:12px"><div style="font-size:34px">{i("lock-key-open")}</div><div><b style="font-size:19px">Sessão única</b><div style="font-size:12px;opacity:.85">protegida e auditada</div></div></div>
<div class="fio" style="left:690px;top:172px;width:130px"></div>
<div class="no" style="left:830px;top:40px"><div class="bola" style="width:64px;height:64px;font-size:30px">{i("squares-four")}</div><b style="font-size:15px">Workspace</b></div>
<div class="no" style="left:830px;top:160px"><div class="bola" style="width:64px;height:64px;font-size:30px">{i("airplane-tilt")}</div><b style="font-size:15px">ConnectAir</b></div>
<div class="no" style="left:830px;top:280px"><div class="bola" style="width:64px;height:64px;font-size:30px">{i("rocket-launch")}</div><b style="font-size:15px">Integrador</b></div>
<div class="kicker" style="position:absolute;left:90px;bottom:40px">Entrou em um, está em todos · saiu de um, saiu de todos</div></div>"""


@imagem("permissoes-modelo", 1200, 460)
def _():
    partes = [("CONNECTAIR", "módulo", "#2563eb"), ("SISTEMA", "recurso", "#059669"), ("ACESSAR", "ação", "#d97706")]
    blocos = "".join(f'<div style="text-align:center"><div style="padding:18px 30px;border-radius:16px;background:{c};color:#fff;font-size:34px;font-weight:800" class="mono">{t}</div><div class="rotulo" style="margin-top:10px">{r}</div></div>' for t, r, c in partes)
    pontos = '<div style="font-size:40px;font-weight:800;color:#94a3b8;align-self:flex-start;padding-top:12px">.</div>'
    exemplos = [("INTEGRADOR.SISTEMA.ADMINISTRAR", "Administrar o Integrador", "m"), ("CONNECTAIR.SISTEMA.ACESSAR", "Entrar no ConnectAir", "b"), ("PARAMETROS.REINTEGRACAO.EDITAR", "Editar parâmetros da reintegração", "a")]
    lista = "".join(f'<div class="perm" style="gap:14px"><span class="mono" style="font-weight:700">{c}</span><span class="mudo">{d}</span></div>' for c, d, _ in exemplos)
    return f"""<div style="padding:44px 60px;height:460px;background:#fff"><div class="lin" style="justify-content:center;margin-bottom:26px"><h2>Cada acesso tem nome, dono e motivo</h2></div>
<div style="display:flex;gap:10px;justify-content:center;align-items:flex-start;margin-bottom:34px">{blocos.replace('</div></div><div', '</div></div>' + pontos + '<div')}</div>
<div class="col" style="gap:8px">{lista}</div></div>"""


@imagem("seguranca-camadas", 1200, 520)
def _():
    camadas = [("shield-check", "Sessão protegida", "cookie seguro, expira por inatividade, encerra em todos os sistemas"), ("vault", "Cofre de senhas", "credenciais fora do código e dos arquivos de configuração"), ("identification-badge", "Permissões mínimas", "cada pessoa vê e faz só o que precisa"), ("clipboard-text", "Auditoria", "quem fez o quê, quando e de onde"), ("eye-slash", "Logs sem dados sensíveis", "erros registrados sem expor senhas ou valores")]
    linhas = "".join(f'<div class="vidro lin" style="padding:14px 18px;margin-bottom:12px"><div class="ic" style="background:rgba(255,255,255,.2);color:#fff">{i(ic)}</div><div><b style="font-size:17px">{t}</b><div style="font-size:13px;opacity:.85">{d}</div></div></div>' for ic, t, d in camadas)
    return f"""<div class="arte g3 aneis" style="height:520px;padding:40px 70px"><div class="kicker" style="margin-bottom:8px">Segurança em camadas</div><h2 style="margin-bottom:22px;font-size:30px">Várias proteções, trabalhando juntas</h2>{linhas}</div>"""


@imagem("auditoria-trilha", 1200, 420)
def _():
    ev = [("Maria Souza", "entrou no sistema", "agora há pouco", "sign-in", "b"), ("João Lima", "copiou permissões de um perfil", "há 12 min", "copy", "r"), ("Ana Reis", "editou um parâmetro do Integrador", "há 1 h", "pencil-simple", "a"), ("Pedro Alves", "publicou uma nota de atualização", "há 3 h", "megaphone", "v")]
    linhas = "".join(f'<div class="card p16 lin"><div class="ic {c}">{i(ic)}</div><div style="flex:1"><b>{n}</b> <span class="mudo">{a}</span></div><span class="mudo" style="font-size:12px">{q}</span></div>' for n, a, q, ic, c in ev)
    return f"""<div style="padding:36px 60px;height:420px;background:#f1f5f9"><div class="lin" style="margin-bottom:18px"><h2>Trilha de auditoria</h2><span class="chip c-azul">dados fictícios</span></div><div class="col" style="gap:10px">{linhas}</div></div>"""


@imagem("notificacoes-arte", 1200, 420)
def _():
    notas = [("rocket-launch", "Nova atualização disponível", "Veja o que mudou nos sistemas Luft", "b"), ("megaphone", "Comunicado do TI", "Manutenção programada no sábado", "a"), ("shield-check", "Novo acesso liberado", "Você já pode usar o ConnectAir", "v")]
    cards = "".join(f'<div class="card p16 lin" style="width:520px;box-shadow:0 14px 34px rgba(15,23,42,.18)"><div class="ic {c}">{i(ic)}</div><div><b>{t}</b><div class="mudo" style="font-size:12.5px">{d}</div></div></div>' for ic, t, d, c in notas)
    return f"""<div class="arte g4 aneis" style="height:420px;padding:56px 80px"><div class="kicker" style="margin-bottom:10px">Fique por dentro</div><h2 style="margin-bottom:24px">Avisos que chegam até você</h2>
<div class="col" style="gap:12px;position:absolute;right:80px;top:50px">{cards}</div><p class="sub" style="max-width:420px">Comunicados e notas de atualização aparecem no sino, no feed e na tela de detalhes.</p></div>"""


@imagem("encerramento", 1200, 340)
def _():
    return f"""<div class="arte g1 aneis" style="height:340px;padding:70px 80px"><div class="lin" style="margin-bottom:18px"><div style="font-size:44px">{i("hand-waving")}</div><h1 style="font-size:44px">Obrigado por fazer parte</h1></div>
<p class="sub" style="max-width:760px">Esta é a primeira de muitas melhorias. Se algo não estiver como você espera, fale com o TI: com a nova base, achamos a causa muito mais rápido.</p></div>"""


# ----------------------------------------------------------------------------- telas (maquetes)

@imagem("tela-hub", 1280, 760)
def _():
    cards = cartao_sistema("Luft-ConnectAir", "Sistema de planejamento aéreo", "airplane-tilt", "b") + cartao_sistema("Luft-Integrador", "Integração de arquivos e dados", "rocket-launch", "r") + cartao_sistema("Luft-Workspace", "Portal central dos sistemas", "squares-four", "v")
    kpis = "".join(f'<div class="card p16 lin"><div class="ic {c}">{i(ic)}</div><div><div class="mudo" style="font-size:12px">{t}</div><b style="font-size:24px">{v}</b></div></div>' for ic, t, v, c in [("squares-four", "Total de sistemas", "3", "b"), ("check-circle", "Operacionais", "3", "v"), ("wrench", "Em manutenção", "0", "a")])
    corpo = f'<div class="titulo">Hub de Sistemas</div><div class="lede">Portal central para acessar todo o ecossistema Luft</div><div class="grid g3c" style="margin-bottom:18px">{kpis}</div><div class="grid g3c">{cards}</div>'
    return shell(corpo)


def _perfil_hero() -> str:
    return f"""<div class="lin" style="padding:20px 22px"><div class="av" style="width:64px;height:64px;font-size:22px;position:relative">MS<span style="position:absolute;right:0;bottom:0;width:14px;height:14px;border-radius:50%;background:#10b981;border:2px solid #fff"></span></div>
<div style="flex:1"><div style="font-size:19px;font-weight:800">Maria Souza</div><div style="color:var(--azul2);font-size:12px;font-weight:800">GRUPO TI</div></div><span class="chip c-verde">● Online</span></div>"""


@imagem("tela-perfil-sessoes", 1280, 780)
def _():
    abas = '<div class="tabs"><div>Dados &amp; Contatos</div><div>Aparência &amp; Tema</div><div class="on">Sessões &amp; Segurança</div></div>'
    resumo = f"""<div class="card p16 grid g2c" style="margin:16px 22px;gap:14px"><div class="lin">{i("shield-check", "", "font-size:22px;color:#059669")}<div><div class="rotulo">Status atual</div><b style="color:#059669;font-size:13px">Online &amp; Ativo</b></div></div>
<div class="lin">{i("sign-in", "", "font-size:22px;color:#2563eb")}<div><div class="rotulo">Total de logins</div><b style="font-size:13px">42</b></div></div>
<div class="lin">{i("clock-counter-clockwise", "", "font-size:22px;color:#475569")}<div><div class="rotulo">Último acesso</div><b style="font-size:13px">hoje às 15:25</b></div></div>
<div class="lin">{i("globe", "", "font-size:22px;color:#2563eb")}<div><div class="rotulo">IP registrado</div><b style="font-size:13px">10.20.4.58</b></div></div></div>"""
    sessoes = f"""<div style="padding:0 22px"><div class="lin" style="justify-content:space-between;margin-bottom:10px"><b style="font-size:14px">Dispositivos Conectados</b><span class="btn d" style="padding:6px 10px;font-size:11.5px">{i("sign-out")}Desconectar outras sessões</span></div>
<div class="sess on" style="margin-bottom:8px">{i("desktop","d")}<div style="flex:1"><b>Chrome 126 em Windows</b> <span class="chip c-verde" style="font-size:10px">Esta sessão</span><small>IP 10.20.4.58 • Última atividade: hoje 15:25</small></div></div>
<div class="sess">{i("device-mobile","d")}<div><b>Safari 17 em iOS</b><small>IP 10.20.9.131 • Última atividade: hoje 12:02</small></div></div></div>"""
    hist = "".join(
        f'<div class="sess" style="margin-bottom:7px">{i(ic, "d")}<div style="flex:1"><b>{n}</b><small>IP {ip} • Início: {ini} • Fim: {fim}</small></div></div>'
        for ic, n, ip, ini, fim in [("desktop", "Chrome 126 em Windows", "10.20.4.58", "06/10 14:02", "Em andamento"), ("desktop", "Firefox 128 em Windows", "10.20.4.58", "05/10 09:15", "05/10 18:40 (Saiu da conta)"), ("device-mobile", "Safari 17 em iOS", "10.20.9.131", "04/10 08:47", "04/10 08:59 (Expirou por inatividade)")]
    )
    historico = f'<div style="padding:16px 22px"><b style="font-size:14px">Histórico de Acessos</b><div class="mudo" style="font-size:11.5px;margin:2px 0 10px">Seus 5 últimos acessos</div>{hist}</div>'
    corpo = _perfil_hero() + abas + resumo + sessoes + historico
    return shell(
        '<div class="titulo">Hub de Sistemas</div><div class="lede">Portal central</div><div class="grid g3c"><div class="card" style="height:180px"></div><div class="card" style="height:180px"></div><div class="card" style="height:180px"></div></div>',
        extra=drawer("Configurações de Perfil", "Gestão da sua conta corporativa Luft", "user-gear", corpo, largura=520),
    )


@imagem("tela-editor-foto", 1280, 760)
def _():
    modal = f"""<div class="veu"></div><div class="card" style="position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);width:520px;padding:22px;box-shadow:0 30px 80px rgba(15,23,42,.4)">
<div class="lin" style="margin-bottom:14px"><div class="ic b">{i("camera")}</div><div style="flex:1"><b style="font-size:17px">Foto de perfil</b><div class="mudo" style="font-size:12px">Arraste para posicionar e ajuste o zoom</div></div>{i("x","mudo")}</div>
<div style="position:relative;height:300px;border-radius:14px;background:linear-gradient(135deg,#334155,#0f172a);display:grid;place-items:center;overflow:hidden">
<div style="position:absolute;inset:0;background:radial-gradient(circle at 50% 50%,transparent 128px,rgba(15,23,42,.62) 130px)"></div>
<div style="width:256px;height:256px;border-radius:50%;background:linear-gradient(135deg,#6366f1,#06b6d4);display:grid;place-items:center;color:#fff;font-size:92px;border:3px solid rgba(255,255,255,.9)">{i("user","","font-size:110px")}</div></div>
<div class="lin" style="margin:16px 0 12px"><span class="mudo" style="font-size:12px;font-weight:700">Zoom</span><div class="barra" style="flex:1"><span style="width:38%"></span></div><span class="btn" style="padding:6px 10px">{i("arrow-counter-clockwise")}</span><span class="btn" style="padding:6px 10px">{i("arrow-clockwise")}</span><span class="btn" style="padding:6px 10px">{i("crosshair")}</span></div>
<div class="lin" style="justify-content:space-between"><span class="btn d">{i("trash")}Remover foto</span><div class="lin"><span class="btn">Cancelar</span><span class="btn p">{i("check")}Salvar foto</span></div></div></div>"""
    return shell('<div class="titulo">Hub de Sistemas</div><div class="grid g3c" style="margin-top:20px"><div class="card" style="height:200px"></div><div class="card" style="height:200px"></div><div class="card" style="height:200px"></div></div>', extra=modal)


@imagem("tela-integracoes", 1280, 780)
def _():
    def card(nome, desc, ic, cor, status, ver):
        return f"""<div class="card p16 col"><div class="lin"><div class="ic {cor}">{i(ic)}</div><div style="flex:1"><b>{nome}</b><div class="mudo" style="font-size:12px">{desc}</div></div><span class="chip {'c-verde' if status=='Conectado' else 'c-amb'}">● {status}</span></div>
<div class="lin" style="justify-content:space-between"><span class="mudo" style="font-size:12px">{ver}</span><span class="btn" style="padding:6px 10px">Detalhes</span></div></div>"""

    cards = card("Cofre de senhas", "Credenciais e segredos dos sistemas", "vault", "r", "Conectado", "Versão do servidor 1.x") + card("Banco corporativo", "Core: usuários, sessões e permissões", "database", "b", "Conectado", "PostgreSQL") + card("Banco de negócio", "Dados dos sistemas de operação", "table", "v", "Conectado", "SQL Server") + card("E-mail", "Envio de avisos e redefinição de senha", "envelope-simple", "a", "Conectado", "SMTP") + card("Diretório de usuários", "Autenticação corporativa", "identification-card", "b", "Conectado", "LDAP") + card("Sessões", "Armazenamento das sessões", "lock-key-open", "v", "Conectado", "PostgreSQL (core)")
    versoes = "".join(f'<tr><td><b>{s}</b></td><td class="mono">{v}</td><td><span class="chip c-verde">Atualizado</span></td></tr>' for s, v in [("Luft-Workspace", "LuftBase 0.1"), ("Luft-ConnectAir", "LuftBase 0.1"), ("Luft-Integrador", "LuftBase 0.1")])
    corpo = f'<div class="titulo">Integrações</div><div class="lede">Estado dos serviços que sustentam os sistemas</div><div class="grid g3c" style="margin-bottom:16px">{cards}</div><div class="card"><table><tr><th>Sistema</th><th>Base</th><th>Situação</th></tr>{versoes}</table></div>'
    return shell(corpo, crumb="Integrações", ativo="Painel")


@imagem("tela-servicos", 1280, 700)
def _():
    linhas = "".join(
        f'<tr><td class="lin">{i(ic,"","font-size:20px;color:#2563eb")}<b>{n}</b></td><td><span class="chip {c}">● {s}</span></td><td class="mudo">{u}</td><td style="text-align:right"><span class="btn" style="padding:5px 9px">{i("arrow-clockwise")}Reiniciar</span></td></tr>'
        for ic, n, s, c, u in [("squares-four", "Luft-Workspace", "Em execução", "c-verde", "há 2 dias"), ("airplane-tilt", "Luft-ConnectAir", "Em execução", "c-verde", "há 5 h"), ("rocket-launch", "Luft-Integrador", "Em execução", "c-verde", "há 1 dia")]
    )
    corpo = f'<div class="titulo">Serviços do servidor</div><div class="lede">Veja o estado e reinicie o serviço de cada sistema, sem acessar o servidor</div><div class="card"><table><tr><th>Serviço</th><th>Situação</th><th>No ar</th><th></th></tr>{linhas}</table></div><div class="card p16 lin" style="margin-top:14px;background:#fffbeb;border-color:#fde68a">{i("warning","","font-size:22px;color:#b45309")}<div style="font-size:13px"><b>Ações registradas.</b> Todo reinício fica na auditoria, com o nome de quem pediu.</div></div>'
    return shell(corpo, crumb="Serviços do servidor", ativo="Painel")


@imagem("tela-copiar-permissoes", 1280, 760)
def _():
    passos = f'<div class="lin" style="gap:26px;margin-bottom:18px"><div class="passo ok"><i>{i("check")}</i>Origem</div><div class="passo on"><i>2</i>Escolher permissões</div><div class="passo"><i>3</i>Destino</div></div>'
    perms = [("CONNECTAIR.SISTEMA.ACESSAR", True), ("PARAMETROS.REINTEGRACAO.VISUALIZAR", True), ("INTEGRADOR.SISTEMA.ACESSAR", True), ("PARAMETROS.REINTEGRACAO.EDITAR", False), ("CONTEUDO.COMUNICADOS.CRIAR", False), ("CONTEUDO.ATUALIZACOES.PUBLICAR", False)]
    lista = "".join(f'<div class="perm"><span class="lin"><span class="ck {"on" if o else ""}">{i("check") if o else ""}</span><span class="mono">{p}</span></span><span class="chip {"c-azul" if o else "c-cinza"}">{"Será copiada" if o else "Ignorada"}</span></div>' for p, o in perms)
    corpo = f'<div class="titulo">Copiar permissões</div><div class="lede">Leve o acesso de uma pessoa para outra, em três passos, vendo antes o que será copiado</div>{passos}<div class="card p20 col"><div class="lin"><div class="av">LA</div><div style="flex:1"><b>Origem: Luciano A.</b><div class="mudo" style="font-size:12px">Perfil de referência · 24 permissões</div></div><span class="chip c-azul">3 selecionadas</span></div><div class="col" style="gap:7px">{lista}</div><div class="lin" style="justify-content:flex-end"><span class="btn">Voltar</span><span class="btn p">Continuar {i("arrow-right")}</span></div></div>'
    return shell(corpo, crumb="Segurança", ativo="Painel")


@imagem("tela-parametros", 1280, 760)
def _():
    linhas = "".join(
        f'<tr><td><b>{c}</b></td><td class="mono">{h}</td><td class="mono">{u}</td><td class="mudo" style="font-size:12px">{p}</td><td><span class="chip {"c-verde" if a else "c-cinza"}">{"Ativo" if a else "Inativo"}</span></td><td style="text-align:right;color:#475569">{i("pencil-simple")} &nbsp;{i("plugs-connected")} &nbsp;{i("eye")}</td></tr>'
        for c, h, u, p, a in [("Cliente Exemplo A", "sftp.exemplo-a.com:22", "usuario_a", "↙ /entrada   ↗ /saida", True), ("Cliente Exemplo B", "sftp.exemplo-b.com:22", "usuario_b", "↙ /in   ↗ /out", True), ("Cliente Exemplo C", "files.exemplo-c.com:2222", "usuario_c", "↙ /recebidos   ↗ /enviados", False)]
    )
    abas = '<div class="lin" style="gap:8px;margin-bottom:14px"><span class="chip c-azul" style="padding:8px 14px">Reintegração WMS</span><span class="chip c-cinza" style="padding:8px 14px">XMLs Ecobox</span></div>'
    corpo = f'<div class="lin" style="justify-content:space-between"><div><div class="titulo">Parâmetros das integrações</div><div class="lede">Antes numa planilha, agora no banco, com histórico e senhas protegidas</div></div><span class="btn p">{i("plus")}Novo cliente</span></div>{abas}<div class="card"><table><tr><th>Cliente</th><th>Servidor</th><th>Usuário</th><th>Pastas</th><th>Situação</th><th></th></tr>{linhas}</table></div><div class="card p16 lin" style="margin-top:14px;background:#ecfdf5;border-color:#a7f3d0">{i("lock-key","","font-size:22px;color:#047857")}<div style="font-size:13px"><b>Senhas cifradas.</b> Ninguém consegue ver uma senha depois de salva, nem nos logs.</div></div>'
    return shell(corpo, crumb="Parâmetros", ativo="Integrador")


@imagem("tela-notas", 1280, 760)
def _():
    def nota(v, t, r, tags, novo=False):
        return f"""<div class="card p20 col" style="gap:8px;{'border-left:5px solid #2563eb' if novo else ''}"><div class="lin"><span class="chip c-azul">CHANGELOG</span><span class="chip c-cinza">v{v}</span><span class="chip c-roxo">{i("globe")}Global</span>{'<span class="chip c-verde">NOVO</span>' if novo else ''}</div>
<b style="font-size:17px">{t}</b><div class="mudo" style="font-size:13px">{r}</div></div>"""

    corpo = '<div class="titulo">Notas de Atualização</div><div class="lede">Tudo o que mudou nos sistemas Luft</div><div class="col">' + nota("2.0", "Nova base dos sistemas Luft", "Login único, permissões claras, perfil renovado e painel de controle completo.", "", True) + nota("1.9", "Melhorias de desempenho", "Telas mais rápidas e mensagens de erro mais claras.", "") + nota("1.8", "Ajustes de acessibilidade", "Contraste e navegação por teclado revisados.", "") + "</div>"
    return shell(corpo, crumb="Notas de Atualização", ativo="Notas")


@imagem("tela-notificacoes", 1280, 700)
def _():
    pop = f"""<div class="card" style="position:absolute;right:70px;top:62px;width:420px;box-shadow:0 24px 60px rgba(15,23,42,.3)"><div class="lin" style="padding:14px 16px;border-bottom:1px solid var(--linha);justify-content:space-between"><b>Notificações</b><span class="mudo" style="font-size:12px">Marcar todas como lidas</span></div>
{''.join(f'<div class="lin" style="padding:13px 16px;border-bottom:1px solid #eef2f7;background:{"#eff6ff" if n else "#fff"}"><div class="ic {c}" style="width:36px;height:36px;font-size:18px">{i(ic)}</div><div style="flex:1"><b style="font-size:13px">{t}</b><div class="mudo" style="font-size:12px">{d}</div></div>{"<span style=width:9px;height:9px;border-radius:50%;background:#2563eb></span>" if n else ""}</div>' for ic,c,t,d,n in [("rocket-launch","b","Nova base dos sistemas Luft","Veja o que mudou para você",True),("megaphone","a","Comunicado do TI","Janela de manutenção no sábado",True),("shield-check","v","Acesso liberado","Você já pode usar o ConnectAir",False)])}</div>"""
    return shell('<div class="titulo">Hub de Sistemas</div><div class="grid g3c" style="margin-top:18px"><div class="card" style="height:180px"></div><div class="card" style="height:180px"></div><div class="card" style="height:180px"></div></div>', extra=pop)


@imagem("tela-busca", 1280, 700)
def _():
    caixa = f"""<div class="veu"></div><div class="card" style="position:absolute;left:50%;top:90px;transform:translateX(-50%);width:640px;box-shadow:0 30px 80px rgba(15,23,42,.4)"><div class="lin" style="padding:16px 18px;border-bottom:1px solid var(--linha)">{i("magnifying-glass","","font-size:20px;color:#2563eb")}<b style="font-size:16px">parâmetros</b></div>
{''.join(f'<div class="lin" style="padding:12px 18px;border-bottom:1px solid #eef2f7;background:{"#eff6ff" if n==0 else "#fff"}"><div class="ic {c}" style="width:34px;height:34px;font-size:17px">{i(ic)}</div><div style="flex:1"><b style="font-size:13.5px">{t}</b><div class="mudo" style="font-size:12px">{d}</div></div><span class="chip c-cinza">{s}</span></div>' for n,(ic,c,t,d,s) in enumerate([("sliders-horizontal","r","Parâmetros das integrações","Reintegração WMS e Ecobox","Integrador"),("gear","b","Configurações gerais","Parâmetros do sistema","Painel"),("clock-counter-clockwise","a","Auditoria","Alterações de parâmetros","Segurança")]))}</div>"""
    return shell('<div class="titulo">Hub de Sistemas</div>', extra=caixa)


@imagem("tela-temas", 1280, 520)
def _():
    def mini(titulo, fundo, side, card, texto, acento):
        return f"""<div class="col" style="gap:8px"><div style="border-radius:14px;overflow:hidden;border:1px solid #cbd5e1;background:{fundo};height:300px;display:flex"><div style="width:70px;background:{side}"></div><div style="flex:1;padding:16px" class="col"><div style="height:14px;width:55%;border-radius:7px;background:{texto}"></div>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px"><div style="height:80px;border-radius:10px;background:{card}"></div><div style="height:80px;border-radius:10px;background:{card}"></div></div><div style="height:12px;width:40%;border-radius:6px;background:{acento}"></div><div style="height:12px;width:70%;border-radius:6px;background:{texto};opacity:.4"></div></div></div><b style="text-align:center;font-size:15px">{titulo}</b></div>"""

    corpo = '<div class="titulo" style="text-align:center">Escolha o seu visual</div><div class="lede" style="text-align:center">Tema claro, tema escuro e a identidade ESG. A escolha fica salva na sua conta.</div><div class="grid g3c" style="padding:0 40px">' + mini("Claro", "#f1f5f9", "#ffffff", "#ffffff", "#0f172a", "#2563eb") + mini("Escuro", "#0f172a", "#111c33", "#1e293b", "#e2e8f0", "#38bdf8") + mini("ESG", "#f0fdf4", "#ffffff", "#dcfce7", "#14532d", "#16a34a") + "</div>"
    return f'<div style="padding:34px;height:520px;background:#fff">{corpo}</div>'


@imagem("tela-login", 1280, 700)
def _():
    return f"""<div style="display:flex;height:700px"><div class="arte g1 aneis" style="flex:1;padding:80px"><img src="{LOGO}" style="width:70px;filter:brightness(0) invert(1);margin-bottom:28px"><h1 style="font-size:46px">Bem-vindo ao<br>ecossistema Luft</h1><p class="sub" style="margin-top:18px;max-width:420px">Um acesso único para o Workspace, o ConnectAir e o Integrador.</p></div>
<div style="width:520px;background:#fff;display:grid;place-items:center"><div style="width:360px" class="col"><div style="font-size:26px;font-weight:800">Entrar</div><div class="mudo" style="font-size:13px;margin-top:-6px">Use o seu usuário e senha corporativos</div>
<div class="card p16 lin" style="box-shadow:none">{i("user","mudo")}<span class="mudo">Usuário</span></div><div class="card p16 lin" style="box-shadow:none">{i("lock","mudo")}<span class="mudo">Senha</span></div><div class="btn p" style="justify-content:center;padding:13px">Entrar</div></div></div></div>"""


def gerar(nomes: list[str]) -> None:
    if CHROME is None:
        raise SystemExit("Chrome/Edge não encontrado.")
    SAIDA.mkdir(parents=True, exist_ok=True)
    escolhidas = nomes or sorted(IMAGENS)
    with tempfile.TemporaryDirectory() as tmp:
        for nome in escolhidas:
            largura, altura, corpo = IMAGENS[nome]
            html = Path(tmp) / f"{nome}.html"
            html.write_text(
                f'<!doctype html><html><head><meta charset="utf-8">{ICONES}<style>{CSS}</style></head>'
                f'<body style="width:{largura}px;height:{altura}px">{corpo}</body></html>',
                encoding="utf-8",
            )
            destino = SAIDA / f"{nome}.png"
            subprocess.run(
                [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--virtual-time-budget=8000",
                 f"--window-size={largura},{altura}", f"--screenshot={destino}", html.as_uri()],
                check=True, capture_output=True, timeout=90,
            )
            print(f"{nome}.png  {destino.stat().st_size // 1024} KB")


if __name__ == "__main__":
    gerar(sys.argv[1:])
