# JW Notícias Feed

> **Aviso importante:** este é um projeto pessoal e independente. Não foi feito pelas Testemunhas de Jeová, não é um produto oficial da organização e não representa seus posicionamentos.

Aplicativo desktop acessível para acompanhar as notícias de https://www.jw.org/pt/noticias/.

## Recursos

- sincroniza a página e paginação de notícias;
- guarda título, data, região, resumo e URL em SQLite;
- novas notícias entram como **não lidas**;
- filtros por estado de leitura, região e texto;
- marca como lida ao abrir;
- abre no navegador padrão ou mostra um resumo acessível;
- interface baseada em `wx.ListCtrl`, com ordem de tabulação e atalhos de teclado.

## Instalação e build no Windows

```powershell
cd D:\projetos_curtos\feed_rss
.\build.ps1
```

O script cria um ambiente virtual, instala as dependências e gera o executável em `dist\\JWNoticiasFeed\\JWNoticiasFeed.exe`.

Para executar diretamente durante o desenvolvimento:

```powershell
.\.venv\Scripts\Activate.ps1
python main.py
```

Para iniciar minimizado na bandeja do Windows:

```powershell
python main.py --background
```

O menu do ícone da bandeja permite mostrar a janela, sincronizar e sair. O processo não usa servidor local e pode ser colocado no Agendador de Tarefas ou na pasta de inicialização do Windows com `--background`.

No Linux:

```bash
cd /caminho/para/feed_rss
chmod +x build.sh
./build.sh
```

O resultado será `dist/JWNoticiasFeed/JWNoticiasFeed`. Para rodar em segundo plano:

```bash
./dist/JWNoticiasFeed/JWNoticiasFeed --background
```

No Git Bash do Windows, o `build.sh` só deve ser usado se o Python estiver funcionando nesse ambiente POSIX. Para gerar um `.exe` Windows, continue usando `build.ps1` no PowerShell: o PyInstaller constrói para o mesmo sistema operacional em que é executado.

## Instalador Windows

Depois de executar `build.ps1`, instale o [Inno Setup 6](https://jrsoftware.org/isinfo.php), abra `installer.iss` no Inno Setup Compiler e escolha `Build > Compile` (ou pressione `Ctrl+F9`). O instalador será gerado em `installer-output/JWNoticiasFeed-Setup.exe` e oferecerá a opção de iniciar com o Windows, minimizado na bandeja.

Quando iniciado com `--background`, o programa sincroniza e mostra uma notificação nativa com a quantidade de notícias não lidas.

Se `wxPython` não estiver disponível para sua versão do Python, use o instalador oficial correspondente ao Windows/Python.

## Teclas

- `Ctrl+S`: sincronizar
- `Ctrl+F`: focar busca
- `Enter`: abrir notícia selecionada
- `Espaço`: alternar lida/não lida
- `Ctrl+Shift+R`: marcar todas como lidas

O banco fica em `%APPDATA%\\JWNoticiasFeed\\noticias.sqlite3`.
