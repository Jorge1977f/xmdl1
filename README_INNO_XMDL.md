# Inno Setup - XMDL

## Onde colocar os arquivos
Copie estes dois arquivos para a **raiz do projeto** `C:\xmdl`:
- `XMDL_Setup.iss`
- `Compilar_Inno_XMDL.bat`

A estrutura esperada é esta:

```text
C:\xmdl
├─ XMDL_Setup.iss
├─ Compilar_Inno_XMDL.bat
├─ build
│  ├─ XMDL.ico
│  └─ main.dist
│     └─ XMLDownloader.exe
└─ ... resto do projeto
```

## Como compilar
1. Instale o **Inno Setup 6** no Windows.
2. Copie os dois arquivos acima para `C:\xmdl`.
3. Dê duplo clique em `Compilar_Inno_XMDL.bat`.

Saída esperada:

```text
C:\xmdl\build\inno\XMDL-Setup.exe
```

## O que este instalador faz
- instala o programa em `Arquivos de Programas\XMDL`
- usa o ícone `build\XMDL.ico`
- cria pasta de dados em `C:\xmdl`
- cria atalho no Menu Iniciar
- oferece atalho na Área de Trabalho
- abre o programa ao final da instalação
- usa compressão máxima do Inno (`lzma2/max` + `SolidCompression=yes`)

## Observações
- o arquivo `main.build` do Nuitka não entra no instalador
- apenas a pasta `build\main.dist` é usada
- se quiser alterar a versão exibida no instalador, troque a linha:

```iss
#define MyAppVersion "1.0.0"
```

no arquivo `XMDL_Setup.iss`
