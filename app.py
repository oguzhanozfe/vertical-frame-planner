"""Run a report on the command line or serve the interactive workspace."""
import argparse
import hmac
import json
import math
import os
import sys
from pathlib import Path
from wsgiref.simple_server import make_server

import project
import providers

ROOT = Path(__file__).resolve().parent
MAX_INPUT = 256 * 1024


def read_json(raw):
    if len(raw) > MAX_INPUT:
        raise ValueError("The JSON file exceeds 256 KiB.")
    def reject(value):
        raise ValueError("Use finite JSON numbers.")
    data = json.loads(raw.decode("utf-8-sig"), parse_constant=reject)
    if not isinstance(data, dict):
        raise ValueError("The input must be a JSON object.")
    def check(item, depth=0):
        if depth > 24:
            raise ValueError("The JSON is nested more than 24 levels.")
        if isinstance(item, (list, dict)):
            if len(item) > 2000:
                raise ValueError("Use at most 2,000 items per collection.")
            for child in item.values() if isinstance(item, dict) else item:
                check(child, depth + 1)
        elif isinstance(item, float) and not math.isfinite(item):
            reject(item)
    check(data)
    return data


def calculate(data):
    try:
        result = project.analyze(data)
        json.dumps(result, allow_nan=False)
        return result
    except (KeyError, TypeError, IndexError, AttributeError, ZeroDivisionError, OverflowError) as exc:
        raise ValueError("Invalid project input. Compare the fields, types and units with the example.") from exc


def model_allowed(env):
    token = os.environ.get("MODEL_ACCESS_TOKEN", "")
    if token:
        return hmac.compare_digest(env.get("HTTP_X_ACCESS_TOKEN", "").encode(), token.encode())
    return env.get("REMOTE_ADDR") in ("127.0.0.1", "::1") and os.getenv("PUBLIC_BIND") != "1"


def application(env, start):
    path, method = env.get("PATH_INFO", "/"), env.get("REQUEST_METHOD", "GET")
    def send(status, value, content_type="application/json"):
        data = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
        start(status, [("Content-Type", content_type + "; charset=utf-8"), ("Content-Length", str(len(data))),
                       ("X-Content-Type-Options", "nosniff"), ("Cache-Control", "no-store")])
        return [data]
    if method == "GET":
        if path == "/health":
            return send("200 OK", {"status": "ok"})
        if path == "/api/example":
            demo = read_json((ROOT / "example.json").read_bytes())
            return send("200 OK", {"title": project.TITLE, "description": project.DESCRIPTION,
                "input": demo, "report": calculate(demo), "provider": providers.active_provider(),
                "access_token_required": bool(os.getenv("MODEL_ACCESS_TOKEN"))})
        assets = {"/": ("index.html", "text/html"), "/style.css": ("style.css", "text/css"),
                  "/ui.js": ("ui.js", "text/javascript"), "/diagram.js": ("diagram.js", "text/javascript")}
        if path in assets:
            name, mime = assets[path]
            return send("200 OK", (ROOT / "web" / name).read_bytes(), mime)
    if method == "POST" and path == "/api/analyze":
        try:
            if env.get("CONTENT_TYPE", "").split(";")[0].strip() != "application/json":
                return send("415 Unsupported Media Type", {"error": "Send application/json."})
            size = int(env.get("CONTENT_LENGTH") or 0)
            if not 0 < size <= MAX_INPUT:
                return send("413 Payload Too Large", {"error": "Send between 1 byte and 256 KiB of JSON."})
            data = read_json(env["wsgi.input"].read(size))
            with_model = data.get("review", False)
            if not isinstance(with_model, bool) or not isinstance(data.get("input"), dict):
                raise ValueError("Expected an input object and an optional boolean review flag.")
            if with_model and not model_allowed(env):
                return send("403 Forbidden", {"error": "Hosted model reviews require a matching MODEL_ACCESS_TOKEN."})
            report = calculate(data["input"])
            if with_model:
                report["model_review"] = providers.review(project.PROMPT, report)
            return send("200 OK", report)
        except (ValueError, RecursionError) as exc:
            return send("400 Bad Request", {"error": str(exc)})
        except providers.ModelError as exc:
            return send("502 Bad Gateway", {"error": str(exc)})
    return send("404 Not Found", {"error": "Unknown route or method."})


def main():
    parser = argparse.ArgumentParser(description=project.DESCRIPTION)
    parser.add_argument("command", choices=("serve", "analyze"), nargs="?", default="serve")
    parser.add_argument("file", type=Path, nargs="?", default=ROOT / "example.json")
    parser.add_argument("--review", action="store_true", help="Request model commentary on the computed report.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    args = parser.parse_args()
    if args.command == "analyze":
        try:
            with args.file.open("rb") as handle:
                result = calculate(read_json(handle.read(MAX_INPUT + 1)))
            if args.review:
                result["model_review"] = providers.review(project.PROMPT, result)
            print(json.dumps(result, ensure_ascii=True, indent=2, allow_nan=False))
        except (ValueError, OSError, providers.ModelError, RecursionError) as exc:
            parser.exit(2, f"Error: {exc}\n")
    else:
        if args.host not in ("localhost", "127.0.0.1", "::1"):
            os.environ["PUBLIC_BIND"] = "1"
        with make_server(args.host, args.port, application) as server:
            print(f"{project.TITLE} at http://{args.host}:{server.server_port}", flush=True)
            server.serve_forever()


if __name__ == "__main__":
    main()
