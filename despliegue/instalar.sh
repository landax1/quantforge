#!/usr/bin/env bash
# Instala botiquant.com en un Ubuntu/Debian recién creado.
#
#   sudo bash instalar.sh botiquant.com tu@correo.com
#
# Se puede volver a correr sin romper nada: cada paso comprueba antes de actuar.
# Lo único que no hace es subir el ZIP de la aplicación, que se compila en
# Windows — PyInstaller no genera binarios de Windows desde Linux.

set -euo pipefail

DOMINIO="${1:?Uso: sudo bash instalar.sh <dominio> <correo>}"
CORREO="${2:?Falta el correo para el certificado}"
REPO="${BQ_REPO:-https://github.com/landax1/quantforge.git}"
DESTINO=/opt/botiquant

echo "==> Instalando $DOMINIO en $DESTINO"

# ---------------------------------------------------------------- paquetes
apt-get update -qq
apt-get install -y -qq python3-venv python3-pip git nginx certbot python3-certbot-nginx

# ---------------------------------------------------------------- usuario
# Sin shell y sin home: si alguna vez entran por la aplicación, la cuenta con la
# que corre no sirve para nada más.
id -u botiquant &>/dev/null || adduser --system --group --no-create-home botiquant

# ---------------------------------------------------------------- código
if [ -d "$DESTINO/.git" ]; then
  git -C "$DESTINO" pull --ff-only
else
  git clone --depth 1 "$REPO" "$DESTINO"
fi
mkdir -p "$DESTINO/workspace" "$DESTINO/dist"
chown -R botiquant:botiquant "$DESTINO"

# requirements.txt y NO el de escritorio: el servidor no abre ventanas, no
# tiene sentido instalarle una biblioteca de interfaz gráfica.
sudo -u botiquant python3 -m venv "$DESTINO/.venv" 2>/dev/null || true
sudo -u botiquant "$DESTINO/.venv/bin/pip" install -q --upgrade pip
sudo -u botiquant "$DESTINO/.venv/bin/pip" install -q -r "$DESTINO/requirements.txt"
sudo -u botiquant "$DESTINO/.venv/bin/pip" install -q uvicorn

# ---------------------------------------------------------------- .env
# Se crea si no existe y NUNCA se pisa: sobrescribirlo cambiaría la clave de
# licencias y dejaría al servidor emitiendo licencias que ninguna aplicación ya
# descargada puede verificar.
if [ ! -f "$DESTINO/.env" ]; then
  echo "==> Creando .env (completá las credenciales de Google después)"
  SECRETO=$("$DESTINO/.venv/bin/python" -c "import secrets;print(secrets.token_urlsafe(48))")
  cat > "$DESTINO/.env" <<EOF
# --- modo -----------------------------------------------------------------
# La web NO calcula: sólo registro, licencia y descarga.
BQ_SOLO_WEB=1
BQ_MULTIUSER=1

# El ZIP lo entrega nginx, no Python: la aplicación comprueba que tengas cuenta
# y contesta con una cabecera; nginx lee esa cabecera y manda el archivo. Sin
# esto, cada descarga de cincuenta megas ocupa al único worker que atiende los
# logins. Tiene que coincidir con el bloque `location /interno/` de nginx.
BQ_XACCEL=/interno/

# --- Google ---------------------------------------------------------------
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
OAUTH_REDIRECT_URI=https://$DOMINIO/api/auth/google/callback

# --- sesiones -------------------------------------------------------------
SESSION_SECRET=$SECRETO

# --- licencias ------------------------------------------------------------
# TIENEN que ser las mismas que quedaron incrustadas en el .exe publicado.
# Si se generan nuevas, el servidor emite licencias que las aplicaciones ya
# descargadas no pueden verificar.
BQ_LICENCIA_PRIVADA=
BQ_LICENCIA_PUBLICA=
EOF
  chown botiquant:botiquant "$DESTINO/.env"
  chmod 600 "$DESTINO/.env"
else
  echo "==> .env ya existe, no se toca"
fi

# ---------------------------------------------------------------- servicio
sed "s/botiquant.com/$DOMINIO/g" "$DESTINO/despliegue/botiquant.service" \
  > /etc/systemd/system/botiquant.service
systemctl daemon-reload
systemctl enable botiquant >/dev/null

# ---------------------------------------------------------------- nginx
sed "s/botiquant.com/$DOMINIO/g" "$DESTINO/despliegue/nginx.conf" \
  > /etc/nginx/sites-available/botiquant
ln -sf /etc/nginx/sites-available/botiquant /etc/nginx/sites-enabled/botiquant
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

# ---------------------------------------------------------------- HTTPS
# Google no acepta un callback por http salvo en localhost, así que sin
# certificado el login no funciona. No es un extra.
if [ ! -d "/etc/letsencrypt/live/$DOMINIO" ]; then
  certbot --nginx -d "$DOMINIO" -d "www.$DOMINIO" \
          --non-interactive --agree-tos -m "$CORREO" --redirect
else
  echo "==> El certificado ya existe"
fi

echo
echo "================================================================"
echo " Falta completar a mano, y sin esto el login no anda:"
echo
echo "   nano $DESTINO/.env"
echo "     GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET"
echo "     BQ_LICENCIA_PRIVADA / BQ_LICENCIA_PUBLICA  (las de tu .exe)"
echo
echo " Después:"
echo "   sudo systemctl restart botiquant"
echo
echo " Y subir el ZIP compilado en Windows:"
echo "   scp Botiquant-Windows.zip root@<IP>:$DESTINO/dist/"
echo
echo " En la consola de Google, agregar como redirección autorizada:"
echo "   https://$DOMINIO/api/auth/google/callback"
echo "================================================================"
