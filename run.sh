#!/bin/bash

################################################################################
# XML Downloader - Script para Executar a Aplicação
################################################################################

# Verifica se o ambiente virtual existe
if [ ! -d "venv" ]; then
    echo "❌ ERRO: Ambiente virtual não encontrado"
    echo ""
    echo "Por favor, execute setup.sh primeiro para configurar o ambiente"
    echo ""
    echo "  bash setup.sh"
    echo ""
    exit 1
fi

# Ativa o ambiente virtual
source venv/bin/activate
if [ $? -ne 0 ]; then
    echo "❌ ERRO ao ativar ambiente virtual"
    exit 1
fi

# Executa a aplicação
echo "🚀 Iniciando XML Downloader..."
echo ""
python main.py
