# API de pedidos (proyecto base de ejemplo)

Esta API FastAPI + SQLite es el proyecto que se copia al workspace de la sandbox. El editor y la API corren en **contenedores separados** que comparten el mismo volumen de trabajo, así que puedes editar en code-server y ver los cambios recargados en la API.

## Arquitectura de la sandbox

- **Editor**: code-server en el puerto interno `8080`, con `/home/coder` montado desde un volumen.
- **API**: `uvicorn main:app --host 0.0.0.0 --port 8000 --reload` en otro contenedor, usando el mismo volumen.
- **Workspace**: `/home/coder/workspace/Proyecto`, propiedad de `1000:1000`.
- **Datos**: SQLite en `data/orders.db`, dentro del workspace, por lo que persisten mientras exista el volumen.

El contenedor de la API se reinicia solo si el proceso falla (`restart: on-failure`). No hay un supervisor que arranque ambos servicios: el orquestador crea un contenedor para cada uno.

## Python y dependencias dentro del contenedor

La imagen de desarrollo instala las dependencias de `requirements.txt` en un entorno virtual (`/opt/crixol/venv`). Ese entorno está en el `PATH` del editor y de la API, así que `python3`, `pip` y `uvicorn` resuelven a los ejecutables correctos sin activar nada manualmente.

Puedes comprobarlo desde el terminal del editor:

```bash
which python3
python3 -c "import fastapi; print(fastapi.__version__)"
which uvicorn
```

El editor y la API son contenedores distintos: un `pip install` en el terminal del editor no modifica el entorno virtual de la API. Úsalo solo para pruebas dentro de un contenedor concreto:

```bash
pip install <paquete>
```

Para dependencias de la aplicación, edita `base-apps/python-orders/requirements.txt` y reconstruye la imagen (el cambio sí queda en la imagen y lo usan ambos contenedores):

```bash
# en el host, desde la raíz del repositorio
python run.py --app python-orders --rebuild
```

## Ejecutar y recargar

La API ya está arrancada cuando la sandbox termina de crear. `uvicorn --reload` vigila los archivos del workspace: al guardar `main.py` se recarga automáticamente.

- `GET /health`: comprobación de disponibilidad.
- `GET /orders`: lista los pedidos no eliminados.
- `GET /orders?include_deleted=true`: lista todos los pedidos.
- `GET /orders/{id}`: obtiene un pedido.
- `POST /orders`: crea un pedido (`{"customer":"Katherine Johnson","total":42.5}`).
- `DELETE /orders/{id}`: actualmente elimina físicamente el pedido.

La documentación interactiva de FastAPI está en `/docs`. La URL pública de la API la imprime `run.py` al crear la sandbox; también aparece en `python run.py --list`.

## Prueba de modificación

Como ejercicio de ejemplo, modifica `DELETE /orders/{id}` para que establezca `deleted_at` en lugar de borrar la fila. Comprueba también que los pedidos eliminados no aparezcan en `GET /orders`, pero sí con `include_deleted=true`.

Tras guardar, la API se recarga sola. Si el proceso no arranca por un error de sintaxis, revisa los logs:

```bash
python run.py --logs <sandbox>
```

La base SQLite se guarda en `data/orders.db`, dentro del workspace montado en un volumen Docker. `--stop` y `--remove` conservan el volumen; `--remove --purge-volumes` lo borra.
