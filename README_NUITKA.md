# Build com Nuitka - XML Downloader

## O que foi ajustado neste projeto
- Banco, logs, cache, certificados e XMLs agora ficam fora da pasta do executável, por padrão em `C:/xmdl`.
- O projeto foi limpo para publicação: sem `.env`, sem banco SQLite local, sem logs e sem cache gerado.
- O setup passou a instalar somente o navegador necessário do Playwright (`chromium`).
- Foram adicionados scripts prontos para build com Nuitka.

## 1) Preparar ambiente
No Windows, dentro da pasta do projeto:

```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements-build.txt
python -m playwright install chromium
```

## 2) Build recomendado
Teste primeiro o build **standalone**:

```bat
build_nuitka_standalone.bat
```

Saída esperada:
- `build/main.dist/XMLDownloader.exe`

Esse é o modo mais indicado para empacotar com Inno Setup.

## 3) Build onefile (opcional)
Use só depois que o standalone estiver validado:

```bat
build_nuitka_onefile.bat
```

Saída esperada:
- `build/XMLDownloader.exe`

## 4) Onde ficam os dados do programa
Por padrão, o aplicativo vai gravar tudo em:

```text
C:/xmdl
```

Estrutura principal:
- `C:/xmdl/data/db`
- `C:/xmdl/data/logs`
- `C:/xmdl/data/cache_raw`
- `C:/xmdl/data/downloads`
- `C:/xmdl/data/xml_processados`
- `C:/xmdl/data/certificados`

Se quiser mudar isso, defina a variável:

```text
XMLDLK_HOME=C:/outra/pasta
```

## 5) .env
Crie um `.env` em uma destas localizações:
- `C:/xmdl/.env`
- ao lado do executável / pasta do projeto

Exemplo mínimo:

```env
XMLDLK_LICENSE_API_URL=https://seu-backend.onrender.com
XMLDLK_APP_VERSION=1.0.0
PLAYWRIGHT_HEADLESS=True
```

## 6) Dica prática de distribuição
Para cliente final, o melhor fluxo é:
1. compilar com `build_nuitka_standalone.bat`
2. testar `build/main.dist/XMLDownloader.exe`
3. gerar o instalador no Inno Setup apontando para a pasta `build/main.dist`
4. publicar o instalador no GitHub Releases
