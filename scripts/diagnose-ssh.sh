#!/usr/bin/env bash
# Diagnóstico para cuando el VPS SIGUE pidiendo password después de setup-ssh.sh.
# Te pide la password (entra por password a propósito) y muestra qué está mal.
set -uo pipefail

VPS="odoo-admin@178.105.15.189"
KEY="$HOME/.ssh/id_ed25519"

echo "=================================================================="
echo " 1) ¿La Mac tiene la llave?"
echo "=================================================================="
ls -l "$KEY" "$KEY.pub" 2>&1 || echo "✗ No hay llave en la Mac — corré setup-ssh.sh"

echo
echo "=================================================================="
echo " 2) Intento de login POR CLAVE con verbose (mirá las líneas 'debug1')"
echo "=================================================================="
# Mostramos solo las líneas relevantes de por qué acepta/rechaza la clave.
ssh -o BatchMode=yes -o ConnectTimeout=10 -v "$VPS" 'echo OK' 2>&1 \
  | grep -Ei "Offering|Authentications that can continue|Server accepts key|publickey|Permission denied|Authenticated" \
  || echo "(sin salida relevante)"

echo
echo "=================================================================="
echo " 3) Estado del lado SERVER (entra por password 1 vez)"
echo "=================================================================="
ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no "$VPS" '
  echo "--- permisos (home debe ser 0755/0700 y NO group-writable) ---"
  ls -ld ~ ~/.ssh ~/.ssh/authorized_keys 2>&1
  echo
  echo "--- ¿la pubkey está en authorized_keys? ---"
  wc -l ~/.ssh/authorized_keys 2>/dev/null
  echo
  echo "--- opciones sshd relevantes ---"
  sudo sshd -T 2>/dev/null | grep -Ei "pubkeyauthentication|authorizedkeysfile|strictmodes" \
    || grep -Ei "PubkeyAuthentication|AuthorizedKeysFile|StrictModes" /etc/ssh/sshd_config /etc/ssh/sshd_config.d/* 2>/dev/null \
    || echo "(no pude leer sshd config sin sudo)"
  echo
  echo "--- últimos rechazos en el log de auth ---"
  sudo tail -n 15 /var/log/auth.log 2>/dev/null | grep -i ssh \
    || echo "(sin acceso a /var/log/auth.log — probá: sudo journalctl -u ssh -n 20)"
'

echo
echo "=================================================================="
echo " Pistas:"
echo "  • Si el home aparece 'drwxrwxr-x' o 'drwxrwxrwx' → StrictModes lo rechaza."
echo "    Fix:  ssh $VPS 'chmod g-w,o-w ~'"
echo "  • Si 'pubkeyauthentication no' → habilitar en sshd_config y reiniciar sshd."
echo "  • Si authorized_keys tiene 0 líneas → re-correr setup-ssh.sh."
echo "=================================================================="
