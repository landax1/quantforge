# Poner botiquant.com en vivo

Lo que hace falta para que alguien que ve un video pueda entrar, registrarse y
bajar la aplicación.

## Por qué alcanza con un servidor chico

Desde que el minado corre en la máquina del usuario, el servidor no hace
cálculo pesado. Sólo sirve páginas, valida logins, firma licencias y entrega un
archivo. Eso corre en el VPS más barato que exista.

La cuenta de tráfico: el ZIP son ~54 MB. Mil descargas son 54 GB, y cualquier
VPS incluye entre 1 y 8 TB por mes. Diez mil descargas siguen entrando.

## El camino corto

En el servidor recién creado, un solo comando:

    curl -fsSL https://raw.githubusercontent.com/landax1/quantforge/main/despliegue/instalar.sh       | sudo bash -s botiquant.com tu@correo.com

Instala todo, saca el certificado y deja el servicio listo. Al final imprime
las dos cosas que hay que completar a mano: las credenciales de Google y las
claves de licencia. Se puede volver a correr sin romper nada.

Abajo está el mismo procedimiento paso a paso, por si algo falla.

## Pasos

**1. Un VPS.** El más chico alcanza (1 vCPU, 1–2 GB). Hostinger, donde ya está
el dominio, sirve; cualquier otro también.

**2. Apuntar el dominio.** En el panel de DNS, dos registros `A` hacia la IP del
servidor:

    @      A    <IP>
    www    A    <IP>

Tarda entre minutos y unas horas en propagarse.

**3. Instalar.**

    sudo adduser --system --group botiquant
    sudo mkdir -p /opt/botiquant && sudo chown botiquant: /opt/botiquant
    sudo -u botiquant git clone <repo> /opt/botiquant
    cd /opt/botiquant
    sudo -u botiquant python3 -m venv .venv
    sudo -u botiquant .venv/bin/pip install -r requirements.txt

`requirements.txt` y no `requirements-desktop.txt`: el servidor no abre
ventanas, no tiene sentido instalarle una biblioteca de interfaz gráfica.

**4. El `.env` del servidor.** NO es el de desarrollo. Cambian tres cosas:

    BQ_SOLO_WEB=1
    BQ_MULTIUSER=1
    BQ_XACCEL=/interno/
    OAUTH_REDIRECT_URI=https://botiquant.com/api/auth/google/callback
    SESSION_SECRET=<uno nuevo, generado en el servidor>
    GOOGLE_CLIENT_ID=<el mismo>
    GOOGLE_CLIENT_SECRET=<el mismo>
    BQ_LICENCIA_PRIVADA=<la MISMA que firma hoy>
    BQ_LICENCIA_PUBLICA=<la misma>

La clave de licencias tiene que ser la misma que está incrustada en el
ejecutable publicado. Si se genera una nueva, las licencias que emita el
servidor no las va a poder verificar ninguna aplicación ya descargada.

**Si alguna vez se rota el par**, son tres pasos y ninguno se puede saltear:

1. `BQ_LICENCIA_PRIVADA` y `BQ_LICENCIA_PUBLICA` en el `.env` del servidor;
2. `CLAVE_PUBLICA` en `botiquant/licencia/clave.py`, que es la que viaja dentro
   del ejecutable — ahí no hay `.env` que leer;
3. recompilar y volver a publicar el ZIP.

Hacer sólo el primero deja al servidor emitiendo licencias que ninguna
aplicación instalada puede verificar, y no hay ninguna señal: el servidor firma
sin problema y la aplicación rechaza. `tests/test_licencia_local.py` compara la
constante contra la privada del `.env` justamente para que eso salga en rojo y
no en producción.

`BQ_MULTIUSER=1` apaga la importación por ruta y el borrado de instrumentos
compartidos. En un servidor abierto, ese endpoint lee cualquier archivo del
disco.

`BQ_XACCEL=/interno/` hace que el ZIP lo entregue nginx y no Python. El
servicio corre con **un solo worker** a propósito —el estado de los logins de
Google vive en memoria del proceso, y con dos falla uno de cada dos sin patrón
aparente—, así que sin esto cada descarga de cincuenta megas compite con los
logins. El valor tiene que coincidir con el bloque `location /interno/` de
`nginx.conf`; hay una prueba que comprueba que los dos archivos digan lo mismo.

**5. El ejecutable.** Se compila en Windows —PyInstaller no hace binarios de
Windows desde Linux— y se sube el ZIP a `/opt/botiquant/dist/`.

**6. nginx y HTTPS.**

    sudo cp despliegue/nginx.conf /etc/nginx/sites-available/botiquant
    sudo ln -s /etc/nginx/sites-available/botiquant /etc/nginx/sites-enabled/
    sudo nginx -t && sudo systemctl reload nginx
    sudo certbot --nginx -d botiquant.com -d www.botiquant.com

HTTPS no es opcional: Google no acepta un callback por http salvo en
localhost, y sin él la cookie de sesión viaja sin cifrar.

**7. El servicio.**

    sudo cp despliegue/botiquant.service /etc/systemd/system/
    sudo systemctl daemon-reload && sudo systemctl enable --now botiquant

**8. Google.** En la consola, agregar a los orígenes y redirecciones
autorizadas:

    https://botiquant.com
    https://botiquant.com/api/auth/google/callback

Y pasar la app a "En producción", o sólo van a poder entrar las cuentas
cargadas como de prueba.

## Comprobar antes de publicar el video

    curl -I https://botiquant.com                    # 200
    curl -s https://botiquant.com/api/descarga       # disponible: true
    curl -I https://botiquant.com/descargar          # 401 sin cuenta

Y entrar con una cuenta que no sea la tuya: es el único modo de ver el flujo
como lo va a ver alguien que llega del video.
