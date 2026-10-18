"""
DESCARGA SEGURA de páginas web (protección contra SSRF y descargas abusivas).

Reglas:
  - sólo http y https; sin usuario/contraseña en la URL;
  - el nombre se resuelve por DNS y se rechaza si CUALQUIERA de sus IPs es privada, de loopback,
    link-local, multicast, reservada o no especificada (p.ej. 127.0.0.1, 10.x, 192.168.x, 169.254.169.254);
  - las redirecciones se siguen a mano (máximo 3) y cada destino se vuelve a validar;
  - tiempo límite de conexión y de lectura; tamaño máximo; tipos de contenido permitidos.

Riesgo residual documentado: entre la validación DNS y la conexión podría cambiar la resolución
(DNS rebinding). Para un servidor local de un solo equipo se considera aceptable.
"""
from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import requests

AGENTE = "DINAMO-Analytics/1.0 (asistente de investigacion; contacto local)"
TAMANO_MAXIMO = 3 * 1024 * 1024
TIPOS_PERMITIDOS = ("text/html", "application/xhtml+xml", "text/plain", "application/pdf", "application/json",
                    "text/xml", "application/xml")
MAX_REDIRECCIONES = 3


class URLBloqueada(ValueError):
    """La URL no se puede leer por seguridad (esquema, red privada, tamaño o tipo)."""


@dataclass(frozen=True)
class Descarga:
    url: str            # URL final tras redirecciones
    tipo: str
    contenido: bytes
    estado: int


def _ip_publica(ip: str) -> bool:
    d = ipaddress.ip_address(ip)
    if isinstance(d, ipaddress.IPv6Address) and d.ipv4_mapped:
        d = d.ipv4_mapped
    return not (d.is_private or d.is_loopback or d.is_link_local or d.is_multicast or d.is_reserved
                or d.is_unspecified or not d.is_global)


def validar_url(url: str, resolver=socket.getaddrinfo) -> str:
    partes = urlsplit(url.strip())
    if partes.scheme not in ("http", "https"):
        raise URLBloqueada("Sólo se permiten direcciones http o https.")
    if not partes.hostname:
        raise URLBloqueada("La dirección no tiene un dominio válido.")
    if partes.username or partes.password:
        raise URLBloqueada("La dirección no puede incluir usuario ni contraseña.")
    host = partes.hostname
    if host in ("localhost",) or host.endswith((".local", ".internal", ".localhost")):
        raise URLBloqueada("No se permiten direcciones internas.")
    try:
        ips = {info[4][0] for info in resolver(host, partes.port or (443 if partes.scheme == "https" else 80))}
    except (socket.gaierror, OSError) as exc:
        raise URLBloqueada(f"No se pudo resolver el dominio {host}.") from exc
    if not ips or not all(_ip_publica(ip) for ip in ips):
        raise URLBloqueada("La dirección apunta a una red privada o reservada.")
    return url.strip()


def descargar(url: str, tamano_maximo: int = TAMANO_MAXIMO, tiempo: tuple = (6, 15),
              resolver=socket.getaddrinfo, sesion=requests) -> Descarga:
    actual = validar_url(url, resolver)
    for _ in range(MAX_REDIRECCIONES + 1):
        try:
            r = sesion.get(actual, headers={"User-Agent": AGENTE, "Accept": "text/html,application/pdf,text/plain;q=0.9,*/*;q=0.5"},
                           allow_redirects=False, stream=True, timeout=tiempo)
        except requests.RequestException as exc:
            raise URLBloqueada(f"No se pudo conectar: {type(exc).__name__}") from exc
        if r.status_code in (301, 302, 303, 307, 308):
            destino = r.headers.get("Location")
            r.close()
            if not destino:
                raise URLBloqueada("Redirección sin destino.")
            actual = validar_url(urljoin(actual, destino), resolver)
            continue
        try:
            if r.status_code >= 400:
                raise URLBloqueada(f"El sitio respondió con error {r.status_code}.")
            tipo = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if tipo and not tipo.startswith(TIPOS_PERMITIDOS):
                raise URLBloqueada(f"Tipo de contenido no permitido: {tipo}.")
            largo = r.headers.get("Content-Length")
            if largo and largo.isdigit() and int(largo) > tamano_maximo:
                raise URLBloqueada("El documento es demasiado grande.")
            trozos, total = [], 0
            for trozo in r.iter_content(64 * 1024):
                total += len(trozo)
                if total > tamano_maximo:
                    raise URLBloqueada("El documento es demasiado grande.")
                trozos.append(trozo)
            return Descarga(actual, tipo or "text/html", b"".join(trozos), r.status_code)
        finally:
            r.close()
    raise URLBloqueada("Demasiadas redirecciones.")
