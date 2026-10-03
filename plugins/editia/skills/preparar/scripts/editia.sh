#!/usr/bin/env bash
# EDIT.IA — ponto de entrada do setup.
# Roda no bash do macOS e no Git Bash que o Claude Code usa no Windows.
# Única tarefa deste arquivo: garantir o uv (que traz o Python) e chamar o juiz.py.
#
#   editia.sh verificar [--estado E1|E2|E3|E4]   diagnostica e mostra o checklist (não instala nada)
#   editia.sh instalar <componente>              aplica uma correção conhecida (uv, ffmpeg, node, deno,
#                                                watchskill, ytdlp, mcp, remotion)
#   editia.sh amostra                            cria a cópia do clipe de teste para o teste da watch-skill

set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG="$DIR/../config"

case "$(uname -s)" in
  Darwin) SO="macos" ;;
  MINGW*|MSYS*|CYGWIN*) SO="windows" ;;
  *) SO="outro" ;;
esac

acha_uv() {
  for c in "$(command -v uv 2>/dev/null)" "$HOME/.local/bin/uv" "$HOME/.local/bin/uv.exe" "$HOME/.cargo/bin/uv" "${USERPROFILE:-}/.local/bin/uv.exe"; do
    if [ -n "$c" ] && [ -x "$c" ]; then echo "$c"; return 0; fi
  done
  return 1
}

if [ "${1:-}" = "instalar" ] && [ "${2:-}" = "uv" ]; then
  if acha_uv >/dev/null; then echo "uv já instalado: $(acha_uv)"; exit 0; fi
  if [ "$SO" = "macos" ]; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
  elif [ "$SO" = "windows" ]; then
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  else
    echo "Sistema não suportado pelo EDIT.IA: $(uname -s)"; exit 3
  fi
  acha_uv >/dev/null && { echo "uv instalado: $(acha_uv)"; exit 0; }
  echo "uv não ficou disponível depois da instalação."; exit 1
fi

UV="$(acha_uv)" || {
  # Sem uv não há Python para o juiz: responde no mesmo formato do juiz, com a correção conhecida.
  echo "🔴 AINDA NÃO ESTÁ PRONTO"
  echo "2. Base técnica · Python (uv) ............ ❌ uv não encontrado"
  echo "===EDITIA_JSON==="
  echo "{\"resultado\":\"NAO_PRONTO\",\"sistema\":\"$SO\",\"proximo\":{\"estado\":\"E2\",\"item\":\"uv\",\"tipo\":\"correcao\",\"comando\":\"instalar uv\",\"evidencia\":\"uv ausente no PATH e em ~/.local/bin\"}}"
  exit 1
}

export EDITIA_UV="$UV" EDITIA_SO="$SO" EDITIA_CONFIG="$CONFIG" EDITIA_SCRIPTS="$DIR"
exec "$UV" run --quiet --no-project --python 3.12 "$DIR/juiz.py" "$@"
