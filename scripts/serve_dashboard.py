"""Levantar API y Vue con un comando. Ctrl+C detiene solo los procesos creados."""
import argparse
import shutil
import socket
import subprocess
import sys
import time

from utils.config import PROJECT_ROOT


def port_busy(port):
    with socket.socket() as sock:
        sock.settimeout(.3)
        return sock.connect_ex(('127.0.0.1', port)) == 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--production', action='store_true', help='Compilar y servir web+API en :8080')
    args = parser.parse_args()
    node = shutil.which('node')
    vite = PROJECT_ROOT/'web'/'node_modules'/'vite'/'bin'/'vite.js'
    if not node or not vite.is_file():
        raise SystemExit('Instalar Node.js y ejecutar npm.cmd ci dentro de web/.')
    ports = [8080] if args.production else [8000,8080]
    if any(port_busy(port) for port in ports):
        raise SystemExit('Ya existe un servicio en :8000 o :8080. Revisa si el dashboard ya está en http://127.0.0.1:8080 .')
    if args.production:
        subprocess.run([node,str(vite),'build'],cwd=PROJECT_ROOT/'web',check=True)
    processes = []
    try:
        processes.append(subprocess.Popen([sys.executable,'-m','uvicorn','api.api_seguridad:app','--host','127.0.0.1',
                                           '--port','8080' if args.production else '8000'],cwd=PROJECT_ROOT))
        if not args.production:
            processes.append(subprocess.Popen([node,str(vite),'--host','127.0.0.1','--port','8080','--strictPort'],cwd=PROJECT_ROOT/'web'))
        print('Dashboard: http://127.0.0.1:8080 · Ctrl+C para detener.',flush=True)
        while all(process.poll() is None for process in processes):
            time.sleep(.5)
    except KeyboardInterrupt:
        pass
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait()


if __name__ == '__main__':
    main()
