# Dashboard BQB
Dashboard para buquebús

## Ejecución
Se puede levantar la aplicación corriendo:
```commandline
uvicorn app.main:app --env-file .env --log-config logging-config.yaml
```
    
Donde `.env` es un archivo basado en `.env.example`


## Settings
Para configurar settings de la aplicación se utiliza [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
que recupera automáticamente variables del environment. Adicionalmente revisar la documentación de [integración con Fastapi](https://fastapi.tiangolo.com/advanced/settings/)


## OpenTelemetry

### Exporting
Seteada para funcionar con OTLP gRPC en el archivo `app/otel.py`. 

### Configuración
Idealmente, toda configuración debe ser pasada por variable de entorno como recomienda la [documentación](https://opentelemetry-python.readthedocs.io/en/latest/sdk/environment_variables.html).

### Trazas HTTP
Se utiliza la integración de [instrumentación de FastAPI](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/fastapi/fastapi.html).

### Logs
Se agrega un handler extra para exportar OTLP en formato json, agregando además `trace` y `span` si está presente.
No modifica la configuración root.

Alcanza con utilizar el módulo `logging` de python "normalmente" haciendo `logging.get_logger(__name__)` 

### Metricas
Alcanza con instanciar un `meter`: `opentelemetry.metrics.get_meter(__name__)`. Referencia completa [aquí](https://opentelemetry.io/docs/languages/python/instrumentation/#metrics).

### Testing
Para validar el correcto funcionamiento de telemetría OTEL, se puede levantar el siguiente [stack de observabilidad local](https://github.com/Biwares-AI/observability-stack-compose/tree/develop).

Configurar la variable `OTEL_EXPORTER_OTLP_ENDPOINT` acordemente (e.g. `http://localhost:4317`)

Si no se encuentra disponible el `otel-collector`, se observará que el sistema telemetría quedará reintentando indefinidamente 
el export de señales. Esto puede ser evitado localmente configurando la variable de entorno `OTEL_SDK_DISABLED=true` para que no se exporte ninguna señal OTEL.


## Development
Para desarrollar en el proyecto es necesario crear un ambiente local de python (e.g. usando `virtualenv`) e instalando
las librerías.
Seguir los siguientes pasos:

1. Crear un nuevo ambiente de python
2. Instalar las librerías

       pip install --index-url=https://us-east1-python.pkg.dev/biwares-ai/pywares/simple --verbose -r requirements-dev.txt
3. Instalar los `pre-commit`s con `pre-commit install`

**Nota**: Usamos `ruff` para *linting* y *formatting*. Agregando el *pre-commit hook* se puede commitear de forma segura
código que ya será aprobado por las acciones automáticas en github.

**Nota**: para gestionar el acceso al registry de google leer [la documentación](https://biwares.atlassian.net/wiki/spaces/General/pages/277544961/Pywares#Acceso-a-librer%C3%ADas-usando-PIP)

### Linting
```console
ruff check --fix
```
This will run linting and do [safe fixes](https://docs.astral.sh/ruff/linter/#fix-safety)

### Formatting
```console
ruff format
```


### Testing de la aplicación
Utilizamos las librerias `pytest` y `pytest-cov` para correr tests.
Principalmente se deben escribir tests de aplicación utilizando `fastapi.testclient.TestClient`. [Documentación](https://fastapi.tiangolo.com/tutorial/testing/)

```console
pytest --cov=app --cov-report=html tests/
```
    
