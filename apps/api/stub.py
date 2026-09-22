"""apps/api/stub.py — заглушка API до Итерации 0-А.

Слушает 0.0.0.0:${APP_PORT} и отвечает 200 на /healthz, 404 на всё остальное.
Нужна только чтобы docker-compose показал сервис healthy и Cloudflare Tunnel
мог быть протестирован до появления реального FastAPI-приложения.
"""
import http.server
import json
import os
import socketserver


PORT = int(os.environ.get("APP_PORT", "8080"))
HOST = os.environ.get("APP_HOST", "0.0.0.0")


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path == "/healthz":
            body = json.dumps({"status": "ok", "stub": True}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):  # noqa: A002
        # Плоский лог в stdout, чтобы docker compose logs красиво показывал.
        print(f"api stub: {self.address_string()} {format % args}", flush=True)


def main():
    print(f"api stub: listening on {HOST}:{PORT}", flush=True)
    with socketserver.TCPServer((HOST, PORT), Handler) as httpd:
        httpd.serve_forever()


if __name__ == "__main__":
    main()
