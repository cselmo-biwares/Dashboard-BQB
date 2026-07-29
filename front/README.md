# Dashboard BQB — front (testing)

Front mínimo en React + Vite para ir probando la API de `Dashboard-BQB` mientras se desarrolla.
No es el front final (ese va en un repo aparte) — esto es para iterar rápido contra la API local.

## Setup

Necesitás Node.js instalado (18+). Si no lo tenés:

```bash
# via nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
nvm install --lts
```

Después:

```bash
cd front
cp .env.example .env   # ajustá VITE_API_URL si la API no corre en :8001
npm install
npm run dev
```

Abre en `http://localhost:5173`.

## Requisitos del lado de la API

- La API (`Dashboard-BQB`) tiene que estar corriendo y con `CORS_ORIGINS` incluyendo
  `http://localhost:5173` en su `.env` (ya viene seteado así por default).
- Recomendado correr la API en un puerto distinto a 5173/8000 si tenés el Conversation
  Manager u otros servicios ocupando esos puertos, ej. `--port 8001`.

## Pantallas

- **Overview**: KPIs + volumen de conversaciones por día/semana, filtrable por canal.
- **Temas**: árbol navegable, detalle de documentos/conversaciones por hoja, ranking de
  resolución (peor primero, con flag de "sin documentación"), y reestructuración del árbol.
- **Documentos**: alta de documentos (clasificación contra el árbol) y borrado.
- **Ingesta**: disparar `/ingestion/update` y ver el estado de la corrida.
- **Conversación**: buscar una conversación por id y ver transcripción + clasificación.
