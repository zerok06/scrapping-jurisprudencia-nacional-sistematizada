#!/bin/bash
# ==============================================================================
# Script de Configuración de Proxy para VPS (Evadir Bloqueo de IP del Poder Judicial)
# Jurisprudencia Nacional - Proyecto Automatizado
# ==============================================================================

# Colores para salida de consola
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # Sin color

echo -e "${CYAN}======================================================================"
echo -e "   CONFIGURADOR DE PROXY PARA JURISPRUDENCIA NACIONAL (VPS)"
echo -e "======================================================================${NC}"
echo "Este script configurará de manera exclusiva un proxy residencial o limpio"
echo "en tu archivo de variables de entorno (.env) y lo validará con el servicio"
echo "de geolocalización."
echo ""

# Verificar que el archivo .env exista
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        echo -e "${YELLOW}[INFO] Creando archivo .env desde .env.example...${NC}"
        cp .env.example .env
    else
        echo -e "${RED}[ERROR] No se encontró .env ni .env.example en el directorio actual.${NC}"
        exit 1
    fi
fi

# Función para actualizar/agregar variables en el archivo .env de forma segura
update_env_var() {
    local key=$1
    local val=$2
    # Escapar barras diagonales para el comando sed
    local escaped_val=$(echo "$val" | sed 's/\//\\\//g')
    
    if grep -q "^${key}=" .env; then
        # Si la variable ya existe, la reemplazamos
        sed -i "s/^${key}=.*/${key}=${escaped_val}/" .env
    else
        # Si no existe, la añadimos al final del archivo
        echo "${key}=${val}" >> .env
    fi
}

echo -e "${CYAN}--- CONFIGURACIÓN DE PROXY ---${NC}"
echo "Ingresa los detalles de tu proxy residencial (Perú o comercial limpio)."
echo ""

echo -n "1. Servidor/Host y Puerto (Ejemplo: 190.119.12.34:8080 o http://190.119.12.34:8080): "
read -r proxy_server

if [ -z "$proxy_server" ]; then
    echo -e "${RED}[ERROR] El servidor del proxy no puede estar vacío.${NC}"
    exit 1
fi

# Asegurarse de tener un protocolo básico
if [[ "$proxy_server" != *"://"* ]]; then
    proxy_server="http://$proxy_server"
fi

echo -n "2. Usuario del Proxy (Opcional, presiona Enter si no requiere): "
read -r proxy_user

proxy_pass=""
if [ -n "$proxy_user" ]; then
    echo -n "3. Contraseña del Proxy: "
    read -s -r proxy_pass
    echo ""
fi

echo -e "\n${YELLOW}[INFO] Guardando configuración en el archivo .env...${NC}"
update_env_var "PROXY_SERVER" "$proxy_server"
update_env_var "PROXY_USER" "$proxy_user"
update_env_var "PROXY_PASS" "$proxy_pass"

echo -e "${GREEN}[ÉXITO] Configuración de proxy guardada en .env.${NC}"
echo ""

# Validar conexión usando el proxy configurado
echo -e "${CYAN}--- PROBANDO CONECTIVIDAD DEL PROXY ---${NC}"
echo "Consultando servicio de geolocalización ipinfo.io..."

if [ -n "$proxy_user" ]; then
    ip_info=$(curl -s --max-time 15 -x "$proxy_server" --proxy-user "$proxy_user:$proxy_pass" ipinfo.io)
else
    ip_info=$(curl -s --max-time 15 -x "$proxy_server" ipinfo.io)
fi

if [ -z "$ip_info" ]; then
    echo -e "${RED}[ERROR] No se pudo establecer conexión a través del proxy.${NC}"
    echo "Verifica que el host, puerto y las credenciales sean válidos."
    exit 1
fi

# Parsear datos de la IP
ip=$(echo "$ip_info" | grep -o '"ip": "[^"]*' | cut -d'"' -f4)
city=$(echo "$ip_info" | grep -o '"city": "[^"]*' | cut -d'"' -f4)
country=$(echo "$ip_info" | grep -o '"country": "[^"]*' | cut -d'"' -f4)
org=$(echo "$ip_info" | grep -o '"org": "[^"]*' | cut -d'"' -f4)

echo -e "${GREEN}IP Externa Detectada:${NC} $ip"
echo -e "${GREEN}Proveedor / ISP:${NC} $org"
echo -e "${GREEN}Ubicación de Salida:${NC} $city, $country"

if [[ "$org" == *"Google"* || "$org" == *"Amazon"* || "$org" == *"Microsoft"* ]]; then
    echo -e "${RED}[ADVERTENCIA] Tu IP de salida ($org) está catalogada como Data Center. El Poder Judicial probablemente te bloqueará.${NC}"
else
    echo -e "${GREEN}[OK] Proxy validado con éxito. IP limpia detectada.${NC}"
fi

echo ""
echo -e "${YELLOW}[INFO] Levantando/Reconstruyendo contenedores de Docker...${NC}"
docker-compose up -d --build
echo -e "${GREEN}[ÉXITO] Contenedores actualizados y ejecutándose en segundo plano con la nueva red proxy.${NC}"
echo "======================================================================"
