# Operador Clientes v1

MVP para buscar negocios por sector/zona, detectar cuáles no tienen `websiteUri` asociado en Google Places, puntuarlos y guardarlos como prospectos.

## 1. Preparar

Necesitas Python 3.11+.

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

En `.env` añade una clave de Google Maps Platform con **Places API (New)** habilitada. La clave de OpenAI es opcional; sin ella, el análisis IA funciona en modo demo.

## 2. Ejecutar

```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

Abre `http://localhost:8000`.

## 3. Probar sin claves

La app arranca en modo demo y devuelve prospectos ficticios. Sirve para revisar la interfaz y el flujo.

## 4. Uso real

Al configurar `GOOGLE_PLACES_API_KEY`, las búsquedas usan Text Search (New). La ausencia de `websiteUri` es una señal de que Google no tiene una web asociada; conviene verificar el negocio antes de contactar.

## 5. Instalar en Android

Cuando esté desplegada bajo HTTPS, abre la URL en Chrome > menú > **Añadir a pantalla de inicio / Instalar aplicación**.

## Siguiente versión

- generar una demo web privada para cada prospecto;
- historial de contactos y estadísticas de conversión;
- búsqueda por radio/municipios;
- verificación adicional de presencia web;
- mensajes de captación con aprobación manual;
- notificaciones y seguimiento.
