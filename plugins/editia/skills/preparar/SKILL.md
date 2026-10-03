---
name: preparar
description: Prepara o computador do aluno do EDIT.IA para editar vídeo com IA. Use quando o aluno pedir "prepare meu computador para editar", "preparar meu computador", "configurar o ambiente do EDIT.IA" ou equivalente.
---

# EDIT.IA — preparar o computador (protótipo da porta de entrada)

Fale com o aluno em português do Brasil, sem jargão técnico.

1. Rode o script de verificação que está na pasta desta skill:

   ```bash
   bash "<pasta desta skill>/scripts/preparar.sh"
   ```

   Use o caminho absoluto da pasta base desta skill (informado quando a skill é carregada).

2. Mostre ao aluno a linha que começa com `EDITIA_SETUP_OK`, exatamente como o script imprimiu.

3. Se o script não imprimir `EDITIA_SETUP_OK`, mostre a saída de erro e pare.
