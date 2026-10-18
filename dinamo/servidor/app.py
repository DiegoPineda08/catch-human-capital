"""
SERVIDOR LOCAL DE DINAMO (sólo biblioteca estándar de Python + requests).

    python -m dinamo.servidor            # abre http://127.0.0.1:8765

Seguridad:
  - escucha sólo en 127.0.0.1 salvo que se configure DINAMO_HOST y además DINAMO_TOKEN;
  - sirve archivos estáticos SÓLO de la carpeta frontend/ (sin listados, sin archivos ocultos,
    con extensiones permitidas); nunca .env, código, datos ni carpetas privadas;
  - toda petición que modifica algo exige la cabecera X-DINAMO (bloquea formularios de otros sitios)
    y, si llega Origin, que coincida con el propio servidor;
  - ids validados, nombres de archivo saneados, límites de tamaño;
  - las claves de API se leen del .env del servidor y nunca se envían al navegador;
  - el registro de operaciones guarda método, ruta, estado y duración: nunca contenidos.
"""
from __future__ import annotations

import json
import mimetypes
import os
import re
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

RAIZ = Path(__file__).resolve().parents[2]
VERSION = "fase1-2026.10"
MAX_JSON = 1024 * 1024
MAX_SUBIDA = 25 * 1024 * 1024
ESTATICOS = {".html", ".css", ".js", ".mjs", ".webp", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff2",
             ".woff", ".json", ".txt", ".map"}


def cargar_env(ruta: Path) -> None:
    """Lee KEY=VALOR de .env sin pisar variables ya definidas en el sistema."""
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        clave, valor = clave.strip(), valor.strip().strip('"').strip("'")
        if clave and clave not in os.environ:
            os.environ[clave] = valor


class Estado:
    """Recursos compartidos del servidor."""

    def __init__(self, carpeta_datos: Path, carpeta_frontend: Path):
        from dinamo.conversacion import Gestor
        self.gestor = Gestor(carpeta_datos)
        self.frontend = carpeta_frontend.resolve()
        self.carpeta_datos = carpeta_datos
        self._llm, self._llm_t = None, 0.0
        self._candado = threading.Lock()
        self.registro = carpeta_datos / "registro_operaciones.log"
        self.token = os.getenv("DINAMO_TOKEN", "").strip()
        self.huellas = huellas_scripts(self.frontend) if self.frontend.exists() else ""

    def llm(self, forzar: bool = False):
        from dinamo.llm.proveedores import elegir_proveedor
        with self._candado:
            if forzar or time.time() - self._llm_t > 60:
                self._llm, self._llm_t = elegir_proveedor(), time.time()
            return self._llm

    def anotar(self, metodo: str, ruta: str, estado: int, ms: float) -> None:
        try:
            ruta = re.sub(r"/archivos/[^/?]+", "/archivos/<archivo>", ruta.split("?")[0])
            with self.registro.open("a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\t{metodo}\t{ruta}\t{estado}\t{ms:.0f}ms\n")
        except OSError:
            pass


CSP = ("default-src 'self'; script-src 'self' https://cdn.jsdelivr.net https://esm.run 'wasm-unsafe-eval'; "
       "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; "
       "img-src 'self' data: blob:; media-src 'self' blob: data:; worker-src 'self' blob:; "
       "connect-src 'self' https://cdn.jsdelivr.net https://esm.run https://huggingface.co https://*.huggingface.co "
       "https://*.hf.co https://raw.githubusercontent.com; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")


def huellas_scripts(carpeta: Path) -> str:
    """Huellas SHA-256 de los <script> incrustados en los HTML de frontend/ (p.ej. DINAMO_Fase1.html).

    Así la versión de un solo archivo funciona sin permitir scripts incrustados arbitrarios ('unsafe-inline')."""
    import base64
    import hashlib
    huellas = set()
    for html in carpeta.glob("*.html"):
        texto = html.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"<script>(.*?)</script>", texto, re.S):
            huellas.add("'sha256-" + base64.b64encode(hashlib.sha256(m.group(1).encode("utf-8")).digest()).decode() + "'")
    return " ".join(sorted(huellas))


class Error(Exception):
    def __init__(self, estado: int, mensaje: str):
        super().__init__(mensaje)
        self.estado, self.mensaje = estado, mensaje


RUTAS: list[tuple[str, re.Pattern, str]] = []


def ruta(metodo: str, patron: str):
    def deco(fn):
        RUTAS.append((metodo, re.compile("^" + patron + "$"), fn.__name__))
        return fn
    return deco


class Manejador(BaseHTTPRequestHandler):
    server_version = "DINAMO"
    sys_version = ""
    protocol_version = "HTTP/1.1"
    estado: Estado = None            # se asigna al crear el servidor

    # ------------------------------------------------------------------ utilidades
    def log_message(self, *args):    # silencio en consola; el registro va a archivo sin contenidos
        pass

    def _cabeceras_seguridad(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Permissions-Policy", "camera=(), geolocation=(), microphone=(self)")
        huellas = self.estado.huellas if self.estado else ""
        self.send_header("Content-Security-Policy", CSP.replace("script-src 'self'", f"script-src 'self' {huellas}".rstrip()))

    def responder_json(self, datos, estado: int = 200):
        cuerpo = json.dumps(datos, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(estado)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self._cabeceras_seguridad()
        self.end_headers()
        self.wfile.write(cuerpo)
        self._estado_final = estado

    def leer_cuerpo(self, maximo: int) -> bytes:
        largo = self.headers.get("Content-Length")
        if largo is None or not largo.isdigit():
            raise Error(411, "Falta Content-Length.")
        largo = int(largo)
        if largo > maximo:
            raise Error(413, f"El contenido supera el máximo permitido ({maximo // (1024 * 1024)} MB).")
        return self.rfile.read(largo)

    def leer_json(self) -> dict:
        crudo = self.leer_cuerpo(MAX_JSON)
        if not crudo:
            return {}
        try:
            d = json.loads(crudo.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise Error(400, "JSON no válido.") from exc
        if not isinstance(d, dict):
            raise Error(400, "Se esperaba un objeto JSON.")
        return d

    def _verificar_escritura(self):
        if self.headers.get("X-DINAMO") != "1":
            raise Error(403, "Petición rechazada (falta la cabecera X-DINAMO).")
        origen = self.headers.get("Origin")
        if origen:
            host = self.headers.get("Host", "")
            if urlsplit(origen).netloc != host:
                raise Error(403, "Origen no permitido.")

    def _verificar_token(self):
        if not self.estado.token:
            return
        enviado = self.headers.get("X-DINAMO-TOKEN") or ""
        cookie = self.headers.get("Cookie") or ""
        m = re.search(r"dinamo_token=([^;]+)", cookie)
        if enviado != self.estado.token and (not m or m.group(1) != self.estado.token):
            raise Error(401, "Se requiere el token de acceso de este servidor.")

    def espacio(self, cid: str):
        try:
            return self.estado.gestor.obtener(cid)
        except KeyError as exc:
            raise Error(404, "Conversación no encontrada.") from exc

    # ------------------------------------------------------------------ despacho
    def _despachar(self, metodo: str):
        inicio = time.time()
        self._estado_final = 200
        partes = urlsplit(self.path)
        camino = unquote(partes.path)
        self.query = {k: v[-1] for k, v in parse_qs(partes.query).items()}
        try:
            if camino.startswith("/api/"):
                self._verificar_token()
                if metodo != "GET":
                    self._verificar_escritura()
                for m, patron, nombre in RUTAS:
                    if m == metodo and (coincide := patron.match(camino)):
                        getattr(self, nombre)(*coincide.groups())
                        break
                else:
                    raise Error(404, "Ruta no encontrada.")
            elif metodo == "GET":
                if self.estado.token and self.query.get("token") == self.estado.token:
                    self._cookie = f"dinamo_token={self.estado.token}; HttpOnly; SameSite=Strict; Path=/"
                elif self.estado.token and camino in ("/", "/index.html"):
                    self._verificar_token()
                self._estatico(camino)
            else:
                raise Error(405, "Método no permitido.")
        except Error as exc:
            self.responder_json({"error": exc.mensaje}, exc.estado)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:                          # error inesperado: sin detalles internos al navegador
            print(f"[DINAMO] Error interno en {metodo} {camino}: {type(exc).__name__}: {exc}", file=sys.stderr)
            try:
                self.responder_json({"error": "Error interno del servidor."}, 500)
            except OSError:
                pass
        finally:
            self.estado.anotar(metodo, camino, self._estado_final, (time.time() - inicio) * 1000)

    def do_GET(self):
        self._despachar("GET")

    def do_POST(self):
        self._despachar("POST")

    def do_DELETE(self):
        self._despachar("DELETE")

    # ------------------------------------------------------------------ estáticos
    def _estatico(self, camino: str):
        if camino in ("", "/"):
            camino = "/index.html"
        relativo = camino.lstrip("/")
        if any(p.startswith(".") for p in relativo.split("/")) or "\\" in relativo or "\x00" in relativo:
            raise Error(404, "No encontrado.")
        destino = (self.estado.frontend / relativo).resolve()
        if not destino.is_relative_to(self.estado.frontend) or not destino.is_file() \
                or destino.suffix.lower() not in ESTATICOS:
            raise Error(404, "No encontrado.")
        datos = destino.read_bytes()
        tipo = mimetypes.guess_type(destino.name)[0] or "application/octet-stream"
        if destino.suffix in (".js", ".mjs"):
            tipo = "text/javascript"
        self.send_response(200)
        self.send_header("Content-Type", tipo + ("; charset=utf-8" if tipo.startswith(("text/", "application/json")) else ""))
        self.send_header("Content-Length", str(len(datos)))
        self.send_header("Cache-Control", "no-cache")
        if getattr(self, "_cookie", None):
            self.send_header("Set-Cookie", self._cookie)
        self._cabeceras_seguridad()
        self.end_headers()
        self.wfile.write(datos)

    # ------------------------------------------------------------------ API: estado
    @ruta("GET", r"/api/estado")
    def api_estado(self):
        llm = self.estado.llm(forzar=self.query.get("forzar") == "1")
        self.responder_json({
            "version": VERSION,
            "llm": llm.describir() if llm else None,
            "llm_navegador": llm is None,
            "privacidad": ("El modelo de lenguaje es local: tus datos no salen del equipo para redactar."
                           if llm and not llm.nube else
                           f"Atención: las preguntas y el material relevante se envían a {llm.etiqueta} para redactar."
                           if llm else "Sin modelo en el servidor: la redacción la hará la IA de tu navegador (local)."),
            "investigacion": "Las búsquedas web envían el texto de la consulta (no tus archivos) al buscador.",
        })

    @ruta("GET", r"/api/integraciones")
    def api_integraciones(self):
        from dinamo.investigacion import integraciones
        self.responder_json({"integraciones": integraciones(comprobar=self.query.get("comprobar") == "1")})

    @ruta("GET", r"/api/paises")
    def api_paises(self):
        from dinamo.investigacion import INDICADORES, PAIS_REFERENCIA_SUGERIDO, PAISES
        self.responder_json({"paises": PAISES, "referencia_sugerida": PAIS_REFERENCIA_SUGERIDO,
                             "indicadores": {k: {"nombre": v[0], "unidad": v[1]} for k, v in INDICADORES.items()}})

    # ------------------------------------------------------------------ API: conversaciones
    @ruta("GET", r"/api/conversaciones")
    def api_listar(self):
        self.responder_json({"conversaciones": self.estado.gestor.listar()})

    @ruta("POST", r"/api/conversaciones")
    def api_crear(self):
        d = self.leer_json()
        e = self.estado.gestor.crear(str(d.get("titulo") or "")[:80] or None)
        self.responder_json(e.a_dict(), 201)

    @ruta("GET", r"/api/conversaciones/([a-f0-9]{12})")
    def api_obtener(self, cid):
        self.responder_json(self.espacio(cid).a_dict())

    @ruta("DELETE", r"/api/conversaciones/([a-f0-9]{12})")
    def api_borrar(self, cid):
        self.espacio(cid)
        self.estado.gestor.borrar(cid)
        self.responder_json({"ok": True})

    @ruta("POST", r"/api/conversaciones/([a-f0-9]{12})/titulo")
    def api_titulo(self, cid):
        e = self.espacio(cid)
        titulo = str(self.leer_json().get("titulo", "")).strip()[:80]
        if not titulo:
            raise Error(400, "El título no puede estar vacío.")
        e.titulo = titulo
        e.guardar()
        self.responder_json(e.ficha())

    @ruta("POST", r"/api/conversaciones/([a-f0-9]{12})/preferencias")
    def api_preferencias(self, cid):
        from dinamo.investigacion import PAISES
        e = self.espacio(cid)
        d = self.leer_json()
        pais = str(d.get("pais_referencia", "")).upper()
        if pais and pais not in PAISES:
            raise Error(400, "País no reconocido.")
        if pais:
            e.preferencias["pais_referencia"] = pais
        else:
            e.preferencias.pop("pais_referencia", None)
        e.guardar()
        self.responder_json({"preferencias": e.preferencias})

    # ------------------------------------------------------------------ archivos
    @ruta("POST", r"/api/conversaciones/([a-f0-9]{12})/archivos")
    def api_subir(self, cid):
        e = self.espacio(cid)
        nombre = unquote(self.headers.get("X-Nombre-Archivo", ""))
        if not nombre:
            raise Error(400, "Falta el nombre del archivo (cabecera X-Nombre-Archivo).")
        contenido = self.leer_cuerpo(MAX_SUBIDA)
        try:
            ficha = e.agregar_archivo(nombre, contenido)
        except ValueError as exc:
            raise Error(400, str(exc)) from exc
        self.responder_json({"archivo": ficha, "archivos": e.archivos}, 201)

    @ruta("DELETE", r"/api/conversaciones/([a-f0-9]{12})/archivos/(.+)")
    def api_quitar(self, cid, nombre):
        e = self.espacio(cid)
        try:
            e.quitar_archivo(nombre)
        except KeyError as exc:
            raise Error(404, "Archivo no encontrado.") from exc
        self.responder_json({"archivos": e.archivos})

    @ruta("GET", r"/api/conversaciones/([a-f0-9]{12})/tablas/([\w\-]+)/vista")
    def api_vista(self, cid, tabla):
        e = self.espacio(cid)
        try:
            filas = int(self.query.get("filas", "20"))
            self.responder_json(e.vista_previa(tabla, filas))
        except (KeyError, ValueError) as exc:
            raise Error(404, "Tabla no encontrada.") from exc

    @ruta("GET", r"/api/conversaciones/([a-f0-9]{12})/descargas/(archivos|scripts)/([^/]+)")
    def api_descargar(self, cid, carpeta, nombre):
        from dinamo.conversacion import nombre_seguro
        e = self.espacio(cid)
        base = (e.carpeta / carpeta).resolve()
        destino = (base / nombre_seguro(nombre)).resolve()
        if not destino.is_relative_to(base) or not destino.is_file():
            raise Error(404, "Archivo no encontrado.")
        datos = destino.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/x-python; charset=utf-8" if destino.suffix == ".py"
                         else (mimetypes.guess_type(destino.name)[0] or "application/octet-stream"))
        self.send_header("Content-Disposition", f'attachment; filename="{destino.name}"')
        self.send_header("Content-Length", str(len(datos)))
        self._cabeceras_seguridad()
        self.end_headers()
        self.wfile.write(datos)

    # ------------------------------------------------------------------ mensajes (streaming NDJSON)
    @ruta("POST", r"/api/conversaciones/([a-f0-9]{12})/mensajes")
    def api_mensaje(self, cid):
        from dinamo.orquestador import procesar
        e = self.espacio(cid)
        d = self.leer_json()
        texto = str(d.get("texto", ""))[:8000]
        if not texto.strip():
            raise Error(400, "El mensaje está vacío.")
        llm = self.estado.llm()
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Connection", "close")
        self._cabeceras_seguridad()
        self.end_headers()
        self.close_connection = True
        with e.candado:
            try:
                for evento in procesar(e, texto, llm=llm, llm_en_navegador=bool(d.get("llm_navegador")) and llm is None,
                                       persona=describir_persona(d.get("perfil"))):
                    self.wfile.write((json.dumps(evento, ensure_ascii=False, default=str) + "\n").encode("utf-8"))
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return
            except Exception as exc:
                print(f"[DINAMO] Error procesando mensaje: {type(exc).__name__}: {exc}", file=sys.stderr)
                self.wfile.write((json.dumps({"tipo": "error", "mensaje": "Ocurrió un error al procesar el mensaje."},
                                             ensure_ascii=False) + "\n").encode("utf-8"))

    @ruta("POST", r"/api/conversaciones/([a-f0-9]{12})/mensajes/([a-f0-9]{10})/completar")
    def api_completar(self, cid, mid):
        from dinamo.orquestador import completar_desde_navegador
        e = self.espacio(cid)
        try:
            m = completar_desde_navegador(e, mid, str(self.leer_json().get("texto", "")))
        except KeyError as exc:
            raise Error(404, "Mensaje pendiente no encontrado.") from exc
        self.responder_json({"mensaje": m})

    # ------------------------------------------------------------------ investigación directa
    @ruta("POST", r"/api/conversaciones/([a-f0-9]{12})/investigacion")
    def api_investigar(self, cid):
        from dinamo.investigacion import MODOS, investigar
        e = self.espacio(cid)
        d = self.leer_json()
        modo = d.get("modo", "web")
        consulta = str(d.get("consulta", "")).strip()[:300]
        if modo not in MODOS:
            raise Error(400, "Modo de investigación no válido.")
        if not consulta and modo != "estadisticas":
            raise Error(400, "Escribe qué quieres investigar.")
        paises = [str(p).upper() for p in d.get("paises") or []][:8]
        ref = e.preferencias.get("pais_referencia")
        if modo == "estadisticas" and ref and ref not in paises and d.get("incluir_referencia", True):
            paises.append(ref)
        inv = investigar(consulta or "indicador", modo=modo, consulta=consulta or None, paises=paises or None,
                         indicador=d.get("indicador") or None)
        if inv.evidencias:
            e.brain.evidencias.agregar(inv.evidencias)
        guardada = e.guardar_investigacion(inv.a_dict())
        self.responder_json(guardada)

    @ruta("POST", r"/api/conversaciones/([a-f0-9]{12})/investigaciones/([a-f0-9]{8})/guardar")
    def api_guardar_inv(self, cid, iid):
        e = self.espacio(cid)
        valor = bool(self.leer_json().get("guardada", True))
        for inv in e.investigaciones:
            if inv["id"] == iid:
                inv["guardada"] = valor
                e.guardar()
                return self.responder_json({"id": iid, "guardada": valor})
        raise Error(404, "Investigación no encontrada.")

    # ------------------------------------------------------------------ memoria
    @ruta("POST", r"/api/conversaciones/([a-f0-9]{12})/memoria")
    def api_recordar(self, cid):
        e = self.espacio(cid)
        hecho = str(self.leer_json().get("hecho", "")).strip()
        if not hecho:
            raise Error(400, "Escribe qué debo recordar.")
        self.responder_json(e.recordar(hecho), 201)

    @ruta("DELETE", r"/api/conversaciones/([a-f0-9]{12})/memoria/([a-f0-9]{8})")
    def api_olvidar(self, cid, mid):
        e = self.espacio(cid)
        e.olvidar(mid)
        self.responder_json({"memoria": e.memoria})

    # ------------------------------------------------------------------ limpieza
    @ruta("POST", r"/api/conversaciones/([a-f0-9]{12})/limpieza/proponer")
    def api_limpieza_proponer(self, cid):
        e = self.espacio(cid)
        try:
            self.responder_json(e.proponer_limpieza(str(self.leer_json().get("archivo", ""))))
        except KeyError as exc:
            raise Error(404, "Archivo no encontrado.") from exc
        except ValueError as exc:
            raise Error(400, str(exc)) from exc

    @ruta("POST", r"/api/conversaciones/([a-f0-9]{12})/limpieza/aplicar")
    def api_limpieza_aplicar(self, cid):
        e = self.espacio(cid)
        d = self.leer_json()
        aprobadas = d.get("aprobadas") or {}
        if not isinstance(aprobadas, dict):
            raise Error(400, "Formato de aprobaciones no válido.")
        try:
            self.responder_json(e.aplicar_limpieza(str(d.get("archivo", "")), {str(k): str(v) for k, v in aprobadas.items()}))
        except KeyError as exc:
            raise Error(404, "Archivo no encontrado.") from exc
        except ValueError as exc:
            raise Error(400, str(exc)) from exc


def describir_persona(p) -> str:
    """Nombre, rol y nivel que el usuario escribió en su perfil: cambian el tono, nunca los números."""
    from dinamo.core.contracts import PerfilUsuario
    if not isinstance(p, dict):
        return ""
    nivel = p.get("nivel") if p.get("nivel") in ("general", "directivo", "analista") else "general"
    return PerfilUsuario(nombre=str(p.get("nombre", ""))[:48], rol=str(p.get("rol", ""))[:60], nivel=nivel).describir()


def crear_servidor(host: str = "127.0.0.1", puerto: int = 8765, carpeta_datos: Path | None = None,
                   carpeta_frontend: Path | None = None) -> ThreadingHTTPServer:
    carpeta_datos = Path(carpeta_datos or os.getenv("DINAMO_DATOS", RAIZ / ".dinamo_datos"))
    carpeta_datos.mkdir(parents=True, exist_ok=True)
    estado = Estado(carpeta_datos, Path(carpeta_frontend or RAIZ / "frontend"))
    if host not in ("127.0.0.1", "localhost", "::1") and not estado.token:
        raise SystemExit("Por seguridad, para escuchar fuera de este equipo define DINAMO_TOKEN en el .env.")
    manejador = type("ManejadorDINAMO", (Manejador,), {"estado": estado})
    servidor = ThreadingHTTPServer((host, puerto), manejador)
    servidor.daemon_threads = True
    return servidor


def main() -> None:
    cargar_env(RAIZ / ".env")
    host = os.getenv("DINAMO_HOST", "127.0.0.1")
    puerto = int(os.getenv("DINAMO_PUERTO", "8765"))
    servidor = crear_servidor(host, puerto)
    llm = servidor.RequestHandlerClass.estado.llm()
    print(f"DINAMO Analytics listo en http://{host}:{puerto}")
    print("Modelo de lenguaje del servidor:", f"{llm.etiqueta} · {llm.modelo}" if llm else
          "ninguno (se usará la IA del navegador o respuestas sin redacción)")
    print("Para detener: Ctrl + C")
    if os.getenv("DINAMO_ABRIR_NAVEGADOR", "1") == "1":
        try:
            import webbrowser
            threading.Timer(1.0, lambda: webbrowser.open(f"http://{host}:{puerto}")).start()
        except Exception:
            pass
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")
