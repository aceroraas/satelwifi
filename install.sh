#!/bin/bash

echo "🚀 Configurando SatelWifi Bot..."

# Verificar si python3-venv está instalado
if ! dpkg -l | grep -q python3-venv; then
    echo "📦 Instalando python3-venv..."
    sudo apt-get update
    sudo apt-get install -y python3-venv
fi

echo "✅ Configuración completada."
echo "🚀 Para iniciar el bot, ejecuta: python3 manager_bots.py"
