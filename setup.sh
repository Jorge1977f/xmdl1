#!/bin/bash

################################################################################
# XML Downloader - Script de Setup Automático para Linux/Mac
################################################################################
#
# Este script cria um ambiente virtual e instala todas as dependências
# automaticamente. Execute uma única vez antes de usar a aplicação.
#
# Uso: bash setup.sh
#
################################################################################

set -e

echo ""
echo "╔════════════════════════════════════════════════════════════════════╗"
echo "║                                                                    ║"
echo "║              XML DOWNLOADER - SETUP AUTOMÁTICO                    ║"
echo "║                                                                    ║"
echo "╚════════════════════════════════════════════════════════════════════╝"
echo ""

# Verifica se Python está instalado
if ! command -v python3 &> /dev/null; then
    echo "❌ ERRO: Python 3 não está instalado"
    echo ""
    echo "Por favor, instale Python 3.11+ usando:"
    echo ""
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        echo "  Ubuntu/Debian:"
        echo "    sudo apt-get update"
        echo "    sudo apt-get install python3 python3-venv python3-pip"
        echo ""
        echo "  Fedora/RHEL:"
        echo "    sudo dnf install python3 python3-venv python3-pip"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        echo "  macOS:"
        echo "    brew install python3"
    fi
    echo ""
    exit 1
fi

echo "✅ Python encontrado"
python3 --version
echo ""

# Verifica se o ambiente virtual já existe
if [ -d "venv" ]; then
    echo "✅ Ambiente virtual já existe"
    echo ""
else
    echo "📦 Criando ambiente virtual..."
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo "❌ ERRO ao criar ambiente virtual"
        exit 1
    fi
    echo "✅ Ambiente virtual criado com sucesso"
    echo ""
fi

# Ativa o ambiente virtual
echo "🔄 Ativando ambiente virtual..."
source venv/bin/activate
if [ $? -ne 0 ]; then
    echo "❌ ERRO ao ativar ambiente virtual"
    exit 1
fi
echo "✅ Ambiente virtual ativado"
echo ""

# Atualiza pip
echo "📦 Atualizando pip..."
python -m pip install --upgrade pip --quiet
if [ $? -ne 0 ]; then
    echo "⚠️  Aviso ao atualizar pip, continuando..."
fi
echo "✅ pip atualizado"
echo ""

# Instala dependências
echo "📦 Instalando dependências..."
echo "   (isso pode levar alguns minutos na primeira vez)"
echo ""
pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "❌ ERRO ao instalar dependências"
    exit 1
fi
echo "✅ Dependências instaladas com sucesso"
echo ""

# Instala Playwright
echo "📦 Instalando Playwright..."
python -m playwright install chromium
if [ $? -ne 0 ]; then
    echo "⚠️  Aviso ao instalar Playwright, continuando..."
fi
echo "✅ Playwright instalado"
echo ""

echo "╔════════════════════════════════════════════════════════════════════╗"
echo "║                                                                    ║"
echo "║                   ✅ SETUP CONCLUÍDO COM SUCESSO!                ║"
echo "║                                                                    ║"
echo "║  Para executar a aplicação, use os comandos abaixo:               ║"
echo "║                                                                    ║"
echo "║  1. Ativar ambiente virtual:                                      ║"
echo "║     source venv/bin/activate                                      ║"
echo "║                                                                    ║"
echo "║  2. Executar aplicação:                                           ║"
echo "║     python main.py                                                ║"
echo "║                                                                    ║"
echo "║  Ou simplesmente execute: bash run.sh                             ║"
echo "║                                                                    ║"
echo "╚════════════════════════════════════════════════════════════════════╝"
echo ""
