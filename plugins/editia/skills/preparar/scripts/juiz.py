"""EDIT.IA — juiz do setup da Aula 1.

O juiz é quem decide se a máquina está pronta. Ele verifica os quatro estados do contrato
e grava o veredito em ~/EDITIA/estado/estado.json. O Claude não aprova nada: só corrige e
pede ao juiz para verificar de novo.

  E1  Claude funcionando
  E2  Base técnica: ffmpeg/ffprobe + Python (uv) + Node/npm
  E3  Watch-skill: motor com transcrição e OCR + MCP no Claude + teste real pelo MCP
  E4  Remotion: render real de um MP4 simples

Uso (sempre pelo editia.sh, que garante o uv):
  verificar [--estado E1|E2|E3|E4]
  instalar <uv|ffmpeg|node|deno|watchskill|ytdlp|mcp|remotion>

Só usa a biblioteca padrão do Python: roda igual no macOS e no Windows.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unicodedata
import uuid
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

SO = os.environ.get("EDITIA_SO") or ("macos" if sys.platform == "darwin" else "windows" if os.name == "nt" else "outro")
CONFIG = Path(os.environ.get("EDITIA_CONFIG") or Path(__file__).resolve().parent.parent / "config")
SCRIPTS = Path(os.environ.get("EDITIA_SCRIPTS") or Path(__file__).resolve().parent)
MODELO_REMOTION = SCRIPTS.parent / "modelo_remotion"
VERSOES = json.loads((CONFIG / "versoes.json").read_text(encoding="utf-8"))
ROTAS = json.loads((CONFIG / "rotas.json").read_text(encoding="utf-8"))

TRABALHO = Path.home() / "EDITIA"
ESTADO_DIR = TRABALHO / "estado"
ESTADO = ESTADO_DIR / "estado.json"
LOG = ESTADO_DIR / "ultimo_log.txt"
MOTOR = TRABALHO / "motor"
TESTE = TRABALHO / "teste"
WS_BIN_ISOLADO = TRABALHO / "watch-skill-bin"
EXE = ".exe" if SO == "windows" else ""
NOME_MCP = VERSOES["watch_skill"]["nome_mcp"]

ORDEM = ["E1", "E2", "E4", "E3"]  # o E3 usa o clipe que o E4 renderiza
TITULOS = {"E1": "Claude", "E2": "Base técnica", "E3": "Watch-skill", "E4": "Remotion"}


# ---------------------------------------------------------------- utilidades

def log(texto: str) -> None:
    ESTADO_DIR.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(texto.rstrip() + "\n")


def rodar(cmd: list[str], timeout: int = 600, env: dict | None = None, cwd: Path | None = None,
          completo: bool = False) -> tuple[int, str]:
    """Executa um comando e devolve (código, saída). Por padrão, só as últimas 40 linhas. Nunca levanta exceção."""
    log(f"$ {' '.join(map(str, cmd))}")
    try:
        p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, env=env, cwd=str(cwd) if cwd else None)
        saida = (p.stdout or "") + (p.stderr or "")
        codigo = p.returncode
    except FileNotFoundError as e:
        saida, codigo = f"comando não encontrado: {e}", 127
    except subprocess.TimeoutExpired:
        saida, codigo = f"tempo esgotado ({timeout}s)", 124
    except Exception as e:  # noqa: BLE001 — o juiz precisa reportar, nunca quebrar
        saida, codigo = f"{type(e).__name__}: {e}", 1
    log(saida[-4000:])
    if completo:
        return codigo, saida
    return codigo, "\n".join(saida.strip().splitlines()[-40:])


def atualizar_path() -> None:
    """Inclui no PATH deste processo os lugares onde as rotas instalam programas.

    No Windows, o app Claude aberto não enxerga o PATH novo de quem acabou de ser instalado:
    lemos o PATH gravado no registro e os diretórios conhecidos do winget/Node/uv.
    """
    extras: list[str] = [str(Path.home() / ".local" / "bin")]
    if SO == "macos":
        extras += ["/opt/homebrew/bin", "/usr/local/bin"]
    elif SO == "windows":
        try:
            import winreg  # type: ignore

            for raiz, chave in ((winreg.HKEY_CURRENT_USER, r"Environment"),
                                (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment")):
                try:
                    with winreg.OpenKey(raiz, chave) as k:
                        valor, _ = winreg.QueryValueEx(k, "Path")
                        extras += [os.path.expandvars(p) for p in valor.split(";") if p]
                except OSError:
                    pass
        except ImportError:
            pass
        local = os.environ.get("LOCALAPPDATA", "")
        extras += [rf"{local}\Microsoft\WinGet\Links", r"C:\Program Files\nodejs", str(Path.home() / ".deno" / "bin")]
    atual = os.environ.get("PATH", "").split(os.pathsep)
    for p in extras:
        if p and p not in atual:
            atual.append(p)
    os.environ["PATH"] = os.pathsep.join(atual)


def achar(nome: str) -> str | None:
    return shutil.which(nome)


def normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]", " ", sem_acento.lower())


def item(estado: str, chave: str, nome: str, ok: bool | None, detalhe: str = "", evidencia: str = "",
         correcao: str | None = None, humano: str | None = None, bloqueia: bool = True,
         aguardando: dict | None = None) -> dict:
    return {"estado": estado, "item": chave, "nome": nome, "ok": ok, "detalhe": detalhe,
            "evidencia": evidencia, "correcao": correcao, "humano": humano, "bloqueia": bloqueia,
            "aguardando_claude": aguardando}


def ler_estado() -> dict:
    try:
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    except Exception:
        return {}


def gravar_estado(dados: dict) -> None:
    ESTADO_DIR.mkdir(parents=True, exist_ok=True)
    tmp = ESTADO.with_suffix(".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, ESTADO)


def claude_exe() -> str | None:
    p = os.environ.get("CLAUDE_CODE_EXECPATH")
    return p if p and Path(p).exists() else None


# ---------------------------------------------------------------- E1 · Claude

def verificar_e1() -> list[dict]:
    dentro = os.environ.get("CLAUDECODE") == "1"
    exe = claude_exe()
    if dentro and exe:
        return [item("E1", "claude", "Claude Code", True, "ativo, executando comandos")]
    return [item("E1", "claude", "Claude Code", False, "o setup não está rodando dentro do Claude Code",
                 evidencia=f"CLAUDECODE={os.environ.get('CLAUDECODE')} CLAUDE_CODE_EXECPATH={exe}",
                 humano="Abra o app Claude, entre na aba Code e peça: prepare meu computador para editar.")]


# ---------------------------------------------------------------- E2 · Base técnica

def verificar_ffmpeg() -> dict:
    ff, fp = achar("ffmpeg"), achar("ffprobe")
    if not ff or not fp:
        return item("E2", "ffmpeg", "ffmpeg / ffprobe", False, "não encontrado",
                    evidencia=f"ffmpeg={ff} ffprobe={fp}", correcao="ffmpeg")
    TESTE.mkdir(parents=True, exist_ok=True)
    saida = TESTE / "ffmpeg_teste.mp4"
    c, o = rodar([ff, "-hide_banner", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=30",
                  "-f", "lavfi", "-i", "sine=frequency=440", "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                  "-c:a", "aac", str(saida)], timeout=120)
    if c != 0:
        return item("E2", "ffmpeg", "ffmpeg / ffprobe", False, "não conseguiu gerar vídeo H.264", evidencia=o,
                    correcao="ffmpeg")
    c, o = rodar([fp, "-v", "error", "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(saida)], timeout=60)
    codecs = set(o.split())
    if c != 0 or not {"h264", "aac"} <= codecs:
        return item("E2", "ffmpeg", "ffmpeg / ffprobe", False, "ffprobe não leu o vídeo gerado", evidencia=o,
                    correcao="ffmpeg")
    _, v = rodar([ff, "-version"], timeout=30)
    versao = (re.search(r"ffmpeg version (\S+)", v) or [None, "?"])[1]
    detalhe = f"{versao} · gerou e leu vídeo H.264 + AAC"
    if SO == "macos":
        _, arq = rodar(["file", "-L", ff], timeout=30)
        maquina = platform.machine()
        if maquina == "arm64" and "arm64" not in arq:
            detalhe += " · aviso: binário Intel rodando via Rosetta"
    return item("E2", "ffmpeg", "ffmpeg / ffprobe", True, detalhe)


def verificar_python() -> dict:
    uv = os.environ.get("EDITIA_UV") or achar("uv")
    _, v = rodar([uv, "--version"], timeout=30) if uv else (1, "")
    py = ".".join(map(str, sys.version_info[:3]))
    if sys.version_info >= (3, 11) and uv:
        return item("E2", "python", "Python (uv)", True, f"{v.split()[1] if v else '?'} · Python {py}")
    return item("E2", "python", "Python (uv)", False, f"Python {py}", evidencia=f"uv={uv}", correcao="uv")


def verificar_node() -> dict:
    node, npm = achar("node"), achar("npm")
    if not node or not npm:
        return item("E2", "node", "Node / npm", False, "não encontrado", evidencia=f"node={node} npm={npm}",
                    correcao="node")
    _, v = rodar([node, "-v"], timeout=30)
    c, soma = rodar([node, "-e", "console.log(40+2)"], timeout=30)
    _, vn = rodar([npm, "-v"], timeout=60)
    m = re.match(r"v(\d+)", v.strip())
    maior = int(m.group(1)) if m else 0
    if c != 0 or soma.strip() != "42":
        return item("E2", "node", "Node / npm", False, "o Node não executou código", evidencia=soma, correcao="node")
    if maior < VERSOES["node_minimo"]:
        return item("E2", "node", "Node / npm", False, f"Node {v.strip()} é antigo (mínimo {VERSOES['node_minimo']})",
                    evidencia=v, correcao="node")
    return item("E2", "node", "Node / npm", True, f"{v.strip()} / npm {vn.strip().splitlines()[-1]}")


def verificar_e2() -> list[dict]:
    return [verificar_ffmpeg(), verificar_python(), verificar_node()]


# ---------------------------------------------------------------- E4 · Remotion

def gerar_voz(destino: Path) -> tuple[bool, bool, str]:
    """Gera a fala do clipe com a voz do próprio sistema. Devolve (ok, voz_em_portugues, evidência)."""
    frase = VERSOES["teste"]["frase"]
    ff = achar("ffmpeg")
    destino.parent.mkdir(parents=True, exist_ok=True)
    bruto = destino.with_suffix(".aiff" if SO == "macos" else ".bruto.wav")
    em_pt = False
    if SO == "macos":
        _, vozes = rodar(["say", "-v", "?"], timeout=30, completo=True)
        # nome completo da voz: "Luciana" ou "Eddy (Português (Brasil))" (nomes curtos se repetem em várias línguas)
        pt = [m.group(1).strip() for m in (re.match(r"^(.+?)\s+pt_BR\s", ln) for ln in vozes.splitlines()) if m]
        voz = "Luciana" if "Luciana" in pt else (pt[0] if pt else None)
        em_pt = voz is not None
        c, o = rodar(["say"] + (["-v", voz] if voz else []) + ["-o", str(bruto), frase], timeout=60)
    elif SO == "windows":
        ps = ("Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
              "$v = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -eq 'pt-BR' } | Select-Object -First 1; "
              "if ($v) { $s.SelectVoice($v.VoiceInfo.Name); Write-Output 'PT' } else { Write-Output 'OUTRA' }; "
              f"$s.SetOutputToWaveFile('{bruto}'); $s.Speak('{frase}'); $s.Dispose()")
        c, o = rodar(["powershell", "-NoProfile", "-Command", ps], timeout=120)
        em_pt = "PT" in o
    else:
        return False, False, "sistema sem síntese de voz conhecida"
    if c != 0 or not bruto.exists():
        return False, False, o
    c, o = rodar([ff, "-v", "error", "-y", "-i", str(bruto), "-ar", "48000", "-ac", "1", str(destino)], timeout=60)
    bruto.unlink(missing_ok=True)
    return c == 0, em_pt, o


def verificar_e4(anteriores: dict) -> list[dict]:
    if not (anteriores.get("ffmpeg") and anteriores.get("node")):
        return [item("E4", "remotion", "Remotion", None, "aguardando a base técnica (ffmpeg e Node)",
                     evidencia="E2 incompleto")]
    modelo = [MODELO_REMOTION / "package.json"] + sorted((MODELO_REMOTION / "src").glob("*"))
    pacote_ok = all((MOTOR / m.relative_to(MODELO_REMOTION)).exists() and
                    (MOTOR / m.relative_to(MODELO_REMOTION)).read_bytes() == m.read_bytes() for m in modelo)
    instalado = (MOTOR / "node_modules" / "remotion").exists() and (MOTOR / "node_modules" / "@remotion" / "cli").exists()
    navegador = (MOTOR / "node_modules" / ".remotion" / "chrome-headless-shell").exists()
    if not (pacote_ok and instalado and navegador):
        falta = [n for n, ok in (("projeto", pacote_ok), ("pacotes", instalado), ("navegador", navegador)) if not ok]
        return [item("E4", "remotion", "Remotion", False, "instalação incompleta: falta " + ", ".join(falta),
                     evidencia=str(MOTOR), correcao="remotion")]
    voz = MOTOR / "public" / "voz.wav"
    estado = ler_estado()
    voz_pt = estado.get("voz_em_portugues", False)
    if not voz.exists():
        ok, voz_pt, ev = gerar_voz(voz)
        if not ok:
            return [item("E4", "remotion", "Remotion", False, "não conseguiu gerar a fala do clipe de teste", evidencia=ev)]
    saida = TESTE / "editia_teste.mp4"
    # impressão digital do que entra no render: só renderiza de novo se algo mudou
    import hashlib
    digital = hashlib.sha256(b"".join(p.read_bytes() for p in modelo + [voz])).hexdigest()[:16]
    if saida.exists() and estado.get("render_digital") == digital and estado.get("render_quadros"):
        return validar_mp4(saida, estado["render_quadros"], "já renderizado nesta máquina, revalidado")
    saida.unlink(missing_ok=True)
    npx = achar("npx")
    comp = VERSOES["remotion"]["composicao"]
    inicio = time.time()
    rv = VERSOES["remotion"]
    _, dur = rodar([achar("ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(voz)], timeout=60)
    try:
        quadros_esperados = int((float(dur.strip()) + rv["folga_segundos"]) * rv["fps"])
    except ValueError:
        return [item("E4", "remotion", "Remotion", False, "não conseguiu medir a fala do clipe de teste", evidencia=dur)]
    props = json.dumps({"quadros": quadros_esperados})
    c, o = rodar([npx, "remotion", "render", "src/index.jsx", comp, str(saida), "--codec=h264", f"--props={props}"],
                 timeout=1800, cwd=MOTOR)
    duracao = time.time() - inicio
    if c != 0 or not saida.exists():
        return [item("E4", "remotion", "Remotion", False, "o render falhou", evidencia=o)]
    resultado = validar_mp4(saida, quadros_esperados, f"renderizado em {duracao:.0f}s")
    if resultado[0]["ok"]:
        estado["voz_em_portugues"] = voz_pt
        estado["render_digital"], estado["render_quadros"] = digital, quadros_esperados
        # clipe novo → amostra nova para o teste da watch-skill (nunca aprovar com um clipe antigo)
        for velha in TESTE.glob("amostra_*.mp4"):
            velha.unlink(missing_ok=True)
        estado.pop("amostra_e3", None)
        gravar_estado(estado)
    return resultado


def validar_mp4(saida: Path, quadros_esperados: int, como: str) -> list[dict]:
    rv = VERSOES["remotion"]
    fp = achar("ffprobe")
    _, info = rodar([fp, "-v", "error", "-count_frames", "-show_entries",
                     "stream=codec_type,codec_name,width,height,nb_read_frames", "-of", "json", str(saida)], timeout=120,
                    completo=True)
    try:
        streams = json.loads(info)["streams"]
    except Exception:
        return [item("E4", "remotion", "Remotion", False, "ffprobe não leu o MP4 gerado", evidencia=info)]
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    quadros = int(video.get("nb_read_frames") or 0)
    problemas = []
    if video.get("codec_name") != "h264":
        problemas.append(f"codec {video.get('codec_name')}")
    if (video.get("width"), video.get("height")) != (rv["largura"], rv["altura"]):
        problemas.append(f"tamanho {video.get('width')}x{video.get('height')}")
    if abs(quadros - quadros_esperados) > 1:
        problemas.append(f"{quadros} quadros")
    if not audio:
        problemas.append("sem áudio")
    if problemas:
        return [item("E4", "remotion", "Remotion", False, "MP4 inválido: " + ", ".join(problemas), evidencia=info)]
    return [item("E4", "remotion", "Remotion", True, f"{quadros} quadros, {como} · MP4 válido ({saida})")]


# ---------------------------------------------------------------- E3 · Watch-skill

def mcp_info() -> dict:
    """Lê do próprio Claude Code como o MCP da watch-skill está registrado e se conecta."""
    exe = claude_exe()
    if not exe:
        return {"existe": False, "evidencia": "CLAUDE_CODE_EXECPATH ausente"}
    c, o = rodar([exe, "mcp", "get", NOME_MCP], timeout=120, completo=True)
    if c != 0 or "Status:" not in o:
        return {"existe": False, "evidencia": o}
    info = {"existe": True, "evidencia": o, "conectado": "Connected" in o or "✔" in o.split("Status:")[1].splitlines()[0],
            "env": {}}
    m = re.search(r"Command:\s*(.+)", o)
    info["comando"] = m.group(1).strip() if m else ""
    m = re.search(r"Args:\s*(.*)", o)
    info["args"] = m.group(1).strip() if m else ""
    em_env = False
    for ln in o.splitlines():
        if ln.strip().startswith("Environment:"):
            em_env = True
            continue
        if em_env:
            if "=" in ln and ln.startswith("    "):
                k, v = ln.strip().split("=", 1)
                info["env"][k] = v
            elif ln.strip():
                em_env = False
    return info


def exe_watchskill(info: dict) -> str | None:
    """Descobre qual executável da watch-skill o MCP usa (sem rodar `uv run`, que sincronizaria pacotes)."""
    cmd, args = info.get("comando", ""), info.get("args", "")
    if Path(cmd).name.startswith("watch-skill"):
        return cmd if Path(cmd).exists() else achar(cmd)
    m = re.search(r"--directory\s+(\S+)", args)
    if Path(cmd).name.startswith("uv") and m:
        pasta = Path(m.group(1)) / ".venv"
        for p in (pasta / "bin" / "watch-skill", pasta / "Scripts" / "watch-skill.exe"):
            if p.exists():
                return str(p)
    uv = os.environ.get("EDITIA_UV")
    if uv:
        c, o = rodar([uv, "tool", "dir", "--bin"], timeout=30)
        p = Path(o.strip().splitlines()[-1]) / f"watch-skill{EXE}" if c == 0 and o.strip() else None
        if p and p.exists():
            return str(p)
    return achar("watch-skill")


def consultar_indice(dados_dir: Path, nome_arquivo: str) -> dict | None:
    """Lê o índice da watch-skill (cópia temporária, nunca o original) e devolve o registro do clipe."""
    banco = dados_dir / "index.db"
    if not banco.exists():
        return None
    with tempfile.TemporaryDirectory() as tmp:
        for sufixo in ("", "-wal", "-shm"):
            origem = Path(str(banco) + sufixo)
            if origem.exists():
                shutil.copy2(origem, Path(tmp) / f"index.db{sufixo}")
        con = sqlite3.connect(Path(tmp) / "index.db")
        try:
            linha = con.execute("SELECT id, transcript_source FROM videos WHERE source LIKE ? "
                                "ORDER BY created_at DESC LIMIT 1", (f"%{nome_arquivo}",)).fetchone()
            if not linha:
                # conteúdo idêntico a um clipe já visto: a watch-skill grava o nome novo como apelido
                # (source_aliases). O apelido só existe se o Claude chamou a ferramenta com esse nome.
                try:
                    linha = con.execute("SELECT v.id, v.transcript_source FROM source_aliases a "
                                        "JOIN videos v ON v.revision_id = a.revision_id WHERE a.alias LIKE ? "
                                        "ORDER BY v.created_at DESC LIMIT 1", (f"%{nome_arquivo}",)).fetchone()
                except sqlite3.Error:
                    linha = None
            if not linha:
                return None
            vid, fonte = linha
            fala = " ".join(t for (t,) in con.execute("SELECT text FROM segments WHERE video_id=?", (vid,)) if t)
            tela = " ".join(t for (t,) in con.execute("SELECT text FROM ocr_blocks WHERE video_id=?", (vid,)) if t)
            return {"transcript_source": fonte, "fala": fala, "tela": tela}
        finally:
            con.close()


def verificar_ytdlp(dados_dir: Path) -> dict:
    candidatos = [dados_dir / "bin" / f"yt-dlp{EXE}", Path.home() / ".local" / "bin" / f"yt-dlp{EXE}"]
    ytdlp = next((str(p) for p in candidatos if p.exists()), None) or achar("yt-dlp")
    if not ytdlp:
        return item("E3", "links", "links (YouTube)", False, "yt-dlp não encontrado", correcao="ytdlp", bloqueia=False)
    env = dict(os.environ)
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")  # yt-dlp em zipapp exige Python ≥ 3.10
    c, o = rodar([ytdlp, "--simulate", "--no-warnings", "--print", "title", VERSOES["teste"]["link"]], timeout=120, env=env)
    if c == 0 and o.strip():
        return item("E3", "links", "links (YouTube)", True, f"leu \"{o.strip().splitlines()[-1][:40]}\"", bloqueia=False)
    _, versao = rodar([ytdlp, "--version"], timeout=30, env=env)
    if not versao.strip() or "Error" in versao:
        return item("E3", "links", "links (YouTube)", False, "yt-dlp não executa", evidencia=versao,
                    correcao="ytdlp", bloqueia=False)
    return item("E3", "links", "links (YouTube)", False, "indisponível agora (falha externa, não bloqueia)",
                evidencia=o, bloqueia=False)


def verificar_e3(anteriores: dict) -> list[dict]:
    itens: list[dict] = []
    info = mcp_info()
    exe = exe_watchskill(info) if info.get("existe") else (exe_watchskill({}) or None)
    # motor + módulos de transcrição e OCR
    if not exe:
        itens.append(item("E3", "motor", "motor + transcrição + OCR", False, "watch-skill não instalada",
                          correcao="watchskill"))
    else:
        _, ver = rodar([exe, "version"], timeout=60)
        _, doc = rodar([exe, "doctor", "--no-fix", "--json"], timeout=300, completo=True)
        try:
            checks = {c["name"]: c for c in json.loads(doc[doc.index("{"):])["checks"]}
            features = checks.get("features", {}).get("message", "")
        except Exception:
            features = ""
        faltando = [m for m in ("whisper", "ocr") if re.search(rf"(—|-)\s.*\b{m}:", features)]
        if not features:
            itens.append(item("E3", "motor", "motor + transcrição + OCR", False, "a watch-skill não respondeu ao diagnóstico",
                              evidencia=doc, correcao="watchskill"))
        elif faltando:
            itens.append(item("E3", "motor", "motor + transcrição + OCR", False, "faltam os módulos: " + ", ".join(faltando),
                              evidencia=features, correcao="watchskill"))
        else:
            itens.append(item("E3", "motor", "motor + transcrição + OCR", True, ver.strip().splitlines()[-1] if ver.strip() else ""))
    # MCP registrado e conectado
    if not info.get("existe"):
        itens.append(item("E3", "mcp", "MCP no Claude", False, "watch-skill não está registrada no Claude Code",
                          evidencia=info.get("evidencia", "")[-600:], correcao="mcp"))
    elif not info.get("conectado"):
        itens.append(item("E3", "mcp", "MCP no Claude", False, "registrada, mas não conecta",
                          evidencia=info.get("evidencia", "")[-600:], correcao="mcp"))
    else:
        itens.append(item("E3", "mcp", "MCP no Claude", True, "conectado"))
    # teste real: o Claude analisa o clipe do E4 pelo MCP; o juiz confere no índice
    clipe = TESTE / "editia_teste.mp4"
    dados_dir = Path(info.get("env", {}).get("WATCHSKILL_DATA_DIR") or Path.home() / ".watch-skill")
    pronto_para_teste = all(i["ok"] for i in itens) and anteriores.get("remotion") and clipe.exists()
    if not pronto_para_teste:
        itens.append(item("E3", "teste_mcp", "transcrição + OCR pelo Claude", None,
                          "aguardando motor, MCP e o clipe do Remotion"))
    else:
        estado = ler_estado()
        amostra = Path(estado.get("amostra_e3", ""))
        if not estado.get("amostra_e3") or not amostra.exists():
            amostra = TESTE / f"amostra_{uuid.uuid4().hex[:8]}.mp4"
            shutil.copy2(clipe, amostra)
            estado["amostra_e3"] = str(amostra)
            gravar_estado(estado)
        reg = consultar_indice(dados_dir, amostra.name)
        if reg is None:
            itens.append(item("E3", "teste_mcp", "transcrição + OCR pelo Claude", False,
                              "o Claude ainda precisa analisar o clipe de teste pela watch-skill",
                              aguardando={"ferramenta": f"mcp__{NOME_MCP}__watch_video", "source": str(amostra)}))
        else:
            fala, tela = normalizar(reg["fala"]), normalizar(reg["tela"]).replace(" ", "")
            chaves = VERSOES["teste"]["palavras_chave"]
            achadas = [k for k in chaves if k in fala.split()]
            voz_pt = estado.get("voz_em_portugues", True)
            fala_ok = reg["transcript_source"] not in (None, "", "none") and \
                (len(achadas) >= VERSOES["teste"]["minimo_palavras_chave"] if voz_pt else bool(fala.strip()))
            tela_ok = normalizar(VERSOES["teste"]["texto_na_tela"]).replace(" ", "") in tela
            if fala_ok and tela_ok:
                itens.append(item("E3", "teste_mcp", "transcrição + OCR pelo Claude", True,
                                  f"fala reconhecida ({', '.join(achadas) or 'texto presente'}) · \"{VERSOES['teste']['texto_na_tela']}\" lido na tela"))
            else:
                ev = f"transcript_source={reg['transcript_source']} · fala=\"{reg['fala'][:120]}\" · tela=\"{reg['tela'][:80]}\""
                itens.append(item("E3", "teste_mcp", "transcrição + OCR pelo Claude", False,
                                  ("transcrição falhou" if not fala_ok else "") + (" · OCR não leu o texto da tela" if not tela_ok else ""),
                                  evidencia=ev, correcao="watchskill" if reg["transcript_source"] in (None, "", "none") else None))
    itens.append(verificar_ytdlp(dados_dir))
    return itens


# ---------------------------------------------------------------- veredito

def verificar(somente: str | None) -> int:
    atualizar_path()
    ESTADO_DIR.mkdir(parents=True, exist_ok=True)
    LOG.write_text(f"EDIT.IA juiz · {time.strftime('%Y-%m-%d %H:%M:%S')} · {SO} {platform.machine()}\n", encoding="utf-8")
    estado = ler_estado()
    itens: dict[str, list[dict]] = estado.get("itens", {})
    for e in ORDEM:
        if somente and e != somente:
            continue
        aprovados = {i["item"]: i["ok"] for lst in itens.values() for i in lst}
        if e == "E1":
            itens[e] = verificar_e1()
        elif e == "E2":
            itens[e] = verificar_e2()
        elif e == "E4":
            itens[e] = verificar_e4(aprovados)
        elif e == "E3":
            itens[e] = verificar_e3(aprovados)
    bloqueantes = [i for e in ORDEM for i in itens.get(e, []) if i["bloqueia"]]
    completo = all(e in itens for e in ORDEM)
    pronto = completo and all(i["ok"] is True for i in bloqueantes)
    proximo = None
    if not pronto:
        for e in ORDEM:
            for i in itens.get(e, []):
                if i["bloqueia"] and i["ok"] is not True and (i["ok"] is False or i["aguardando_claude"]):
                    proximo = i
                    break
            if proximo:
                break
        if not proximo:
            proximo = next((i for e in ORDEM for i in itens.get(e, []) if i["bloqueia"] and i["ok"] is not True), None)
    estado = ler_estado()
    estado.update({"kit": VERSOES["kit"], "sistema": SO, "arquitetura": platform.machine(),
                   "atualizado_em": time.strftime("%Y-%m-%dT%H:%M:%S"),
                   "resultado": "PRONTO" if pronto else "NAO_PRONTO", "itens": itens})
    gravar_estado(estado)
    imprimir_checklist(itens, pronto)
    print("===EDITIA_JSON===")
    print(json.dumps({"resultado": estado["resultado"], "sistema": SO, "proximo": proximo,
                      "itens": itens, "log": str(LOG)}, ensure_ascii=False))
    return 0 if pronto else 1


def imprimir_checklist(itens: dict, pronto: bool) -> None:
    print("🟢 PRONTO PARA EDITAR" if pronto else "🔴 AINDA NÃO ESTÁ PRONTO")
    numeros = {"E1": "1", "E2": "2", "E3": "3", "E4": "4"}
    for e in ("E1", "E2", "E3", "E4"):
        print(f"{numeros[e]}. {TITULOS[e]}")
        for i in itens.get(e, []):
            simbolo = "✅" if i["ok"] else ("⚠️" if i["ok"] is False and not i["bloqueia"] else "⏳" if i["ok"] is None or i["aguardando_claude"] else "❌")
            print(f"   {i['nome']:.<34} {simbolo} {i['detalhe']}")


# ---------------------------------------------------------------- correções conhecidas

def comando_rota(chave: str, extras: dict) -> list[str] | None:
    rota = ROTAS.get(SO, {}).get(chave) or ROTAS["comum"].get(chave)
    if not rota:
        return None
    return [p.format(**extras) for p in rota]


def instalar(componente: str) -> int:
    atualizar_path()
    uv = os.environ.get("EDITIA_UV") or achar("uv") or ""
    extras = {"uv": uv, "pacote_watchskill": VERSOES["watch_skill"]["pacote"], "brew": "",
              "versoes_watchskill": "watchskill_versoes.txt"}  # relativo: o uv corta caminhos com espaço
    if componente in ("ffmpeg", "node", "deno"):
        if SO == "macos":
            brew = achar("brew")
            if not brew:
                print("EDITIA_HUMANO homebrew")
                print("O Mac precisa do Homebrew para instalar esta ferramenta. Ele pede a senha do computador, "
                      "então o aluno roda no Terminal:")
                print(ROTAS["macos"]["homebrew_humano"])
                return 2
            extras["brew"] = brew
        elif SO == "windows" and not achar("winget"):
            print("EDITIA_HUMANO winget")
            print("O Windows precisa do 'Instalador de Aplicativo' (winget). Abra a Microsoft Store, procure "
                  "'Instalador de Aplicativo', atualize e volte aqui.")
            return 2
        cmd = comando_rota(componente, extras)
        c, o = rodar(cmd, timeout=1800)
        print(o)
        return 0 if c == 0 else 1
    if componente in ("watchskill", "ytdlp"):
        c, o = rodar(comando_rota(componente, extras), timeout=1800, cwd=CONFIG)
        print(o)
        return 0 if c == 0 else 1
    if componente == "mcp":
        return instalar_mcp(uv)
    if componente == "remotion":
        return instalar_remotion()
    print(f"componente desconhecido: {componente}")
    return 1


def instalar_mcp(uv: str) -> int:
    exe = claude_exe()
    if not exe:
        print("CLAUDE_CODE_EXECPATH ausente: rode o setup de dentro do Claude Code.")
        return 1
    c, o = rodar([uv, "tool", "dir", "--bin"], timeout=30)
    ws = Path(o.strip().splitlines()[-1]) / f"watch-skill{EXE}" if c == 0 and o.strip() else None
    if not ws or not ws.exists():
        print("A watch-skill do EDIT.IA não está instalada. Rode antes: instalar watchskill")
        return 1
    config = Path.home() / ".claude.json"
    if config.exists():
        copia = ESTADO_DIR / "backups" / f"claude.json.{time.strftime('%Y%m%d-%H%M%S')}"
        copia.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(config, copia)
        print(f"backup da configuração do Claude: {copia}")
    for escopo in ("user", "local"):
        rodar([exe, "mcp", "remove", NOME_MCP, "-s", escopo], timeout=60)
    WS_BIN_ISOLADO.mkdir(parents=True, exist_ok=True)
    cmd = [exe, "mcp", "add", "-s", "user", NOME_MCP,
           "-e", f"WATCHSKILL_WHISPER_MODEL={VERSOES['watch_skill']['modelo_transcricao']}",
           "-e", f"WATCHSKILL_BIN_DIR={WS_BIN_ISOLADO}",
           "--", str(ws), "serve"]
    c, o = rodar(cmd, timeout=120)
    print(o)
    if c == 0:
        print("EDITIA_RECARREGAR digite /reload-plugins; se a watch-skill não aparecer, abra uma sessão nova.")
    return 0 if c == 0 else 1


def instalar_remotion() -> int:
    npm, npx = achar("npm"), achar("npx")
    if not npm or not npx:
        print("Node/npm não encontrado. Rode antes: instalar node")
        return 1
    MOTOR.mkdir(parents=True, exist_ok=True)
    for nome in ("package.json", "package-lock.json"):
        shutil.copy2(MODELO_REMOTION / nome, MOTOR / nome)
    shutil.copytree(MODELO_REMOTION / "src", MOTOR / "src", dirs_exist_ok=True)
    c, o = rodar([npm, "ci", "--no-audit", "--no-fund"], timeout=1800, cwd=MOTOR)
    print(o)
    if c != 0:
        return 1
    c, o = rodar([npx, "remotion", "browser", "ensure"], timeout=1800, cwd=MOTOR)
    print(o)
    return 0 if c == 0 else 1


# ---------------------------------------------------------------- entrada

def main(argv: list[str]) -> int:
    if not argv or argv[0] == "verificar":
        somente = None
        if "--estado" in argv:
            somente = argv[argv.index("--estado") + 1].upper()
        return verificar(somente)
    if argv[0] == "instalar" and len(argv) > 1:
        ESTADO_DIR.mkdir(parents=True, exist_ok=True)
        LOG.write_text(f"EDIT.IA instalar {argv[1]} · {time.strftime('%Y-%m-%d %H:%M:%S')}\n", encoding="utf-8")
        return instalar(argv[1])
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
