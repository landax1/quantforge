"""Quién está usando Botiquant. Se corre en el servidor y sólo lee.

    ssh root@botiquant.com "/opt/botiquant/.venv/bin/python /opt/botiquant/despliegue/metricas.py"

TRES FUENTES que miden cosas distintas y no se suman:

  · la base de datos  → quién se dio de alta con Google
  · el log de nginx   → quién miró la portada y quién se bajó el ZIP
  · las licencias     → quién ABRIÓ la aplicación en su máquina

La tercera es la única que dice si alguien la está usando de verdad, y dice
poco: la aplicación es de escritorio y mina sin conexión, así que lo que pasa
adentro —cuántas búsquedas, qué mercados, si exportó algo— no llega acá y no
hay forma de saberlo sin pedirle permiso al usuario para contarlo.

Lo que se ve son DESCARGAS y APERTURAS, no uso. Conviene tenerlo presente
antes de sacar conclusiones sobre si la aplicación le sirvió a alguien.
"""
from __future__ import annotations

import glob
import gzip
import pathlib
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

BASE = pathlib.Path("/opt/botiquant")
DB = BASE / "workspace" / "botiquant.sqlite"
LOGS = sorted(glob.glob("/var/log/nginx/access.log*"))


def titulo(t: str) -> None:
    print(f"\n{'═' * 66}\n{t}\n{'═' * 66}")


# ═══════════════════════════════════════════════════════════════ las cuentas
titulo("CUENTAS")
try:
    cx = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    n = cx.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    hoy = cx.execute("SELECT COUNT(*) FROM users "
                     "WHERE created >= datetime('now','-1 day')").fetchone()[0]
    act = cx.execute("SELECT COUNT(*) FROM users "
                     "WHERE last_seen >= datetime('now','-7 day')").fetchone()[0]
    print(f"  registrados        {n}")
    print(f"  altas 24 h         {hoy}")
    print(f"  vistos 7 días      {act}")
    print("\n  altas por día:")
    for d, c in cx.execute("SELECT substr(created,1,10), COUNT(*) FROM users "
                           "GROUP BY 1 ORDER BY 1 DESC LIMIT 7"):
        print(f"     {d}   {'█' * min(c, 40)} {c}")
except Exception as e:                                        # noqa: BLE001
    print(f"  no pude leer la base: {e}")

# ═══════════════════════════════════════════════════════════════════ el log
LINEA = re.compile(
    r'^(\S+) \S+ \S+ \[([^\]]+)\] "(\S+) (\S+)[^"]*" (\d{3}) (\S+)')


def lineas():
    for f in LOGS:
        abrir = gzip.open if f.endswith(".gz") else open
        try:
            with abrir(f, "rt", errors="replace") as fh:
                for ln in fh:
                    m = LINEA.match(ln)
                    if m:
                        yield m.groups()
        except OSError:
            continue


ips = defaultdict(set)
por_dia = defaultdict(set)
codigos = Counter()
bytes_zip = 0
for ip, cuando, metodo, ruta, cod, tam in lineas():
    limpia = ruta.split("?")[0]
    dia = cuando.split(":")[0]
    if limpia in ("/", "/descargar", "/api/licencia", "/cuenta"):
        ips[limpia].add(ip)
    if limpia == "/":
        por_dia[dia].add(ip)
    if limpia == "/descargar" and cod == "200":
        ips["bajaron"].add(ip)
        bytes_zip += int(tam) if tam.isdigit() else 0
    if cod[0] in "45" and not re.search(r"wp-|\.php|\.env|admin|\.git", limpia):
        codigos[f"{cod} {metodo} {limpia}"] += 1

titulo("EL EMBUDO  (IP distintas)")
for ruta, etiqueta in (("/", "miraron la portada"),
                       ("/cuenta", "entraron a su cuenta"),
                       ("bajaron", "bajaron el ZIP"),
                       ("/api/licencia", "ABRIERON la aplicación")):
    print(f"  {etiqueta:<26} {len(ips[ruta]):>4}")
print(f"\n  MB de ZIP servidos         {bytes_zip / 1048576:>7.0f}")

titulo("VISITANTES POR DÍA")
for dia in sorted(por_dia)[-10:]:
    c = len(por_dia[dia])
    print(f"  {dia:<14} {'█' * min(c, 46)} {c}")

titulo("ERRORES  (sin el ruido de los escáneres)")
if not codigos:
    print("  ninguno")
for k, c in codigos.most_common(12):
    print(f"  {c:>4}x  {k}")

titulo("QUÉ NO SE PUEDE VER DESDE ACÁ")
print("""  La aplicación es de escritorio y mina sin conexión: cuántas búsquedas
  lanzó alguien, sobre qué mercados, si exportó un robot a MetaTrader —nada
  de eso llega al servidor, y no hay forma de saberlo sin pedirle permiso al
  usuario para contarlo.

  Lo más cerca que estamos es la línea "ABRIERON la aplicación", que sale de
  la licencia que se pide al arrancar. Dice que la abrieron. No dice que les
  haya servido.""")

hora = datetime.now(timezone.utc) - timedelta(hours=3)
print(f"\n  medido {hora:%Y-%m-%d %H:%M} (hora de Argentina)")
