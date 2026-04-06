import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, urlunsplit


HOST = os.getenv("OVERLAY_STATIC_HOST", "127.0.0.1")
PORT = int(os.getenv("OVERLAY_STATIC_PORT", "8000"))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ALIASES = {
    "/": "/control.html",
    "/control": "/control.html",
    "/overlay": "/Overlay.html",
    "/Overlay": "/Overlay.html",
    "/standings_full": "/standings_full.html",
    "/standings_mini": "/standings_mini.html",
    "/bracket_mini": "/bracket_mini.html",
}


class NoCacheStaticHandler(SimpleHTTPRequestHandler):
    def _apply_alias(self):
        parsed = urlsplit(self.path)
        alias_path = ALIASES.get(parsed.path, parsed.path)
        if alias_path != parsed.path:
            self.path = urlunsplit(parsed._replace(path=alias_path))

    def do_GET(self):
        self._apply_alias()
        super().do_GET()

    def do_HEAD(self):
        self._apply_alias()
        super().do_HEAD()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()


def run():
    server = ThreadingHTTPServer(
        (HOST, PORT),
        lambda *args, **kwargs: NoCacheStaticHandler(*args, directory=BASE_DIR, **kwargs),
    )
    print(f"Static server laeuft auf http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    run()
