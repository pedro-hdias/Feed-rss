# JW Notícias Feed

> **Aviso importante:** este é um projeto pessoal e independente. Não foi feito pelas Testemunhas de Jeová, não é um produto oficial da organização e não representa seus posicionamentos.

Aplicativo desktop para Windows, **pensado para uso com leitor de tela** (NVDA, JAWS), que acompanha as notícias de https://www.jw.org/pt/noticias/.

## Recursos

- sincroniza as notícias e guarda título, data, região, resumo e texto completo em SQLite;
- notícias novas entram como **não lidas**; filtros por leitura, região (com contagem de não lidas) e texto;
- **leitura dentro do app** (`Enter`): título, data, região, resumo e, sob demanda, o texto completo, sem tirar o foco para o navegador;
- navegação rápida entre não lidas (`F8` / `Shift+F8`);
- sincronização automática periódica, notificações e ícone na bandeja com o total de não lidas;
- instância única: abrir o programa de novo traz a janela já aberta para a frente;
- atalho global para mostrar/esconder a janela (padrão `Ctrl+Alt+J`).

## Acessibilidade

- barra de menus completa (Arquivo, Notícia, Exibir, Ajuda), que é como o leitor de tela revela as funções;
- todo campo tem rótulo imediatamente antes dele e atalho `Alt+letra`; botões e itens de menu têm mnemônicos;
- a barra de status é a real do Windows (leitores a leem com `Insert+End` no NVDA); `Ctrl+E` fala o resumo do estado;
- as mudanças importantes são faladas pelo `accessible_output2`, sempre na thread da interface. No modo **Automática**, o programa só fala por conta própria se houver um leitor de tela ativo (não usa a voz do Windows/SAPI sozinha, para não criar uma segunda voz). Há outros modos em **Opções**;
- a lista mantém a seleção ao marcar como lida, filtrar ou sincronizar; colunas na ordem **Estado, Título, Data, Região** (configurável: com o título primeiro, a digitação rápida na lista encontra pelo título);
- regiões aparecem em caixa mista ("Notícias Mundiais"), porque leitores de tela soletram texto todo em maiúsculas;
- `Enter` e `Espaço` só agem dentro da lista (não atrapalham a busca nem os botões); a tecla Aplicativos / `Shift+F10` abre o menu sobre o item selecionado.

## Teclas

Na lista: `Enter` ler · `Ctrl+Enter` abrir no navegador · `Espaço` lida/não lida · `Ctrl+C` copiar título e link · `F8`/`Shift+F8` próxima/anterior não lida.

Em qualquer lugar: `Ctrl+S` sincronizar · `Ctrl+F` busca (Enter leva à lista) · `Ctrl+L` lista · `Ctrl+E` falar status · `Ctrl+Shift+R` marcar todas como lidas · `Ctrl+O` opções · `Ctrl+M` enviar para a bandeja · `Ctrl+Q` sair · `F1` ajuda.

Ao ler uma notícia: `Alt+A`/`Alt+P` anterior/próxima · `Alt+N` navegador · `Alt+C` texto completo · `Alt+L` lida/não lida · `Alt+I` copiar link · `Esc` fecha.

## Bandeja

Minimizar (ou `Ctrl+M`) envia o programa para a bandeja. Para voltar: clique no ícone, use o atalho global, ou abra o programa de novo. Fechar no X encerra o programa, a menos que você ative em **Opções** "Fechar a janela envia para a bandeja".

Opções de linha de comando: `--background` (inicia na bandeja e sincroniza) e `--interval N` (minutos entre sincronizações nesta execução; 0 desativa). O padrão, 60 minutos, e as demais preferências ficam em **Opções** (`settings.json`).

## Build no Windows

```powershell
.\build.ps1
```

Cria o ambiente virtual, instala as dependências, gera `dist\JWNoticiasFeed\JWNoticiasFeed.exe` e, se o [Inno Setup 6](https://jrsoftware.org/isinfo.php) estiver instalado, o instalador em `installer-output\JWNoticiasFeed-Setup-<versão>.exe`. O build inclui as DLLs e módulos do `accessible_output2` (`--collect-all`); sem isso o .exe não consegue falar.

Desenvolvimento: `python main.py`. No Linux, `build.sh` gera o binário (o app é voltado ao Windows).

## Testes e CI

```bash
pip install -r requirements-dev.txt   # ou: pip install pytest requests beautifulsoup4
python -m pytest
```

Cobrem banco, parser, formatação e configurações (sem wxPython). O workflow `.github/workflows/build.yml` roda os testes em Linux e Windows e gera o .exe e o instalador no Windows; em tags `v*` publica o instalador na release.

## Arquivos de dados e diagnóstico

Tudo em `%APPDATA%\JWNoticiasFeed\`: `noticias.sqlite3`, `settings.json`, `feed.log` (com rotação) e `crash.log` (quedas nativas de DLL/COM). Envie `feed.log` e `crash.log` ao relatar travamentos; **Ajuda > Abrir pasta de logs** abre essa pasta.

## Limitações conhecidas

- O parser depende do HTML do site; se ele mudar, a sincronização avisa que nenhuma notícia foi reconhecida em vez de falhar em silêncio. Os testes usam HTML sintético: atualize `tests/test_parser.py` com uma página salva quando o site mudar.
- As variantes `pt-pt` e `pt-ao` seguem o mesmo padrão de URL, mas não foram testadas.
- O leitor de tela Narrator não é suportado pelo `accessible_output2`; use o modo de voz "Só quando eu pedir" ou "Eventos importantes" se quiser falas pela voz do Windows.
