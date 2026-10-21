"""Imagens da nota global da plataforma sobre os cinco sistemas na nova base (PNG, via Chrome sem interface).

    python tools/gerar_imagens_changelog_sistemas.py                 # gera tudo
    python tools/gerar_imagens_changelog_sistemas.py banner cronologia   # so algumas

Complementa `gerar_imagens_changelog.py` (perfil, notificacoes, temas, busca...): as imagens daqui
(banner, antes-depois, linha-do-tempo, login-unico, tela-hub e as novas) NAO existem la, para que
nenhuma geracao sobrescreva a outra. As telas sao maquetes com dados ficticios. Precisa de internet
(os icones Phosphor vem do CDN) e do Chrome ou Edge.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SAIDA = RAIZ / "src" / "luftbase" / "interface" / "static" / "img" / "changelog"
SO = set(sys.argv[1:])
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
html,body{width:100%;height:100%}
body{font-family:'Segoe UI',Arial,sans-serif;color:#0f172a;overflow:hidden}
.f{width:100%;height:100%;padding:40px 56px;position:relative;background:#f8fafc}
.f.cl{background:radial-gradient(900px 420px at 100% 0%,#dbeafe 0%,transparent 60%),radial-gradient(700px 420px at 0% 100%,#e0e7ff 0%,transparent 60%),#f8fafc}
.f.es{background:linear-gradient(135deg,#0b1f5c 0%,#1d4ed8 55%,#06b6d4 100%);color:#fff}
.es::before{content:"";position:absolute;right:-120px;top:-160px;width:620px;height:620px;border-radius:50%;border:2px solid rgba(255,255,255,.14)}
.es::after{content:"";position:absolute;right:-20px;top:-60px;width:420px;height:420px;border-radius:50%;border:2px solid rgba(255,255,255,.14)}
.selo{display:inline-flex;gap:8px;align-items:center;padding:7px 16px;border-radius:999px;background:#dbeafe;color:#1d4ed8;font-weight:800;font-size:14px;letter-spacing:.09em;text-transform:uppercase}
.es .selo{background:rgba(255,255,255,.18);color:#fff}
h1{font-size:52px;line-height:1.08;letter-spacing:-.03em;font-weight:900}
h2{font-size:33px;letter-spacing:-.02em;font-weight:850}
.sub{font-size:21px;line-height:1.45;color:#475569;margin-top:10px}
.es .sub{color:#dbeafe}
.c{background:#fff;border:1px solid #e2e8f0;border-radius:18px;box-shadow:0 14px 34px rgba(15,23,42,.09)}
.ic{display:inline-flex;align-items:center;justify-content:center;border-radius:16px}
.pill{display:inline-flex;align-items:center;gap:6px;padding:6px 13px;border-radius:999px;font-weight:800;font-size:14px}
.ok{background:#d1fae5;color:#047857}.av{background:#fef3c7;color:#b45309}.in{background:#dbeafe;color:#1d4ed8}.cz{background:#e2e8f0;color:#475569}.pe{background:#fee2e2;color:#b91c1c}
.grid{display:grid;gap:18px}
.rod{position:absolute;left:56px;bottom:22px;font-size:15px;color:#64748b;font-weight:600}
.es .rod{color:#bfdbfe}
.num{width:36px;height:36px;border-radius:50%;background:#2563eb;color:#fff;display:inline-flex;align-items:center;justify-content:center;font-weight:900;font-size:18px;flex:0 0 auto}
.seta{font-size:36px;color:#2563eb;display:flex;align-items:center;justify-content:center}
.tc{text-align:center}
"""

SIS = [
    ("Luft-Workspace", "squares-four", "#047857", "#d1fae5", "Portal central dos sistemas", "02/10"),
    ("Luft-ConnectAir", "airplane-tilt", "#1d4ed8", "#dbeafe", "Sistema de planejamento aéreo", "02/10"),
    ("Luft-Integrador", "rocket-launch", "#6d28d9", "#ede9fe", "Integração de arquivos e dados", "05/10"),
    ("Luft-Control", "cpu", "#b45309", "#fef3c7", "Controladoria: Razão, DRE e Budget", "14/10"),
    ("Luft-Docs", "books", "#be185d", "#fce7f3", "Documentação dos sistemas e assistente LIA", "19/10"),
]


def i(nome, extra=""):
    return f'<i class="ph-bold ph-{nome}" {extra}></i>'


def pagina(corpo, classe=""):
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<link rel='stylesheet' href='https://cdn.jsdelivr.net/npm/@phosphor-icons/web@2.1.2/src/bold/style.css'>"
        f"<style>{CSS}</style></head><body><div class='f {classe}'>{corpo}</div></body></html>"
    )


def cartao_sis(n, comp=False, desde=True, badge="Já na nova base"):
    nome, ic, cor, fundo, desc, data = SIS[n]
    tam = 62 if not comp else 54
    return f"""<div class='c' style='padding:{22 if not comp else 18}px;text-align:center'>
 <span class='ic' style='width:{tam}px;height:{tam}px;background:{fundo};color:{cor};font-size:{tam*0.5:.0f}px'>{i(ic)}</span>
 <div style='font-size:{19 if comp else 21}px;font-weight:850;margin-top:12px;white-space:nowrap'>{nome}</div>
 {f"<div style='font-size:15px;color:#64748b;margin-top:5px;line-height:1.35;min-height:40px'>{desc}</div>" if not comp else ''}
 <div style='margin-top:10px'><span class='pill ok'>{i('check-circle')} {badge}</span></div>
 {f"<div style='font-size:14px;color:#64748b;margin-top:9px;font-weight:700'>desde {data}/2026</div>" if desde else ''}
</div>"""


IMG = {}

IMG["banner"] = (1200, 420, "es", f"""
<div style='display:grid;grid-template-columns:1.25fr 1fr;gap:30px;align-items:center;height:100%'>
 <div>
  <div style='display:flex;align-items:center;gap:14px'><span class='ic' style='width:62px;height:62px;background:rgba(255,255,255,.18);font-size:30px'>{i('rocket-launch')}</span><span style='letter-spacing:.22em;font-weight:800;font-size:16px;color:#c7d2fe'>NOTA DE ATUALIZAÇÃO</span></div>
  <h1 style='margin-top:22px'>Uma base nova<br>para o seu dia a dia</h1>
  <p class='sub' style='max-width:640px'>Login único, perfil renovado, avisos com notificação e comunicados escritos como e-mails, agora em cinco sistemas Luft.</p>
 </div>
 <div style='background:rgba(255,255,255,.14);border:1px solid rgba(255,255,255,.25);border-radius:22px;padding:24px'>
  <span class='pill' style='background:#22d3ee;color:#083344'>LuftBase</span>
  <div style='display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-top:20px'>{''.join(f"<span class='ic' style='width:100%;aspect-ratio:1;background:rgba(255,255,255,.2);font-size:26px'>{i(s[1])}</span>" for s in SIS)}</div>
  <div style='margin-top:18px;height:12px;border-radius:6px;background:rgba(255,255,255,.55);width:72%'></div>
  <div style='margin-top:10px;height:12px;border-radius:6px;background:rgba(255,255,255,.3);width:92%'></div>
  <div style='margin-top:10px;height:12px;border-radius:6px;background:rgba(255,255,255,.3);width:55%'></div>
 </div>
</div>""")

IMG["linha-do-tempo"] = (1200, 380, "", f"""
<div class='tc'><h2 style='font-size:42px;font-weight:900'>Quais sistemas já estão na nova base</h2><p class='sub' style='margin-top:6px;font-size:19px'>Os cinco sistemas abaixo já usam o LuftBase</p></div>
<div class='grid' style='grid-template-columns:repeat(5,1fr);margin-top:28px'>{''.join(cartao_sis(n, comp=True) for n in range(5))}</div>""")

IMG["login-unico"] = (1200, 440, "es", f"""
<div style='display:grid;grid-template-columns:230px 1fr 330px 1fr 250px;align-items:center;height:100%'>
 <div class='tc'><span class='ic' style='width:92px;height:92px;border-radius:26px;background:rgba(255,255,255,.2);font-size:46px'>{i('user-circle')}</span><div style='font-size:24px;font-weight:850;margin-top:12px'>Você</div><div style='font-size:15px;color:#dbeafe'>entra uma vez</div></div>
 <div style='height:3px;background:linear-gradient(90deg,transparent,rgba(255,255,255,.8),transparent)'></div>
 <div style='background:rgba(255,255,255,.18);border:1px solid rgba(255,255,255,.3);border-radius:22px;padding:26px;display:flex;gap:14px;align-items:center'><span style='font-size:44px'>{i('lock-key-open')}</span><div><div style='font-size:26px;font-weight:900'>Sessão única</div><div style='font-size:15px;color:#dbeafe'>protegida e auditada</div></div></div>
 <div style='height:3px;background:linear-gradient(90deg,transparent,rgba(255,255,255,.8),transparent)'></div>
 <div style='display:grid;gap:9px'>{''.join(f"<div style='display:flex;align-items:center;gap:12px;background:rgba(255,255,255,.18);border-radius:14px;padding:9px 14px'><span style='font-size:26px'>{i(s[1])}</span><b style='font-size:18px'>{s[0].replace('Luft-','')}</b></div>" for s in SIS)}</div>
</div>
<div class='rod' style='letter-spacing:.2em;font-weight:800;left:56px;bottom:26px;text-transform:uppercase;color:#dbeafe'>Entrou em um, está em todos · Saiu de um, saiu de todos</div>""")

linhas_antes = ["Um login por sistema", "Perfil diferente em cada tela", "Avisos espalhados", "Difícil saber onde a conta está aberta", "Cada sistema com o seu visual", "Comunicados em texto simples"]
linhas_agora = ["Login único para todos", "Perfil igual em todos os sistemas", "Comunicados e notas com notificação", "Dispositivos e histórico de acessos", "Temas claro, escuro e ESG", "Comunicados escritos como e-mails"]
ic_antes = ["lock", "user-circle", "bell-slash", "question", "palette", "text-t"]
ic_agora = ["lock-open", "user-circle", "bell-ringing", "devices", "palette", "envelope-simple"]
IMG["antes-depois"] = (1200, 560, "", f"""
<div class='tc'><h2 style='font-size:42px;font-weight:900'>O que muda, em um olhar</h2></div>
<div style='display:grid;grid-template-columns:1fr 70px 1fr;gap:10px;margin-top:30px;align-items:center'>
 <div class='c' style='padding:26px 30px;border-top:7px solid #94a3b8'><div style='font-size:24px;font-weight:850;margin-bottom:12px'>Antes</div>{''.join(f"<div style='display:flex;gap:14px;align-items:center;font-size:19px;margin:13px 0;color:#334155'><span style='font-size:24px'>{i(ic_antes[k])}</span>{linhas_antes[k]}</div>" for k in range(6))}</div>
 <div class='seta'>{i('arrow-right')}</div>
 <div class='c' style='padding:26px 30px;border-top:7px solid #2563eb'><div style='font-size:24px;font-weight:850;margin-bottom:12px'>Agora</div>{''.join(f"<div style='display:flex;gap:14px;align-items:center;font-size:19px;margin:13px 0'><span style='font-size:24px;color:#2563eb'>{i(ic_agora[k])}</span>{linhas_agora[k]}</div>" for k in range(6))}</div>
</div>""")


def hub_cartao(n, estado="Online"):
    nome, ic, cor, fundo, desc, _ = SIS[n]
    return f"""<div style='background:#fff;border:1px solid #e2e8f0;border-radius:16px;padding:18px'>
 <div style='display:flex;gap:12px;align-items:center'><span class='ic' style='width:48px;height:48px;border-radius:13px;background:{fundo};color:{cor};font-size:24px'>{i(ic)}</span>
 <div style='flex:1'><div style='font-size:18px;font-weight:850'>{nome}</div><div style='font-size:13px;color:#64748b;margin-top:2px;line-height:1.3'>{desc}</div></div>
 <span class='pill ok' style='font-size:12px;padding:4px 10px'>{estado}</span></div>
 <div style='margin-top:14px;background:#2563eb;color:#fff;border-radius:10px;padding:10px;text-align:center;font-weight:800;font-size:15px'>Abrir sistema {i('arrow-right')}</div></div>"""


IMG["tela-hub"] = (1280, 760, "", f"""
<div style='position:absolute;inset:0;display:grid;grid-template-columns:230px 1fr;background:#f1f5f9'>
 <div style='background:#fff;border-right:1px solid #e2e8f0;padding:18px 14px'>
  <div style='display:flex;gap:10px;align-items:center;padding:4px 6px 16px;border-bottom:1px solid #e2e8f0'><span class='ic' style='width:38px;height:38px;border-radius:10px;background:#2563eb;color:#fff;font-size:20px'>{i('squares-four')}</span><div><b style='font-size:15px'>Luft Healthcare</b><div style='font-size:11px;font-weight:800;color:#2563eb;letter-spacing:.07em'>LUFT-WORKSPACE</div></div></div>
  <div style='margin-top:14px;font-size:14px;color:#334155;display:grid;gap:4px'>
   <div style='padding:8px 10px;font-weight:700'>{i('squares-four')} Hub de Sistemas</div>
   <div style='padding:8px 10px 8px 26px;background:#dbeafe;color:#1d4ed8;border-radius:9px;font-weight:700'>{i('house')} Visão Geral</div>
   {''.join(f"<div style='padding:8px 10px 8px 26px;color:#475569'>{i(SIS[n][1])} {SIS[n][0]}</div>" for n in (1, 3, 4, 2))}
   <div style='padding:8px 10px;font-weight:700;margin-top:6px'>{i('sliders-horizontal')} Painel de Controle</div>
   <div style='padding:8px 10px;font-weight:700'>{i('megaphone-simple')} Comunicados</div>
   <div style='padding:8px 10px;font-weight:700'>{i('rocket-launch')} Notas de Atualização</div>
  </div>
  <div style='position:absolute;left:14px;bottom:16px;width:202px;border:1px solid #e2e8f0;border-radius:12px;padding:10px;display:flex;gap:10px;align-items:center'><span class='ic' style='width:36px;height:36px;border-radius:50%;background:linear-gradient(135deg,#2563eb,#06b6d4);color:#fff;font-weight:800;font-size:13px'>MS</span><div><b style='font-size:14px'>Maria Souza</b><div style='font-size:11px;color:#64748b'>GRUPO TI</div></div></div>
 </div>
 <div style='padding:0 26px'>
  <div style='height:62px;display:flex;align-items:center;justify-content:space-between'><div style='font-size:14px;color:#64748b'>{i('house')} Workspace &nbsp;›&nbsp; <b style='color:#0f172a'>Visão Geral</b></div><div style='display:flex;gap:12px;align-items:center'><div style='background:#e8edf5;border-radius:10px;padding:9px 16px;font-size:13px;color:#64748b;width:240px'>{i('magnifying-glass')} Buscar telas e funções...</div><span style='font-size:22px'>{i('bell')}</span></div></div>
  <div style='display:flex;justify-content:space-between;align-items:flex-end'><div><div style='font-size:30px;font-weight:900;letter-spacing:-.02em'>Bom dia, Maria</div><div style='font-size:14px;color:#64748b;margin-top:4px'>Portal central para acessar todo o ecossistema Luft</div></div><span class='pill ok'>{i('circle', 'style="font-size:9px"')} Todos os sistemas online</span></div>
  <div class='grid' style='grid-template-columns:repeat(4,1fr);margin-top:18px;gap:14px'>
   {''.join(f"<div class='c' style='padding:14px 16px;box-shadow:none;border-radius:14px'><div style='font-size:12px;color:#64748b'>{t}</div><div style='font-size:26px;font-weight:900;margin-top:2px'>{v}</div></div>" for t, v in [("Total de sistemas", 5), ("Online", "5 de 5"), ("Em manutenção", 0), ("Favoritos", 2)])}
  </div>
  <div class='grid' style='grid-template-columns:repeat(3,1fr);margin-top:16px;gap:14px'>{''.join(hub_cartao(n) for n in (1, 3, 4))}{''.join(hub_cartao(n) for n in (2, 0))}</div>
 </div>
</div>""")

IMG["sistemas-cartoes"] = (1200, 600, "cl", f"""
<div class='tc'><span class='selo'>Os sistemas da nova base</span><h2 style='margin-top:12px'>Cinco sistemas, a mesma experiência</h2></div>
<div class='grid' style='grid-template-columns:repeat(3,1fr);margin-top:26px'>{''.join(cartao_sis(n) for n in range(5))}
<div class='c' style='padding:22px;border:2px dashed #cbd5e1;box-shadow:none;background:transparent;display:flex;align-items:center;justify-content:center;text-align:center;color:#64748b;font-size:17px;line-height:1.45'>Os demais sistemas da Luft seguem com o próprio login e o próprio visual. Você será avisado das novidades.</div></div>""")

marcos = [("02/10", "Workspace e ConnectAir", "squares-four", "#047857"), ("05/10", "Integrador", "rocket-launch", "#6d28d9"), ("14/10", "Control", "cpu", "#b45309"), ("19/10", "Docs", "books", "#be185d"), ("21/10", "Editor de comunicados", "envelope-simple", "#1d4ed8")]
IMG["cronologia"] = (1200, 440, "cl", f"""
<div class='tc'><span class='selo'>Outubro de 2026</span><h2 style='margin-top:12px'>Como chegamos até aqui</h2></div>
<div style='position:relative;margin-top:50px'>
 <div style='position:absolute;left:60px;right:60px;top:34px;height:6px;border-radius:3px;background:linear-gradient(90deg,#2563eb,#06b6d4)'></div>
 <div class='grid' style='grid-template-columns:repeat(5,1fr);position:relative'>{''.join(f"<div class='tc'><span class='ic' style='width:74px;height:74px;border-radius:50%;background:#fff;border:6px solid {c};color:{c};font-size:30px;box-shadow:0 8px 18px rgba(15,23,42,.15)'>{i(ic)}</span><div style='font-size:24px;font-weight:900;margin-top:16px'>{d}</div><div style='font-size:17px;color:#475569;margin-top:4px;font-weight:600'>{t}</div></div>" for d, t, ic, c in marcos)}</div>
</div>""")

IMG["hub-organizar"] = (1200, 560, "cl", f"""
<div class='tc'><span class='selo'>Hub de Sistemas</span><h2 style='margin-top:12px'>Organize os seus sistemas do seu jeito</h2></div>
<div class='c' style='margin-top:24px;padding:20px 24px'>
 <div style='display:flex;justify-content:space-between;align-items:center'>
  <div style='display:flex;gap:8px'><span class='pill in'>Todos os sistemas</span><span class='pill cz'>{i('star')} Favoritos</span><span class='pill cz'>{i('clock-counter-clockwise')} Acessados recentemente</span></div>
  <div style='border:1px solid #cbd5e1;border-radius:10px;padding:8px 14px;font-size:15px;color:#334155'>Ordenar por: <b>Online primeiro</b> ▾</div>
 </div>
 <div class='grid' style='grid-template-columns:repeat(3,1fr);margin-top:18px;gap:14px'>
  {''.join(f"<div style='border:1px solid #e2e8f0;border-radius:14px;padding:16px;position:relative'><span style='position:absolute;right:14px;top:12px;font-size:22px;color:{'#f59e0b' if k < 2 else '#cbd5e1'}'>{i('star')}</span><span class='ic' style='width:44px;height:44px;border-radius:12px;background:{SIS[n][3]};color:{SIS[n][2]};font-size:22px'>{i(SIS[n][1])}</span><div style='font-weight:850;font-size:17px;margin-top:10px'>{SIS[n][0]}</div><div style='margin-top:6px'><span class='pill ok' style='font-size:12px;padding:3px 9px'>Online</span></div></div>" for k, n in enumerate((3, 1, 4)))}
 </div>
</div>
<div style='display:grid;grid-template-columns:repeat(3,1fr);gap:18px;margin-top:22px;font-size:17px;font-weight:700;color:#334155'>
 <div style='display:flex;gap:10px;align-items:center'><span class='num'>1</span>Troque de aba para ver favoritos e recentes</div>
 <div style='display:flex;gap:10px;align-items:center'><span class='num'>2</span>Ordene por nome, online ou manutenção</div>
 <div style='display:flex;gap:10px;align-items:center'><span class='num'>3</span>Clique na estrela para favoritar</div>
</div>
<div class='rod'>Favoritos e acessos recentes ficam guardados neste navegador.</div>""")

IMG["manutencao"] = (1200, 430, "cl", f"""
<div class='tc'><span class='selo'>Manutenção</span><h2 style='margin-top:12px'>Quando um sistema está em manutenção</h2></div>
<div style='display:grid;grid-template-columns:1fr 1fr;gap:30px;margin-top:28px'>
 <div class='c' style='padding:22px'><div style='display:flex;gap:12px;align-items:center'><span class='ic' style='width:50px;height:50px;border-radius:13px;background:#dbeafe;color:#1d4ed8;font-size:25px'>{i('airplane-tilt')}</span><div style='flex:1;font-size:20px;font-weight:850'>Luft-ConnectAir</div><span class='pill ok'>Online</span></div><div style='margin-top:16px;background:#2563eb;color:#fff;border-radius:11px;padding:12px;text-align:center;font-weight:800;font-size:16px'>Abrir sistema {i('arrow-right')}</div><div style='margin-top:12px;font-size:16px;color:#475569;text-align:center'>Funcionando normalmente</div></div>
 <div class='c' style='padding:22px;background:#f1f5f9'><div style='display:flex;gap:12px;align-items:center;opacity:.65'><span class='ic' style='width:50px;height:50px;border-radius:13px;background:#fef3c7;color:#b45309;font-size:25px'>{i('cpu')}</span><div style='flex:1;font-size:20px;font-weight:850'>Luft-Control</div><span class='pill av'>{i('wrench')} Indisponível</span></div><div style='margin-top:16px;background:#cbd5e1;color:#64748b;border-radius:11px;padding:12px;text-align:center;font-weight:800;font-size:16px'>{i('lock-simple')} Em manutenção</div><div style='margin-top:12px;font-size:16px;color:#475569;text-align:center'>Não abre enquanto a manutenção durar</div></div>
</div>""")

passos_acesso = [("user-gear", "O responsável libera", "O gestor ou o TI concede a permissão de acesso no Painel de Controle."), ("bell-ringing", "Você é avisado", "Chega uma notificação no sino e, se o envio estiver configurado, um e-mail."), ("squares-four", "O cartão aparece", "O sistema passa a aparecer no seu Hub e no menu lateral."), ("arrow-square-out", "Abra e use", "Clique em Abrir sistema. Sem digitar a senha de novo.")]
IMG["acesso-liberado"] = (1200, 470, "cl", f"""
<div class='tc'><span class='selo'>Acessos</span><h2 style='margin-top:12px'>Como o seu acesso chega até você</h2></div>
<div style='display:grid;grid-template-columns:1fr 36px 1fr 36px 1fr 36px 1fr;gap:6px;margin-top:30px;align-items:stretch'>
{''.join(f"<div class='c' style='padding:20px;text-align:center'><span class='ic' style='width:62px;height:62px;background:#dbeafe;color:#1d4ed8;font-size:30px'>{i(ic)}</span><div style='font-size:20px;font-weight:850;margin-top:12px'>{t}</div><div style='font-size:15px;color:#475569;margin-top:8px;line-height:1.4'>{d}</div></div>" + (f"<div class='seta' style='font-size:26px'>{i('caret-right')}</div>" if k < 3 else "") for k, (ic, t, d) in enumerate(passos_acesso))}
</div>
<div class='rod'>Só avisa quando você passa de "sem acesso" para "com acesso".</div>""")

cards_prot = [("timer", "Sessão com prazo", "Sem atividade por um tempo, a sessão expira e você entra de novo. O que não foi salvo se perde."), ("sign-out", "Sair em um, sair em todos", "Use o botão Sair do menu lateral. A sessão é encerrada em todos os sistemas."), ("devices", "Veja onde está conectado", "No perfil: navegador, sistema, IP e última atividade, mais os 5 últimos acessos."), ("shield-warning", "Acesso bloqueado", "Se um administrador bloquear a conta, as sessões caem e a entrada é recusada.")]
IMG["protecao-conta"] = (1200, 520, "cl", f"""
<div class='tc'><span class='selo'>Segurança</span><h2 style='margin-top:12px'>A sua conta, protegida e à vista</h2></div>
<div class='grid' style='grid-template-columns:1fr 1fr;margin-top:26px'>
{''.join(f"<div class='c' style='padding:22px;display:flex;gap:18px;align-items:flex-start'><span class='ic' style='width:60px;height:60px;background:#e0e7ff;color:#4338ca;font-size:30px;flex:0 0 auto'>{i(ic)}</span><div><div style='font-size:21px;font-weight:850'>{t}</div><div style='font-size:16px;color:#475569;margin-top:6px;line-height:1.45'>{d}</div></div></div>" for ic, t, d in cards_prot)}
</div>""")

ICONE_X = i("x", 'style="font-size:16px;color:#94a3b8"')
IMG["notificacoes-limpar"] = (1200, 470, "cl", f"""
<div class='tc'><span class='selo'>Notificações</span><h2 style='margin-top:12px'>Limpe a sua lista, sem apagar para os outros</h2></div>
<div style='display:grid;grid-template-columns:1.25fr 1fr;gap:34px;margin-top:26px;align-items:start'>
 <div class='c' style='overflow:hidden'>
  <div style='display:flex;justify-content:space-between;align-items:center;padding:14px 20px;border-bottom:1px solid #e2e8f0'><b style='font-size:19px'>{i('bell')} Notificações</b><span style='border:1px solid #cbd5e1;border-radius:9px;padding:6px 12px;font-size:14px;font-weight:700'>{i('broom')} Limpar ▾</span></div>
  {''.join(f"<div style='display:flex;gap:14px;padding:14px 20px;border-bottom:1px solid #f1f5f9;{'background:#eff6ff' if novo else ''}'><span class='ic' style='width:40px;height:40px;border-radius:50%;background:{cor};color:#fff;font-size:19px'>{i(ic)}</span><div style='flex:1'><div style='font-weight:{900 if novo else 700};font-size:16px'>{t}</div><div style='font-size:14px;color:#64748b;margin-top:2px'>{d}</div></div>{ICONE_X}</div>" for ic, cor, t, d, novo in [("key", "#059669", "Acesso liberado ao Luft-Control", "Abrir Luft-Control", True), ("megaphone-simple", "#2563eb", "Manutenção programada", "Sexta-feira, das 22h às 23h", True), ("rocket-launch", "#7c3aed", "Uma base nova para os sistemas Luft", "Nota de atualização 2.2.0", False)])}
 </div>
 <div style='display:grid;gap:16px'>
  <div class='c' style='padding:8px'><div style='padding:11px 14px;font-weight:700;font-size:16px'>{i('check')} Limpar as lidas</div><div style='padding:11px 14px;font-weight:700;font-size:16px;background:#f1f5f9;border-radius:10px'>{i('broom')} Limpar todas</div></div>
  <div style='background:#0f172a;color:#fff;border-radius:14px;padding:16px 20px;display:flex;justify-content:space-between;align-items:center;font-size:16px'><span>{i('check-circle')} 3 notificações limpas</span><b style='color:#93c5fd'>Desfazer · 8 s</b></div>
  <div style='font-size:16px;color:#475569;line-height:1.5'>Limpar tira da <b>sua</b> lista e do contador do sino. A notificação continua existindo para as demais pessoas.</div>
 </div>
</div>""")

abas = [("squares-four", "Visão Geral", "Atalhos para o que você pode usar"), ("shield-check", "Segurança & Permissões", "Acessos, grupos, bloqueios e módulos"), ("app-window", "Aplicações & Ambiente", "Catálogo de sistemas, manutenção e serviços"), ("megaphone-simple", "Comunicação", "Comunicados e notas de atualização"), ("chart-line-up", "Auditoria & Análise", "Quem acessou, desempenho e sessões"), ("gear-six", "Configurações Gerais", "Parâmetros que o sistema declara")]
IMG["painel-controle"] = (1200, 560, "cl", f"""
<div class='tc'><span class='selo'>Para quem administra</span><h2 style='margin-top:12px'>O Painel de Controle em seis abas</h2></div>
<div class='grid' style='grid-template-columns:repeat(3,1fr);margin-top:26px'>{''.join(f"<div class='c' style='padding:22px'><span class='ic' style='width:54px;height:54px;background:#dbeafe;color:#1d4ed8;font-size:27px'>{i(ic)}</span><div style='font-size:20px;font-weight:850;margin-top:12px'>{t}</div><div style='font-size:15px;color:#475569;margin-top:6px;line-height:1.4'>{d}</div></div>" for ic, t, d in abas)}</div>
<div class='rod'>Cada aba só aparece para quem tem a permissão correspondente.</div>""")

IMG["busca-atalho"] = (1200, 440, "cl", f"""
<div class='tc'><span class='selo'>Busca global</span><h2 style='margin-top:12px'>Ache qualquer tela em segundos</h2></div>
<div class='c' style='margin:26px auto 0;max-width:820px;overflow:hidden'>
 <div style='display:flex;align-items:center;gap:12px;padding:16px 22px;border-bottom:1px solid #e2e8f0;font-size:20px'>{i('magnifying-glass')}<span>perm</span><span style='margin-left:auto;border:2px solid #cbd5e1;border-bottom-width:4px;border-radius:8px;padding:2px 10px;font-size:14px;font-weight:800;color:#475569'>Ctrl K</span></div>
 {''.join(f"<div style='display:flex;gap:14px;align-items:center;padding:13px 22px;{'background:#dbeafe;' if k == 0 else ''}font-size:18px'><span style='font-size:22px;color:#2563eb'>{i(ic)}</span><div><b>{t}</b><div style='font-size:13px;color:#64748b'>{d}</div></div></div>" for k, (ic, t, d) in enumerate([("shield-check", "Segurança & Permissões", "Painel de Controle"), ("users-three", "Por Grupos Corporativos", "Painel de Controle"), ("user-plus", "Espelhar Permissões", "Painel de Controle")]))}
</div>
<div style='display:flex;gap:26px;justify-content:center;margin-top:22px;font-size:17px;font-weight:700;color:#334155'><span>↑ ↓ navegam</span><span>Enter abre</span><span>Esc fecha</span></div>""")

IMG["temas-tres"] = (1200, 460, "cl", f"""
<div class='tc'><span class='selo'>Aparência</span><h2 style='margin-top:12px'>Escolha o visual que cansa menos os olhos</h2></div>
<div class='grid' style='grid-template-columns:repeat(3,1fr);margin-top:26px'>
{''.join(f"<div style='border-radius:18px;overflow:hidden;border:1px solid #cbd5e1;box-shadow:0 14px 34px rgba(15,23,42,.12)'><div style='background:{bg};padding:16px'><div style='display:flex;gap:6px'><i style='width:11px;height:11px;border-radius:50%;background:#f87171;display:block'></i><i style='width:11px;height:11px;border-radius:50%;background:#fbbf24;display:block'></i><i style='width:11px;height:11px;border-radius:50%;background:#34d399;display:block'></i></div><div style='background:{pn};border-radius:12px;padding:14px;margin-top:12px'><div style='height:14px;width:60%;border-radius:7px;background:{tx};opacity:.85'></div><div style='height:10px;width:85%;border-radius:5px;background:{tx};opacity:.35;margin-top:10px'></div><div style='height:34px;width:46%;border-radius:9px;background:{ac};margin-top:14px'></div></div></div><div style='background:#fff;padding:12px 16px;font-weight:850;font-size:19px;display:flex;justify-content:space-between'>{nome}<span style='font-size:14px;color:#64748b;font-weight:600'>{leg}</span></div></div>" for nome, leg, bg, pn, tx, ac in [("Claro", "padrão", "#e2e8f0", "#ffffff", "#0f172a", "#2563eb"), ("Escuro", "descansa a vista", "#0f172a", "#1e293b", "#f8fafc", "#3b82f6"), ("Luft ESG", "identidade verde", "#e6f0e4", "#ffffff", "#14532d", "#16a34a")])}
</div>
<div class='rod'>A escolha fica salva na sua conta e vale em todos os sistemas.</div>""")

IMG["ajuda-chamado"] = (1200, 440, "es", f"""
<div style='display:grid;grid-template-columns:1fr 1.15fr;gap:40px;align-items:center;height:100%'>
 <div><span class='selo'>Suporte</span><h1 style='font-size:46px;margin-top:16px'>Algo não saiu como esperado?</h1><p class='sub'>Abra um chamado pelo botão <b>Suporte</b> do Hub e conte o essencial.</p></div>
 <div style='display:grid;gap:12px'>{''.join(f"<div style='display:flex;gap:14px;align-items:center;background:rgba(255,255,255,.16);border-radius:16px;padding:14px 18px;font-size:19px;font-weight:700'><span style='font-size:28px'>{i(ic)}</span>{t}</div>" for ic, t in [("app-window", "Em qual sistema e em qual tela"), ("cursor-click", "O que você estava fazendo"), ("clock", "O horário aproximado"), ("image-square", "Uma captura de tela ajuda"), ("prohibit", "Nunca envie a sua senha")])}</div>
</div>""")

def gerar() -> None:
    if CHROME is None:
        raise SystemExit("Chrome/Edge nao encontrado.")
    SAIDA.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for nome, (largura, altura, classe, corpo) in IMG.items():
            if SO and nome not in SO:
                continue
            arquivo = Path(tmp) / f"{nome}.html"
            arquivo.write_text(pagina(corpo, classe), encoding="utf-8")
            destino = SAIDA / f"{nome}.png"
            subprocess.run(
                [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
                 f"--window-size={largura},{altura}", "--virtual-time-budget=8000", f"--screenshot={destino}", arquivo.as_uri()],
                check=True, capture_output=True, timeout=90,
            )
            print(f"{nome}.png  {destino.stat().st_size // 1024} KB")


if __name__ == "__main__":
    gerar()
