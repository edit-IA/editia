---
name: preparar
description: Prepara o computador do aluno do EDIT.IA para editar vídeo com IA (Aula 1) — diagnostica, instala só o que falta e termina no checklist PRONTO PARA EDITAR. Use quando o aluno pedir "prepare meu computador para editar", "preparar meu computador", "configurar o ambiente do EDIT.IA", "verificar se está tudo instalado" ou equivalente.
---

# EDIT.IA — preparar o computador

Você conduz o setup da Aula 1. Fale com o aluno em **português do Brasil, frases curtas e sem jargão** (não fale "PATH", "MCP", "npm", "venv"; diga "ferramenta de leitura de vídeo", "motor de vídeo" etc.). O aluno pode nunca ter usado um terminal.

## Papéis

- **O juiz (`scripts/editia.sh`) decide.** Ele verifica os 4 estados e grava o resultado. Você nunca declara nada aprovado por conta própria e nunca edita `~/EDITIA/estado/estado.json`.
- **Você resolve.** Quando o juiz reprova algo, você aplica a correção, conduz o aluno quando for preciso e manda o juiz verificar de novo.

Os 4 estados: **1 Claude · 2 Base técnica (ffmpeg, Python, Node) · 3 Watch-skill (transcrição, OCR, ferramenta conectada ao Claude) · 4 Remotion (render real)**.

## Como rodar o juiz

`<pasta>` é a pasta base desta skill (informada quando a skill é carregada). Rode direto, **sem ler os scripts antes**:

```bash
bash "<pasta>/scripts/editia.sh" verificar
```

A saída tem o checklist e, depois da linha `===EDITIA_JSON===`, um JSON com `resultado`, `proximo` (o primeiro item a resolver) e `itens`. Downloads e instalações podem levar minutos: use um timeout longo (10 min) e avise o aluno que está baixando.

## Ciclo

1. Diga ao aluno, em uma frase, que vai verificar o computador. Rode `verificar`.
2. Se `resultado` = `PRONTO`: vá para **Final**.
3. Senão, olhe `proximo` e aja conforme o tipo:
   - **`correcao`** (ex.: `"remotion"`): diga em uma frase o que vai instalar e rode `bash "<pasta>/scripts/editia.sh" instalar <correcao>`. Se o item for `uv`, o comando é `instalar uv`.
   - **`aguardando_claude`**: é o teste da ferramenta de leitura de vídeo. Carregue a ferramenta indicada em `aguardando_claude.ferramenta` (use a busca de ferramentas, se ela estiver adiada) e chame-a com `source` = `aguardando_claude.source`. Não precisa comentar o resultado com o aluno; o juiz confere sozinho.
   - **`humano`**: siga **Ações do aluno**.
   - **`ok: false` sem correção conhecida**: siga **Erro não previsto**.
4. Depois de qualquer ação, rode o juiz de novo **só no estado afetado** (`verificar --estado E2`, `E3` ou `E4`; o estado está em `proximo.estado`) e volte ao passo 2. Quando um estado passar, rode `verificar` completo uma vez antes do final.
5. Limite: **3 tentativas por estado**. Na 3ª falha, pare e vá para **Não ficou pronto**.

Itens com `"bloqueia": false` (links do YouTube) não impedem o 🟢. Se falharem por motivo externo, só avise no final.

## Ações do aluno (só quando inevitáveis)

Explique o que vai acontecer, peça a ação e espere o aluno responder "pronto" ou "continuar".

- **Homebrew no Mac** (a saída tem `EDITIA_HUMANO homebrew`): o instalador pede a senha do computador, e você não pode digitá-la. Se você tiver uma ferramenta para abrir o terminal do app, abra com o comando impresso. Se não, peça para o aluno abrir o app **Terminal**, colar o comando e apertar Enter. Texto para o aluno: *"Agora o Mac vai pedir a senha do seu computador. Ela não aparece enquanto você digita, é normal. Digite, aperte Enter e aguarde até aparecer 'Installation successful'. Se aparecer uma janela da Apple pedindo para instalar 'ferramentas de linha de comando', clique em Instalar. Depois me escreva: continuar."*
- **Janelas do Windows pedindo permissão** (instalações pelo winget): *"O Windows vai abrir uma janela perguntando se você permite a instalação. Clique em Sim."*
- **Depois de registrar a ferramenta de leitura de vídeo** (a saída tem `EDITIA_RECARREGAR`): *"Digite /reload-plugins e aperte Enter. Depois me escreva: continuar."* Se, depois disso, a ferramenta `watch_video` não aparecer, peça para abrir uma **sessão nova** e escrever de novo "prepare meu computador para editar".
- **E1 reprovado** (fora do app Claude): explique que o setup precisa rodar na aba **Code** do app Claude.

## Erro não previsto

Quando o juiz reprova algo sem correção conhecida, ou a correção falha:

1. Leia `evidencia` no JSON e, se precisar, o log em `~/EDITIA/estado/ultimo_log.txt`.
2. Investigue com comandos **só de leitura** (versões, caminhos, `--help`) e, se precisar, a documentação oficial da ferramenta.
3. Aplique a **menor correção possível**. Regras:
   - nunca apague arquivos do aluno;
   - não mexa em configurações de segurança do sistema;
   - peça autorização antes de remover ou desinstalar qualquer coisa;
   - tudo que pedir senha ou clique vai para o aluno, com instruções simples.
4. Rode o juiz de novo no estado afetado. O critério de aprovação é sempre o do juiz.

## Final

Quando o juiz devolver `PRONTO`, mostre ao aluno **o checklist exatamente como o juiz imprimiu**, começando por **🟢 PRONTO PARA EDITAR**, e diga em uma frase que o computador está preparado para as próximas aulas.

## Não ficou pronto

Mostre **🔴 AINDA NÃO ESTÁ PRONTO** e, em linguagem simples:

- o que falhou (o item do checklist);
- a evidência (uma linha);
- a causa provável;
- o que precisa ser feito e quem faz (você ou o aluno).

Sugira que o aluno envie o arquivo `~/EDITIA/estado/estado.json` ao suporte do EDIT.IA.
