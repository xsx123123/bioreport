"""Offline static report launcher using only the Python standard library."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import argparse
from threading import Timer
import webbrowser


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--no-browser', action='store_true', help='Print the URL without opening a browser')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    handler = partial(SimpleHTTPRequestHandler, directory=str(root))
    with ThreadingHTTPServer(('127.0.0.1', args.port), handler) as server:
        url = f'http://127.0.0.1:{server.server_port}/'
        print(f'BioReport: {url} — Stop: Ctrl+C', flush=True)
        opener = Timer(.2, webbrowser.open, args=(url,)) if not args.no_browser else None
        if opener:
            opener.daemon = True
            opener.start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print('Report server stopped.', flush=True)
        finally:
            if opener:
                opener.cancel()


if __name__ == '__main__':
    main()
