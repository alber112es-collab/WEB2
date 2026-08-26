# Centinela — vigilante de webs con GitHub

Revisa periódicamente una lista de webs, detecta cambios en su contenido y
te los muestra en un panel (GitHub Pages) y, si quieres, te avisa por
Telegram. Todo corre gratis en GitHub Actions, sin servidor propio.

## Cómo funciona

1. `urls.json` define qué webs vigilar.
2. Un workflow de **GitHub Actions** (`.github/workflows/watch.yml`) ejecuta
   `scripts/check_sites.py` cada 30 minutos.
3. El script descarga cada web, extrae su texto visible, lo compara con la
   última captura guardada y, si cambió, anota la diferencia en
   `docs/data/history.json`.
4. **GitHub Pages** sirve `docs/index.html`, que lee esos JSON y muestra el
   estado de cada web + el historial de cambios.
5. (Opcional) Si configuras un bot de Telegram, recibes un mensaje cada vez
   que se detecta un cambio.

## Puesta en marcha

### 1. Crea el repositorio

Sube esta carpeta tal cual a un repositorio nuevo en GitHub (público o
privado, funciona igual).

```bash
git init
git add .
git commit -m "Primer commit: Centinela"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/TU_REPO.git
git push -u origin main
```

### 2. Configura las webs a vigilar

Edita `urls.json`:

```json
[
  { "name": "Mi web favorita", "url": "https://ejemplo.com/noticias", "selector": null }
]
```

- `selector` es opcional: un selector CSS (ej. `"#contenido"` o
  `"main article"`) para fijarte solo en una parte de la página y evitar
  "cambios" falsos por banners, publicidad o fecha/hora en el pie. Si lo
  dejas en `null`, se compara todo el `<body>`.

### 3. Activa GitHub Pages

En el repo: **Settings → Pages → Build and deployment → Source: Deploy from
a branch**, rama `main`, carpeta `/docs`. Guarda. En un par de minutos tu
panel estará en `https://TU_USUARIO.github.io/TU_REPO/`.

### 4. Activa el workflow

En **Settings → Actions → General**, asegúrate de que las Actions estén
habilitadas. El workflow ya está programado (`cron: */30 * * * *`), pero
puedes lanzarlo a mano la primera vez desde la pestaña **Actions → Vigilar
webs → Run workflow** para generar la primera captura.

### 5. (Opcional) Notificaciones por Telegram

1. Habla con [@BotFather](https://t.me/BotFather) en Telegram, crea un bot
   con `/newbot` y guarda el **token** que te da.
2. Escríbele algo a tu bot recién creado (para "activarlo").
3. Visita `https://api.telegram.org/bot<TU_TOKEN>/getUpdates` y busca el
   campo `"chat":{"id": ...}` — ese número es tu **chat id**.
4. En el repo: **Settings → Secrets and variables → Actions → New repository
   secret**, crea:
   - `TELEGRAM_BOT_TOKEN` con el token del bot.
   - `TELEGRAM_CHAT_ID` con tu chat id.

A partir de ahí, cada cambio detectado te llega también por Telegram.

## Ajustar la frecuencia

En `.github/workflows/watch.yml`, cambia la línea `cron`. GitHub no garantiza
ejecuciones más frecuentes que cada 5 minutos, y en la práctica puede
retrasarse unos minutos en horas de mucho tráfico en Actions.

## Probar en local

```bash
pip install -r requirements.txt
python scripts/check_sites.py
```

Esto genera/actualiza `docs/data/sites.json`, `docs/data/history.json` y las
capturas en `docs/data/snapshots/`. Abre `docs/index.html` con un servidor
local (por ejemplo `python -m http.server` dentro de `docs/`) para verlo,
ya que al abrirlo como archivo local el `fetch()` puede bloquearse por CORS.

## Estructura del proyecto

```
website-watcher/
├── urls.json                 # qué webs vigilar
├── requirements.txt
├── scripts/check_sites.py    # lógica de chequeo y diff
├── .github/workflows/watch.yml
└── docs/                     # esto es lo que sirve GitHub Pages
    ├── index.html            # panel
    └── data/
        ├── sites.json        # estado actual de cada web
        ├── history.json      # historial de cambios con diff
        └── snapshots/        # última copia de texto de cada web
```
