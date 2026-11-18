"""Run the private API and public Streamlit UI in one Render container."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.request


def main():
    if not os.environ.get('APP_PASSWORD', '').strip():
        raise SystemExit('Set APP_PASSWORD in hosting environment before starting the public demo.')
    os.chdir(Path(__file__).resolve().parents[1])
    processes = []

    def stop(signum, frame):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        backend = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'backend.main:app',
                                    '--host', '127.0.0.1', '--port', '8000'])
        processes.append(backend)
        for _ in range(120):
            if backend.poll() is not None:
                raise RuntimeError('Backend exited during startup')
            try:
                with urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=1) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(.5)
        else:
            raise RuntimeError('Backend did not become healthy')
        frontend = subprocess.Popen([sys.executable, '-m', 'streamlit', 'run', 'app/app.py',
            '--server.address=0.0.0.0', '--server.port=' + os.environ.get('PORT', '10000'),
            '--server.headless=true', '--server.maxUploadSize=2', '--browser.gatherUsageStats=false'])
        processes.append(frontend)
        while all(process.poll() is None for process in processes):
            time.sleep(.5)
        raise RuntimeError('A service exited; shutting down the container')
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == '__main__':
    main()
