#!/usr/bin/env python3
"""
Revisa una lista de webs (urls.json), compara su contenido con la última
captura guardada y, si hay cambios, actualiza el historial (docs/data) y
opcionalmente avisa por Telegram.

Pensado para ejecutarse desde GitHub Actions con cron, pero funciona igual
en local: `python scripts/check_sites.py`
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
SNAPSHOTS_DIR = os.path.join(DATA_DIR, "snapshots")
SITES_FILE = os.path.join(DATA_DIR, "sites.json")
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")

MAX_HISTORY_ENTRIES = 300
MAX_DIFF_LINES = 60
REQUEST_TIMEOUT = 20
USER_AGENT = "website-watcher-bot/1.0 (+https://github.com)"

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "site"


def load_json(path, default):
    if not os.path.exists(path):
        return default

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fetch_text(url: str, selector: str | None) -> str:
    resp = requests.get(
        url,
        timeout=REQUEST_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
    )

    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    node = soup.select_one(selector) if selector else soup.body or soup

    text = node.get_text(separator="\n")

    # Normaliza espacios en blanco para no detectar "cambios" que son solo
    # diferencias de formato/espaciado.
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]

    return "\n".join(lines)


def notify_telegram(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "disable_web_page_preview": True,
            },
            timeout=REQUEST_TIMEOUT,
        )

    except requests.RequestException as exc:
        print(
            f"[aviso] No se pudo notificar por Telegram: {exc}",
            file=sys.stderr,
        )


def main():
    sites_config = load_json(URLS_FILE, [])

    if not sites_config:
        print("urls.json está vacío. No hay nada que revisar.")
        return

    sites_status = load_json(SITES_FILE, {})
    history = load_json(HISTORY_FILE, [])

    # ============================================================
    # IMPORTANTE:
    # urls.json es la fuente de verdad.
    #
    # Si una web se elimina de urls.json, también se elimina de
    # sites.json y del historial que utiliza la web.
    # ============================================================

    active_slugs = {
        slugify(site["name"])
        for site in sites_config
    }

    # Eliminar webs que ya no existen en urls.json
    sites_status = {
        slug: data
        for slug, data in sites_status.items()
        if slug in active_slugs
    }

    # Eliminar del historial las webs que ya no existen en urls.json
    history = [
        entry
        for entry in history
        if entry.get("slug") in active_slugs
    ]

    os.makedirs(SNAPSHOTS_DIR, exist_ok=True)

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    changed_messages = []

    for site in sites_config:
        name = site["name"]
        url = site["url"]
        selector = site.get("selector")

        slug = slugify(name)

        snapshot_path = os.path.join(
            SNAPSHOTS_DIR,
            f"{slug}.txt"
        )

        try:
            new_text = fetch_text(url, selector)

        except Exception as exc:  # noqa: BLE001
            print(
                f"[error] {name} ({url}): {exc}",
                file=sys.stderr,
            )

            sites_status[slug] = {
                **sites_status.get(slug, {}),
                "name": name,
                "url": url,
                "last_checked": now,
                "last_status": "error",
                "last_error": str(exc),
            }

            continue

        new_hash = hashlib.sha256(
            new_text.encode("utf-8")
        ).hexdigest()

        old_text = None

        old_hash = sites_status.get(slug, {}).get("hash")

        if os.path.exists(snapshot_path):
            with open(
                snapshot_path,
                "r",
                encoding="utf-8"
            ) as f:
                old_text = f.read()

        if old_text is None:
            # Primera vez que vemos esta web:
            # solo guardamos la línea base.
            status = "primera-captura"

        elif new_hash != old_hash:
            status = "cambio-detectado"

            diff = list(
                difflib.unified_diff(
                    old_text.splitlines(),
                    new_text.splitlines(),
                    lineterm="",
                    n=1,
                )
            )[:MAX_DIFF_LINES]

            entry = {
                "id": f"{slug}-{now}",
                "slug": slug,
                "name": name,
                "url": url,
                "timestamp": now,
                "diff": diff,
            }

            history.insert(0, entry)

            changed_messages.append(
                f'🔔 Cambio detectado en "{name}"\n'
                f"{url}\n"
                f"{now}"
            )

        else:
            status = "sin-cambios"

        with open(
            snapshot_path,
            "w",
            encoding="utf-8"
        ) as f:
            f.write(new_text)

        sites_status[slug] = {
            "name": name,
            "url": url,
            "hash": new_hash,
            "last_checked": now,
            "last_status": status,
            "last_change_at": (
                now
                if status == "cambio-detectado"
                else sites_status.get(slug, {}).get(
                    "last_change_at"
                )
            ),
        }

    # Limitar el historial al máximo configurado
    history = history[:MAX_HISTORY_ENTRIES]

    # Guardar los datos actualizados
    save_json(SITES_FILE, sites_status)
    save_json(HISTORY_FILE, history)

    if changed_messages:
        notify_telegram(
            "\n\n".join(changed_messages)
        )

    print(
        f"Revisión completa. "
        f"{len(changed_messages)} cambio(s) detectado(s)."
    )


if __name__ == "__main__":
    main()
