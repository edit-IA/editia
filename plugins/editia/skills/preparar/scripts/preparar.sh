#!/usr/bin/env bash
# EDIT.IA — protótipo da porta de entrada: só detecta o sistema operacional.
# Roda no bash do macOS e no Git Bash que o Claude Code usa no Windows.
case "$(uname -s)" in
  Darwin) so="macOS" ;;
  MINGW*|MSYS*|CYGWIN*) so="Windows" ;;
  *) so="desconhecido ($(uname -s))" ;;
esac
pasta="$(cd "$(dirname "$0")/.." && pwd)"
echo "EDITIA_SETUP_OK — $so"
echo "arquitetura: $(uname -m) · skill em: $pasta"
echo "arquivos de configuração: $(ls "$pasta/config" | tr '\n' ' ')"
