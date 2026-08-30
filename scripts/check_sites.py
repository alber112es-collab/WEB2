#!/usr/bin/env python3
"""
Revisa una lista de webs (urls.json), compara su contenido con la última
captura guardada y, si hay cambios, actualiza el historial (docs/data) y
opcionalmente avisa por Telegram.

Pensado para ejecutarse desde GitHub Actions con cron, pero funciona igual
en local:

    python scripts/check_sites.py


SELECTORES ESPECIALES
=====================

Además de selectores CSS normales, urls.json puede utilizar:

    "selector": "text:Escala Auxiliar de Administración"

o:

    "selector": "text:Tablón de anuncios"

Esto permite vigilar una parte concreta de una página sin comparar
todo el contenido.

Ejemplo UniRioja:

    "selector": "text:Escala Auxiliar de Administración"

Detectará:

    Escala Auxiliar de Administración
    (último llamamiento: n.º 108)

y posteriormente:

    Escala Auxiliar de Administración
    (último llamamiento: n.º 109)


Ejemplo Nájera:

    "selector": "text:Tablón de anuncios"

De esta forma se intenta vigilar únicamente el bloque del Tablón de
anuncios y no la fecha/hora dinámica de la página.
"""

import difflib
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

URLS_FILE = os.path.join(ROOT, "urls.json")

DATA_DIR = os.path.join(ROOT, "docs", "data")

SNAPSHOTS_DIR = os.path.join(
    DATA_DIR,
    "snapshots",
)

SITES_FILE = os.path.join(
    DATA_DIR,
    "sites.json",
)

HISTORY_FILE = os.path.join(
    DATA_DIR,
    "history.json",
)


MAX_HISTORY_ENTRIES = 300
MAX_DIFF_LINES = 60
REQUEST_TIMEOUT = 20

USER_AGENT = (
    "website-watcher-bot/1.0 "
    "(+https://github.com)"
)


TELEGRAM_BOT_TOKEN = os.environ.get(
    "TELEGRAM_BOT_TOKEN"
)

TELEGRAM_CHAT_ID = os.environ.get(
    "TELEGRAM_CHAT_ID"
)


# ============================================================
# UTILIDADES
# ============================================================

def slugify(text: str) -> str:
    """
    Convierte el nombre de una web en un identificador seguro.
    """

    text = text.strip().lower()

    text = re.sub(
        r"[^a-z0-9]+",
        "-",
        text,
    )

    return (
        text.strip("-")
        or "site"
    )


def load_json(path, default):
    """
    Carga un JSON.
    Si no existe, devuelve el valor indicado en default.
    """

    if not os.path.exists(path):
        return default

    with open(
        path,
        "r",
        encoding="utf-8",
    ) as f:
        return json.load(f)


def save_json(path, data):
    """
    Guarda un JSON creando previamente el directorio.
    """

    os.makedirs(
        os.path.dirname(path),
        exist_ok=True,
    )

    with open(
        path,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
        )


# ============================================================
# NORMALIZACIÓN DE TEXTO
# ============================================================

def normalize_text(text: str) -> str:
    """
    Normaliza espacios y líneas.

    Esto evita falsos positivos provocados únicamente por
    espacios, saltos de línea o formato HTML.
    """

    lines = []

    for line in text.splitlines():

        line = re.sub(
            r"\s+",
            " ",
            line,
        ).strip()

        if line:
            lines.append(line)

    return "\n".join(lines)


# ============================================================
# EXTRACCIÓN ESPECIAL POR TEXTO
# ============================================================

def find_element_by_text(
    soup: BeautifulSoup,
    search_text: str,
):
    """
    Busca un elemento que contenga search_text.

    Se utiliza para selectores del tipo:

        text:Escala Auxiliar de Administración

        text:Tablón de anuncios

    Intenta encontrar el contenedor útil más pequeño.
    """

    pattern = re.compile(
        re.escape(search_text),
        re.IGNORECASE,
    )

    matches = soup.find_all(
        string=pattern
    )

    if not matches:
        return None

    # ========================================================
    # PRIMERA ESTRATEGIA
    #
    # Buscar primero elementos típicos de contenido.
    # ========================================================

    preferred_tags = (
        "a",
        "li",
        "article",
        "tr",
        "td",
        "p",
    )

    for match in matches:

        current = match.parent

        while current is not None:

            if current.name in preferred_tags:

                text = current.get_text(
                    " ",
                    strip=True,
                )

                if re.search(
                    re.escape(search_text),
                    text,
                    re.IGNORECASE,
                ):
                    return current

            current = current.parent

    # ========================================================
    # SEGUNDA ESTRATEGIA
    #
    # Si no hemos encontrado un contenedor específico,
    # devolvemos el padre inmediato.
    # ========================================================

    return matches[0].parent


# ============================================================
# EXTRACCIÓN ESPECÍFICA DEL TABLÓN DE NÁJERA
# ============================================================

def extract_najera_board(
    soup: BeautifulSoup,
):
    """
    Intenta localizar el bloque correspondiente al
    "Tablón de anuncios" de Nájera.

    La página contiene elementos dinámicos como fecha y hora.
    Por eso no debemos comparar todo el body.

    Se prueban varias estrategias para encontrar el encabezado
    y posteriormente el contenedor de publicaciones.
    """

    pattern = re.compile(
        r"Tabl[oó]n\s+de\s+anuncios",
        re.IGNORECASE,
    )

    heading = None

    # --------------------------------------------------------
    # Buscar encabezados HTML.
    # --------------------------------------------------------

    for tag in soup.find_all(
        ["h1", "h2", "h3", "h4", "h5", "h6"]
    ):

        text = tag.get_text(
            " ",
            strip=True,
        )

        if pattern.search(text):
            heading = tag
            break

    # --------------------------------------------------------
    # Si no es un heading, buscar cualquier elemento.
    # --------------------------------------------------------

    if heading is None:

        for element in soup.find_all(
            string=pattern
        ):

            heading = element.parent
            break

    if heading is None:
        return None

    # --------------------------------------------------------
    # Intentar encontrar el contenedor del tablón.
    # --------------------------------------------------------

    current = heading

    for _ in range(6):

        if current is None:
            break

        # Si encontramos un contenedor grande, comprobamos
        # si contiene elementos que parecen anuncios.
        if current.name in (
            "section",
            "div",
            "article",
            "main",
        ):

            text = current.get_text(
                "\n",
                strip=True,
            )

            if len(text) > len(
                heading.get_text(
                    " ",
                    strip=True,
                )
            ):

                # Evitamos devolver todo el body.
                if len(text) < 100000:
                    return current

        current = current.parent

    # --------------------------------------------------------
    # Como último recurso devolvemos el padre.
    # --------------------------------------------------------

    return heading.parent


# ============================================================
# FETCH PRINCIPAL
# ============================================================

def fetch_text(
    url: str,
    selector: str | None,
) -> str:

    resp = requests.get(
        url,
        timeout=REQUEST_TIMEOUT,
        headers={
            "User-Agent": USER_AGENT,
        },
    )

    resp.raise_for_status()

    soup = BeautifulSoup(
        resp.text,
        "html.parser",
    )

    # --------------------------------------------------------
    # Eliminar contenido que nunca nos interesa comparar.
    # --------------------------------------------------------

    for tag in soup(
        [
            "script",
            "style",
            "noscript",
        ]
    ):
        tag.decompose()

    # ========================================================
    # SELECTOR ESPECIAL: text:
    # ========================================================

    if selector and selector.startswith(
        "text:"
    ):

        search_text = selector[
            len("text:"):
        ].strip()

        if not search_text:
            raise ValueError(
                "El selector text: está vacío."
            )

        # ----------------------------------------------------
        # NÁJERA
        #
        # Para esta web hacemos una extracción específica
        # del bloque del tablón.
        # ----------------------------------------------------

        if search_text.lower() in (
            "tablón de anuncios",
            "tablon de anuncios",
        ):

            node = extract_najera_board(
                soup
            )

        # ----------------------------------------------------
        # RESTO DE WEBS
        # ----------------------------------------------------

        else:

            node = find_element_by_text(
                soup,
                search_text,
            )

        if node is None:

            raise ValueError(
                f'No se encontró el texto '
                f'"{search_text}" en la página.'
            )

        text = node.get_text(
            separator="\n"
        )

    # ========================================================
    # SELECTOR CSS NORMAL
    # ========================================================

    else:

        node = (
            soup.select_one(selector)
            if selector
            else soup.body or soup
        )

        if node is None:

            raise ValueError(
                f'No se encontró el selector CSS '
                f'"{selector}"'
            )

        text = node.get_text(
            separator="\n"
        )

    # ========================================================
    # NORMALIZAR
    # ========================================================

    return normalize_text(
        text
    )


# ============================================================
# TELEGRAM
# ============================================================

def notify_telegram(
    message: str,
):

    if (
        not TELEGRAM_BOT_TOKEN
        or not TELEGRAM_CHAT_ID
    ):
        return

    try:

        requests.post(
            (
                "https://api.telegram.org/"
                f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            ),
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "disable_web_page_preview": True,
            },
            timeout=REQUEST_TIMEOUT,
        )

    except requests.RequestException as exc:

        print(
            "[aviso] No se pudo notificar "
            f"por Telegram: {exc}",
            file=sys.stderr,
        )


# ============================================================
# MAIN
# ============================================================

def main():

    sites_config = load_json(
        URLS_FILE,
        [],
    )

    if not sites_config:

        print(
            "urls.json está vacío. "
            "No hay nada que revisar."
        )

        return

    sites_status = load_json(
        SITES_FILE,
        {},
    )

    history = load_json(
        HISTORY_FILE,
        [],
    )

    # ========================================================
    # urls.json ES LA FUENTE DE VERDAD
    # ========================================================

    active_slugs = {
        slugify(site["name"])
        for site in sites_config
    }

    # --------------------------------------------------------
    # Eliminar webs que ya no están en urls.json.
    # --------------------------------------------------------

    sites_status = {
        slug: data
        for slug, data in sites_status.items()
        if slug in active_slugs
    }

    # --------------------------------------------------------
    # Eliminar del historial las webs eliminadas.
    # --------------------------------------------------------

    history = [
        entry
        for entry in history
        if entry.get("slug")
        in active_slugs
    ]

    os.makedirs(
        SNAPSHOTS_DIR,
        exist_ok=True,
    )

    now = datetime.now(
        timezone.utc
    ).isoformat(
        timespec="seconds"
    )

    changed_messages = []

    # ========================================================
    # COMPROBAR CADA WEB
    # ========================================================

    for site in sites_config:

        name = site["name"]

        url = site["url"]

        selector = site.get(
            "selector"
        )

        slug = slugify(
            name
        )

        snapshot_path = os.path.join(
            SNAPSHOTS_DIR,
            f"{slug}.txt",
        )

        print(
            f"[check] {name}"
        )

        try:

            new_text = fetch_text(
                url,
                selector,
            )

        except Exception as exc:

            print(
                f"[error] {name} "
                f"({url}): {exc}",
                file=sys.stderr,
            )

            sites_status[slug] = {
                **sites_status.get(
                    slug,
                    {},
                ),
                "name": name,
                "url": url,
                "last_checked": now,
                "last_status": "error",
                "last_error": str(exc),
            }

            continue

        # ====================================================
        # HASH NUEVO
        # ====================================================

        new_hash = hashlib.sha256(
            new_text.encode(
                "utf-8"
            )
        ).hexdigest()

        old_text = None

        old_hash = (
            sites_status
            .get(slug, {})
            .get("hash")
        )

        # ====================================================
        # CARGAR SNAPSHOT ANTERIOR
        # ====================================================

        if os.path.exists(
            snapshot_path
        ):

            with open(
                snapshot_path,
                "r",
                encoding="utf-8",
            ) as f:

                old_text = f.read()

        # ====================================================
        # PRIMERA CAPTURA
        # ====================================================

        if old_text is None:

            status = (
                "primera-captura"
            )

            print(
                f"[info] {name}: "
                "primera captura"
            )

        # ====================================================
        # CAMBIO
        # ====================================================

        elif new_hash != old_hash:

            status = (
                "cambio-detectado"
            )

            diff = list(
                difflib.unified_diff(
                    old_text.splitlines(),
                    new_text.splitlines(),
                    fromfile="anterior",
                    tofile="actual",
                    lineterm="",
                    n=1,
                )
            )

            diff = diff[
                :MAX_DIFF_LINES
            ]

            entry = {
                "id": (
                    f"{slug}-{now}"
                ),
                "slug": slug,
                "name": name,
                "url": url,
                "timestamp": now,
                "diff": diff,
            }

            history.insert(
                0,
                entry,
            )

            # ------------------------------------------------
            # Preparar Telegram.
            # ------------------------------------------------

            diff_text = "\n".join(
                diff[:20]
            )

            changed_messages.append(
                f'🔔 Cambio detectado '
                f'en "{name}"\n\n'
                f"{url}\n\n"
                f"{diff_text}"
            )

            print(
                f"[CAMBIO] {name}"
            )

            print(
                diff_text
            )

        # ====================================================
        # SIN CAMBIOS
        # ====================================================

        else:

            status = (
                "sin-cambios"
            )

            print(
                f"[OK] {name}: "
                "sin cambios"
            )

        # ====================================================
        # GUARDAR SNAPSHOT
        # ====================================================

        with open(
            snapshot_path,
            "w",
            encoding="utf-8",
        ) as f:

            f.write(
                new_text
            )

        # ====================================================
        # ACTUALIZAR ESTADO
        # ====================================================

        sites_status[slug] = {
            "name": name,
            "url": url,
            "hash": new_hash,
            "last_checked": now,
            "last_status": status,
            "last_change_at": (
                now
                if status
                == "cambio-detectado"
                else sites_status
                .get(slug, {})
                .get(
                    "last_change_at"
                )
            ),
        }

    # ========================================================
    # LIMITAR HISTORIAL
    # ========================================================

    history = history[
        :MAX_HISTORY_ENTRIES
    ]

    # ========================================================
    # GUARDAR DATOS
    # ========================================================

    save_json(
        SITES_FILE,
        sites_status,
    )

    save_json(
        HISTORY_FILE,
        history,
    )

    # ========================================================
    # TELEGRAM
    # ========================================================

    if changed_messages:

        notify_telegram(
            "\n\n".join(
                changed_messages
            )
        )

    # ========================================================
    # RESULTADO
    # ========================================================

    print(
        "Revisión completa. "
        f"{len(changed_messages)} "
        "cambio(s) detectado(s)."
    )


if __name__ == "__main__":
    main()
