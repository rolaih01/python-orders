"""Arranca y supervisa FastAPI y code-server dentro del mismo contenedor."""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

WORKSPACE = Path(os.getenv("CRIXOL_WORKSPACE", "/home/coder/workspace/Proyecto"))
TEMPLATE = Path("/opt/crixol/template/Proyecto")
APP_PORT = os.getenv("CRIXOL_APP_PORT", "8000")
CODE_SERVER = Path("/usr/bin/code-server")

children: list[tuple[str, subprocess.Popen]] = []
_stopping = False


def stop_children(exit_code: int = 0) -> None:
    """Detiene los procesos hijos sin ocultar errores del proceso que falló."""
    global _stopping
    if _stopping:
        return
    _stopping = True

    for _label, process in children:
        if process.poll() is None:
            process.terminate()
    for _label, process in children:
        if process.poll() is None:
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
    raise SystemExit(exit_code)


def handle_signal(signum: int, _frame: object) -> None:
    print(f"[supervisor] Recibida señal {signum}; deteniendo servicios...", flush=True)
    stop_children(0)



def append_managed_block(path: Path, marker: str, block: str) -> None:
    """Añade una configuración administrada sin sobrescribir la del usuario."""
    try:
        current = path.read_text(encoding="utf-8") if path.exists() else ""
    except OSError as exc:
        raise RuntimeError(f"No se pudo leer {path}: {exc}") from exc
    if marker in current:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        if current and not current.endswith("\n"):
            stream.write("\n")
        stream.write(block.rstrip() + "\n")


def ensure_terminal_python_environment() -> None:
    """Hace que las nuevas terminales interactivas usen el venv de la imagen.

    El terminal integrado puede iniciar una shell de login que reconstruya PATH;
    por eso no confiamos únicamente en el ENV PATH del Dockerfile.
    """
    home = Path.home()
    bashrc_marker = "# >>> CRIXOL MANAGED PYTHON ENVIRONMENT >>>"
    bashrc_block = f'''{bashrc_marker}
export VIRTUAL_ENV="/opt/crixol/venv"
export PATH="/opt/crixol/venv/bin:$PATH"
# <<< CRIXOL MANAGED PYTHON ENVIRONMENT <<<'''
    append_managed_block(home / ".bashrc", bashrc_marker, bashrc_block)

    profile_marker = "# >>> CRIXOL LOAD BASHRC >>>"
    profile_block = f'''{profile_marker}
if [ -f "$HOME/.bashrc" ]; then
    . "$HOME/.bashrc"
fi
# <<< CRIXOL LOAD BASHRC <<<'''
    append_managed_block(home / ".profile", profile_marker, profile_block)
    append_managed_block(home / ".bash_profile", profile_marker, profile_block)

def main() -> int:
    print("[supervisor] Iniciando sandbox Crixol...", flush=True)
    print(f"[supervisor] Usuario efectivo: uid={os.getuid()} gid={os.getgid()}", flush=True)
    print(f"[supervisor] Workspace: {WORKSPACE}", flush=True)
    ensure_terminal_python_environment()
    print("[supervisor] Entorno virtual configurado para las nuevas terminales de code-server.", flush=True)

    # El contenedor arranca con WorkingDir=/home/coder (no con WORKSPACE).
    # Así evitamos que Docker cree workspace/Proyecto como root antes de ejecutar
    # este supervisor. El usuario coder crea aquí el árbol de directorios y será
    # su propietario, por lo que podrá editarlo desde code-server.
    # Comprobamos el fichero de entrada real y completamos solo los ficheros que
    # falten, sin sobrescribir cambios que ya existan en un volumen persistente.
    if not (TEMPLATE / "main.py").is_file():
        raise RuntimeError(f"La plantilla no contiene main.py: {TEMPLATE}")

    try:
        WORKSPACE.mkdir(parents=True, exist_ok=True)
    except PermissionError as exc:
        raise RuntimeError(
            f"El usuario uid={os.getuid()} no puede crear {WORKSPACE}. "
            "Comprueba los permisos del volumen montado en /home/coder."
        ) from exc

    if not os.access(WORKSPACE, os.W_OK | os.X_OK):
        raise RuntimeError(
            f"El workspace no permite escritura al usuario uid={os.getuid()}: {WORKSPACE}. "
            "La sandbox debe utilizar un volumen nuevo y WorkingDir=/home/coder."
        )

    if not (WORKSPACE / "main.py").is_file():
        print(f"[supervisor] Copiando plantilla desde {TEMPLATE} a {WORKSPACE}...", flush=True)
        for source in TEMPLATE.rglob("*"):
            relative_path = source.relative_to(TEMPLATE)
            destination = WORKSPACE / relative_path
            if source.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
            elif not destination.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)

    if not (WORKSPACE / "main.py").is_file():
        raise RuntimeError(
            f"No se pudo preparar main.py en {WORKSPACE}. "
            f"Comprueba que la plantilla existe en {TEMPLATE} y que el volumen permite escribir."
        )

    if not CODE_SERVER.is_file():
        raise RuntimeError(f"No se encuentra el ejecutable esperado: {CODE_SERVER}")
    if not os.access(CODE_SERVER, os.X_OK):
        raise RuntimeError(f"El ejecutable no tiene permiso de ejecución: {CODE_SERVER}")

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    app_command = [
        "/opt/crixol/venv/bin/uvicorn",
        "main:app",
        "--host", "0.0.0.0",
        "--port", APP_PORT,
    ]
    print(f"[supervisor] Lanzando FastAPI en 0.0.0.0:{APP_PORT}...", flush=True)
    app = subprocess.Popen(app_command, cwd=WORKSPACE)
    children.append(("FastAPI", app))

    editor_command = [
        str(CODE_SERVER),
        "--bind-addr", "0.0.0.0:8080",
        "--auth", "none",
        "--disable-telemetry",
        str(WORKSPACE),
    ]
    print("[supervisor] Lanzando code-server en 0.0.0.0:8080...", flush=True)
    editor = subprocess.Popen(editor_command, cwd=WORKSPACE)
    children.append(("code-server", editor))
    print("[supervisor] Procesos lanzados. Los logs de ambos aparecen a continuación.", flush=True)

    while True:
        for label, process in children:
            return_code = process.poll()
            if return_code is not None:
                print(
                    f"[supervisor] ERROR: {label} terminó con código {return_code}.",
                    flush=True,
                )
                stop_children(1)
        time.sleep(1)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        print(f"[supervisor] ERROR al iniciar sandbox: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        try:
            stop_children(1)
        except SystemExit:
            raise
        raise SystemExit(1)
