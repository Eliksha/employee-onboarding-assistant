"""Maintenance responder for the migration image: answers on port 8000 so App Service considers the container started,
but serves no application functionality (503 for everything except the platform's startup probe)."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    server_version = "maintenance"
    sys_version = ""

    def _reply(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Retry-After", "300")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        if self.path.startswith("/robots933456.txt"):      # App Service container start-up probe
            self._reply(200, b"{}")
        else:
            self._reply(503, b'{"detail":"Maintenance: database migration in progress."}')

    do_HEAD = do_POST = do_PUT = do_PATCH = do_DELETE = do_GET

    def log_message(self, fmt, *args):  # request paths only, no headers or bodies
        print("maintenance:", self.command, self.path.split("?")[0], flush=True)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
