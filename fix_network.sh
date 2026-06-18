#!/bin/bash
echo "Configurando DNS IPv4 estable para la conexión Wi-Fi (marko)..."
nmcli con mod marko ipv4.dns "8.8.8.8 1.1.1.1"
nmcli con mod marko ipv4.ignore-auto-dns yes

echo "Aplicando los cambios a la interfaz wlo1..."
nmcli dev reapply wlo1

echo "Reiniciando el servicio systemd-resolved para limpiar caché DNS..."
systemctl restart systemd-resolved

echo "Prueba de conexión a GitHub:"
curl -I https://api.github.com

echo ""
echo "¡Listo! La resolución DNS debería estar funcionando correctamente ahora."
