#!/bin/bash
# ==============================================================================
# Script de Configuración de Red para VPS (Evadir Bloqueo de IP del Poder Judicial)
# Jurisprudencia Nacional - Proyecto Automatizado
# ==============================================================================

# Colores para salida de consola
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # Sin color

echo -e "${CYAN}======================================================================"
echo -e "   CONFIGURADOR DE RED PARA JURISPRUDENCIA NACIONAL (VPS)"
echo -e "======================================================================${NC}"
echo "Este script te guiará para configurar un Proxy o una VPN en tu servidor"
echo "para evitar el bloqueo/timeout del portal de Jurisprudencia del Perú."
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

show_menu() {
    echo -e "${CYAN}Selecciona una opción de configuración:${NC}"
    echo "1) Configurar un PROXY en el archivo .env (Recomendado y rápido)"
    echo "2) Instalar y levantar VPN con OpenVPN (Toda la VM sale por la VPN)"
    echo "3) Verificar IP actual de la VM (Comprobar geolocalización)"
    echo "4) Salir"
    echo -n "Opción [1-4]: "
}

configure_proxy() {
    echo -e "\n${CYAN}--- CONFIGURACIÓN DE PROXY ---${NC}"
    echo "Ingresa los detalles de tu proxy (preferiblemente residencial en Perú o comercial limpio)."
    echo ""
    
    echo -n "1. IP/Host y Puerto del Proxy (Ejemplo: http://190.119.12.34:8080): "
    read -r proxy_server
    
    if [ -z "$proxy_server" ]; then
        echo -e "${RED}[ERROR] El servidor del proxy no puede estar vacío.${NC}"
        return
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
    echo -e "${YELLOW}[INFO] Levantando contenedores con la nueva configuración...${NC}"
    docker-compose up -d --build
    echo -e "${GREEN}[ÉXITO] Contenedores actualizados y ejecutándose en segundo plano.${NC}"
}

configure_vpn() {
    echo -e "\n${CYAN}--- INSTALACIÓN Y CONFIGURACIÓN DE OPENVPN ---${NC}"
    echo "Este proceso instalará OpenVPN y configurará tu archivo de conexión .ovpn."
    echo ""
    
    # 1. Instalar OpenVPN
    echo -e "${YELLOW}[INFO] Actualizando paquetes e instalando OpenVPN...${NC}"
    sudo apt update && sudo apt install -y openvpn
    
    # 2. Obtener archivo de configuración
    echo -e "\n${YELLOW}[ACCIÓN REQUERIDA]${NC} Por favor, copia y pega el contenido completo de tu archivo de configuración (.ovpn)."
    echo "Al terminar de pegar, presiona Ctrl+D en una línea vacía para guardar:"
    echo -e "${CYAN}------------------------------------------------------------${NC}"
    cat > vpn_config.ovpn
    echo -e "${CYAN}------------------------------------------------------------${NC}"
    
    if [ ! -s vpn_config.ovpn ]; then
        echo -e "${RED}[ERROR] No se pegó ningún contenido. Abortando instalación de VPN.${NC}"
        rm -f vpn_config.ovpn
        return
    fi
    
    echo -e "${GREEN}[ÉXITO] Archivo vpn_config.ovpn creado.${NC}"
    
    # 3. Preguntar por credenciales
    echo -n "¿Tu proveedor de VPN requiere usuario y contraseña para conectar? (s/n): "
    read -r requires_auth
    
    if [ "$requires_auth" = "s" ] || [ "$requires_auth" = "S" ]; then
        echo -n "Ingresa el Usuario de tu VPN: "
        read -r vpn_user
        echo -n "Ingresa la Contraseña de tu VPN: "
        read -s -r vpn_pass
        echo ""
        
        # Guardar credenciales
        echo "$vpn_user" > vpn_creds.txt
        echo "$vpn_pass" >> vpn_creds.txt
        chmod 600 vpn_creds.txt
        
        # Modificar archivo .ovpn para que lea las credenciales automáticamente
        if grep -q "auth-user-pass" vpn_config.ovpn; then
            # Si ya tiene la directiva auth-user-pass, la redirigimos a nuestro archivo
            sed -i 's/auth-user-pass.*/auth-user-pass vpn_creds.txt/' vpn_config.ovpn
        else
            # Si no la tiene, la añadimos al final
            echo "auth-user-pass vpn_creds.txt" >> vpn_config.ovpn
        fi
        echo -e "${GREEN}[INFO] Credenciales guardadas y vinculadas al archivo de configuración.${NC}"
    fi
    
    # 4. Levantar la VPN
    echo -e "\n${YELLOW}[INFO] Iniciando OpenVPN en segundo plano...${NC}"
    sudo openvpn --config vpn_config.ovpn --daemon
    
    echo -e "${YELLOW}[INFO] Esperando 8 segundos a que se establezca la conexión...${NC}"
    sleep 8
    
    # Verificar IP
    verify_ip
    
    # 5. Levantar contenedores
    echo -e "\n${YELLOW}[INFO] Reiniciando contenedores de Docker en la red VPN...${NC}"
    docker-compose down
    docker-compose up -d --build
    echo -e "${GREEN}[ÉXITO] Contenedores levantados correctamente dentro del canal de la VPN.${NC}"
}

verify_ip() {
    echo -e "\n${CYAN}--- COMPROBACIÓN DE DIRECCIÓN IP ---${NC}"
    echo "Consultando servicio de geolocalización..."
    
    ip_info=$(curl -s --max-time 10 ipinfo.io)
    
    if [ -z "$ip_info" ]; then
        echo -e "${RED}[ERROR] No se pudo obtener información de red. Verifica tu conexión a internet o el estado de la VPN/Proxy.${NC}"
        return
    fi
    
    ip=$(echo "$ip_info" | grep -o '"ip": "[^"]*' | cut -d'"' -f4)
    city=$(echo "$ip_info" | grep -o '"city": "[^"]*' | cut -d'"' -f4)
    country=$(echo "$ip_info" | grep -o '"country": "[^"]*' | cut -d'"' -f4)
    org=$(echo "$ip_info" | grep -o '"org": "[^"]*' | cut -d'"' -f4)
    
    echo -e "${GREEN}IP Actual:${NC} $ip"
    echo -e "${GREEN}Proveedor/ISP:${NC} $org"
    echo -e "${GREEN}Ubicación:${NC} $city, $country"
    
    if [[ "$org" == *"Google"* || "$org" == *"Amazon"* || "$org" == *"Microsoft"* ]]; then
        echo -e "${RED}[ADVERTENCIA] Tu IP actual ($org) está catalogada como Data Center. El Poder Judicial probablemente te bloqueará.${NC}"
    else
        echo -e "${GREEN}[OK] Tu IP actual no parece ser de un Data Center estándar. Listo para raspar.${NC}"
    fi
    echo ""
}

# Bucle principal
while true; do
    show_menu
    read -r main_option
    case $main_option in
        1)
            configure_proxy
            break
            ;;
        2)
            configure_vpn
            break
            ;;
        3)
            verify_ip
            ;;
        4)
            echo "Saliendo del configurador."
            break
            ;;
        *)
            echo -e "${RED}Opción no válida. Inténtalo de nuevo.${NC}\n"
            ;;
    esac
done
