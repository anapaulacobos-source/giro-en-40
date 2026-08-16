# Giro en 40 — fábrica gratuita de YouTube Shorts

Este proyecto crea videos verticales `1080 × 1920` con microhistorias originales, narración en español, texto en pantalla, fondos animados y música procedural. Incluye 31 historias iniciales, elige una distinta cada día y puede subirla a YouTube de forma privada. Si la voz en línea falla, GitHub usa una voz local de respaldo para no perder la publicación.

La idea de canal es **Giro en 40**: historias breves de misterio suave, humor, emoción, fantasía, decisiones y ciencia ficción. Todas terminan con una pregunta para estimular comentarios. Los fondos y la música se crean con código; no se descargan clips ni canciones de terceros.

## ¿Dónde se coloca este código?

La opción recomendada es un **repositorio de GitHub**. GitHub Actions ejecuta el código cada día incluso cuando tu computador está apagado. Google Colab sirve para probarlo manualmente, pero su sesión gratuita se desconecta y no es una buena base para una automatización diaria.

## Lo más importante antes de empezar

- YouTube no garantiza ingresos. Para recibir reparto de anuncios en Shorts necesitas cumplir los requisitos vigentes del Programa de Socios y aprobar la revisión del canal.
- Un canal lleno de videos casi idénticos, repetidos o producidos masivamente puede no monetizar. Por eso este proyecto cambia historia, paleta, composición, ritmo y música, conserva el archivo de cada guion y evita reutilizar material ajeno. Aun así, **revisa cada video antes de publicarlo** y aporta decisiones editoriales propias.
- Los proyectos nuevos y no auditados de YouTube Data API solo pueden subir videos en modo **privado**. El código respeta esa limitación. Puedes revisar el video en YouTube Studio y cambiarlo manualmente a público, o solicitar la auditoría de cumplimiento de la API cuando el canal esté preparado.
- “Para todo público” significa audiencia general. El código declara que el contenido **no está dirigido específicamente a niños**.

## Puesta en marcha sencilla

### 1. Crear el repositorio

1. Crea una cuenta en [GitHub](https://github.com/) si todavía no tienes una.
2. Pulsa **New repository** y llámalo `giro-en-40`.
3. Puede ser público —GitHub Actions es gratuito en repositorios públicos con ejecutores estándar— o privado usando los minutos incluidos en tu plan.
4. Descomprime este paquete y sube **todo su contenido**, incluida la carpeta `.github`.
5. En el repositorio abre **Actions → Short diario — Giro en 40 → Run workflow**.

Al principio, la variable `UPLOAD_TO_YOUTUBE` no existe y el flujo solo genera el MP4. Lo encontrarás al final de la ejecución, en la sección **Artifacts**. Esta es la forma más segura de probarlo.

### 2. Probarlo en tu computador (opcional)

Necesitas Python 3.12 y FFmpeg.

```bash
python -m venv .venv
```

En Windows:

```powershell
.venv\Scripts\activate
pip install -r requirements.txt
python src/daily.py --no-upload --keep-unused
```

En macOS o Linux:

```bash
source .venv/bin/activate
pip install -r requirements.txt
python src/daily.py --no-upload --keep-unused
```

El resultado queda en `output/`. Para una prueba rápida sin conexión ni narración, usa:

```bash
python src/daily.py --no-upload --silent --keep-unused
```

### 3. Conectar tu cuenta de YouTube

1. Entra a [Google Cloud Console](https://console.cloud.google.com/).
2. Crea un proyecto y habilita **YouTube Data API v3**.
3. Configura la pantalla de consentimiento OAuth. Usa tu propia cuenta como usuario de prueba.
4. Crea credenciales OAuth de tipo **Aplicación de escritorio** y descarga el archivo como `client_secrets.json` dentro del proyecto.
5. En tu computador ejecuta:

```bash
python src/authorize_youtube.py
```

6. Inicia sesión en la cuenta que administra tu canal y acepta el permiso de subida.
7. El programa mostrará tres valores. En GitHub abre **Settings → Secrets and variables → Actions → Secrets** y crea:
   - `YOUTUBE_CLIENT_ID`
   - `YOUTUBE_CLIENT_SECRET`
   - `YOUTUBE_REFRESH_TOKEN`
8. En la pestaña **Variables** crea:
   - `UPLOAD_TO_YOUTUBE` = `true`
   - `YOUTUBE_PRIVACY` = `private`

No publiques esos tres secretos ni subas `client_secrets.json` al repositorio. Si la aplicación OAuth permanece en estado **Testing**, su token de actualización puede caducar a los siete días. Para una operación estable, revisa el estado de publicación de tu aplicación OAuth; esto es distinto de la auditoría que exige YouTube para que las subidas de la API puedan ser públicas.

### 4. Horario

El archivo `.github/workflows/daily-short.yml` ejecuta el proyecto todos los días a las **08:05 en la zona America/Santiago**. Para cambiar la hora, edita:

```yaml
schedule:
  - cron: "5 8 * * *"
    timezone: "America/Santiago"
```

GitHub puede iniciar los trabajos programados con algunos minutos de retraso. También puedes generar un video cuando quieras con **Run workflow**.

## Historias automáticas después del día 31

Las primeras 31 están en `content/stories.json`. La opción de mayor control editorial es agregar nuevas historias a ese archivo cada mes.

Como alternativa, puedes crear una clave en [Google AI Studio](https://aistudio.google.com/apikey), guardarla como secreto `GEMINI_API_KEY` y dejar que el sistema prepare una historia nueva cuando se acabe la cola. El borrador se guarda en `content/generated/` y pasa controles básicos de estructura y similitud. El nivel gratuito, los modelos disponibles y sus límites pueden cambiar; además, el contenido enviado a un nivel gratuito puede usarse para mejorar productos de Google. No uses información privada en los prompts.

## Personalización rápida

- Nombre del canal y etiqueta: `config.json`.
- Voz: variable `VOICE`. Para ver voces disponibles, ejecuta `edge-tts --list-voices`.
- Velocidad: variable `VOICE_RATE`, por ejemplo `+4%` o `+10%`.
- Historias: `content/stories.json`.
- Colores por categoría: diccionario `PALETTES` en `src/render_video.py`.
- Privacidad de YouTube: variable `YOUTUBE_PRIVACY`. Mantén `private` mientras tu proyecto API no haya aprobado la auditoría.

## Rutina editorial recomendada

1. Deja que el sistema genere y suba los videos como privados.
2. Una vez por semana, revisa siete videos en YouTube Studio.
3. Corrige títulos o narración si algo no suena natural.
4. Programa un Short por día y responde comentarios durante la primera hora disponible.
5. A los 30 días, conserva las categorías con mejor retención y abandona las que no funcionan.

No compres vistas ni suscriptores y no publiques muchas variaciones del mismo video. La meta inicial no es una cifra diaria de dinero: es encontrar un formato que logre que la gente se detenga, vea hasta el final y vuelva al canal.
