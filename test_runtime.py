"""Shared WSGI, input boundary and optional model-provider contract tests."""
import io
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

import app
import project
import providers


def call(path, method="GET", data=None, raw=None, **env_override):
    body = raw if raw is not None else json.dumps(data).encode() if data is not None else b""
    environ = {
        "PATH_INFO": path,
        "REQUEST_METHOD": method,
        "REMOTE_ADDR": "127.0.0.1",
        "CONTENT_TYPE": "application/json",
        "CONTENT_LENGTH": str(len(body)),
        "wsgi.input": io.BytesIO(body),
        **env_override,
    }
    response = {}

    def start(status, headers):
        response["status"] = int(status.split()[0])
        response["headers"] = dict(headers)

    payload = b"".join(app.application(environ, start))
    if int(response["headers"]["Content-Length"]) != len(payload):
        raise AssertionError("Content-Length does not match the actual response.")
    return response["status"], response["headers"], payload


def json_call(*args, **kwargs):
    status, headers, payload = call(*args, **kwargs)
    if "application/json" not in headers["Content-Type"]:
        raise AssertionError("Expected a JSON response.")
    return status, json.loads(payload)


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, {"MODEL_PROVIDER": "off"}, clear=True).start()
        self.fixture = json.loads((app.ROOT / "example.json").read_text(encoding="utf-8-sig"))
        self.expected = project.analyze(self.fixture)

    def test_health_and_static_assets(self):
        self.assertEqual(json_call("/health"), (200, {"status": "ok"}))
        for path, mime in (("/", "text/html"), ("/style.css", "text/css"), ("/ui.js", "text/javascript")):
            with self.subTest(path=path):
                status, headers, body = call(path)
                self.assertEqual(status, 200)
                self.assertIn(mime, headers["Content-Type"])
                self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
                self.assertTrue(body)
        self.assertEqual(json_call("/missing")[0], 404)

    def test_example_and_post_preserve_entire_project_report(self):
        status, page = json_call("/api/example")
        self.assertEqual(status, 200)
        self.assertEqual(page["input"], self.fixture)
        self.assertEqual(page["report"], self.expected)
        self.assertEqual(page["title"], project.TITLE)
        self.assertEqual(page["provider"], "off")
        self.assertEqual(json_call("/api/analyze", "POST", {"input":self.fixture}), (200, self.expected))

    def test_validation_and_media_type(self):
        for raw in (b'[]', b'{}', b'{"input":{},"review":1}', b'{"input":NaN}', b'{"input":1e999}', b'{'):
            with self.subTest(raw=raw):
                self.assertEqual(json_call("/api/analyze", "POST", raw=raw)[0], 400)
        raw = json.dumps({"input": self.fixture}).encode()
        self.assertEqual(json_call("/api/analyze", "POST", raw=raw, CONTENT_TYPE="text/plain")[0], 415)
        self.assertEqual(json_call("/api/analyze", "POST", raw=raw, CONTENT_LENGTH=str(app.MAX_INPUT+1))[0], 413)
        self.assertEqual(json_call("/api/analyze", "POST", raw=raw, CONTENT_LENGTH="invalid")[0], 400)
        with self.assertRaises(ValueError):
            app.read_json(b'{"x":' + b"["*25 + b"0" + b"]"*25 + b"}")
        with self.assertRaises(ValueError):
            app.read_json(json.dumps({"x": [0]*2001}).encode())

    def test_public_review_requires_secret_even_from_reverse_proxy(self):
        request = {"input": self.fixture, "review": True}
        with patch.dict(os.environ, {"PUBLIC_BIND": "1"}), patch.object(providers, "review") as model:
            self.assertEqual(json_call("/api/analyze", "POST", request)[0], 403)
            with patch.dict(os.environ, {"MODEL_ACCESS_TOKEN": "unit-test-token"}):
                self.assertEqual(json_call("/api/analyze", "POST", request, HTTP_X_ACCESS_TOKEN="wrong")[0], 403)
            model.assert_not_called()

    def test_authorized_review_augments_but_does_not_truncate_report(self):
        request = {"input": self.fixture, "review": True}
        with patch.dict(os.environ, {"MODEL_ACCESS_TOKEN": "fake-test-token"}), \
             patch.object(providers, "review", return_value="Verified test response.") as model:
            status, result = json_call("/api/analyze", "POST", request,
                                       HTTP_X_ACCESS_TOKEN="fake-test-token", REMOTE_ADDR="203.0.113.5")
        self.assertEqual(status, 200)
        self.assertEqual(result.pop("model_review"), "Verified test response.")
        self.assertEqual(result, self.expected)
        self.assertEqual(model.call_count, 1)

    def test_unconfigured_provider_returns_error_without_credentials_in_response(self):
        with patch.dict(os.environ, {"MODEL_PROVIDER":"api", "MODEL_ID":"stub"}), \
             patch.object(providers.urllib.request, "urlopen") as net:
            status, result = json_call("/api/analyze", "POST", {"input": self.fixture, "review": True})
            self.assertEqual(status, 502)
            self.assertIn("error", result)
            net.assert_not_called()


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, {}, clear=True).start()
        self.report = {"summary":"Seven guides reviewed.", "metrics":{"Guides":7}, "rows":[{"Label":"Save"}]}

    def request_for(self, configured):
        answer = {"choices": [{"message": {"content": " Model review. "}}]}
        with patch.dict(os.environ, configured), \
             patch.object(providers.urllib.request, "urlopen", return_value=io.BytesIO(json.dumps(answer).encode())) as net:
            self.assertEqual(providers.review("Explain the evidence.", self.report), "Model review.")
        req = net.call_args.args[0]
        self.assertEqual(req.get_method(), "POST")
        headers = {k.lower():v for k,v in req.header_items()}
        body = json.loads(req.data)
        self.assertEqual(body["model"], configured["MODEL_ID"])
        evidence = json.loads(body["messages"][1]["content"])
        self.assertEqual(evidence["rows"], self.report["rows"])
        return req.full_url, headers, body

    def test_azure_v1_url_and_resource_key(self):
        for base in ("https://unit.openai.azure.com", "https://unit.openai.azure.com/openai/v1/"):
            with self.subTest(base=base):
                url, headers, body = self.request_for({"MODEL_PROVIDER":"azure", "MODEL_ID":"deployment",
                                                      "MODEL_BASE_URL":base, "MODEL_API_KEY":"dummy-key"})
                self.assertEqual(url, "https://unit.openai.azure.com/openai/v1/chat/completions")
                self.assertEqual(headers["api-key"], "dummy-key")
                self.assertNotIn("authorization", headers)
                self.assertIn("max_completion_tokens", body)

    def test_local_and_compatible_api_use_bearer_headers(self):
        for provider, base in (("local","http://127.0.0.1:1234/v1"), ("api","https://example.test/v1")):
            with self.subTest(provider=provider):
                url, headers, body = self.request_for({"MODEL_PROVIDER":provider, "MODEL_ID":"model",
                                                      "MODEL_BASE_URL":base, "MODEL_API_KEY":"dummy-key"})
                self.assertEqual(url, base+"/chat/completions")
                self.assertEqual(headers["authorization"], "Bearer dummy-key")
                self.assertIn("max_tokens", body)
        url, headers, _ = self.request_for({"MODEL_PROVIDER":"local", "MODEL_ID":"model"})
        self.assertEqual(url, "http://127.0.0.1:11434/v1/chat/completions")
        self.assertNotIn("authorization", headers)

    def test_bedrock_converse_contract(self):
        boto = MagicMock()
        client = boto.client.return_value
        client.converse.return_value = {"output":{"message":{"content":[{"text":"First."},{"text":"Second."}]}}}
        with patch.dict(sys.modules, {"boto3":boto}), patch.dict(os.environ, {
            "MODEL_PROVIDER":"bedrock", "MODEL_ID":"test-profile", "AWS_REGION":"eu-west-1",
        }):
            self.assertEqual(providers.review("Use the metrics.", self.report), "First.\nSecond.")
        boto.client.assert_called_once_with("bedrock-runtime", region_name="eu-west-1")
        body = client.converse.call_args.kwargs
        self.assertEqual(body["modelId"], "test-profile")
        self.assertEqual(body["inferenceConfig"]["maxTokens"], 1024)
        self.assertIn("Use the metrics.", body["system"][0]["text"])
        self.assertEqual(body["messages"][0]["role"], "user")
        self.assertEqual(json.loads(body["messages"][0]["content"][0]["text"])["metrics"], self.report["metrics"])

    def test_configuration_errors_do_not_start_requests(self):
        for config in (
            {"MODEL_PROVIDER":"azure", "MODEL_BASE_URL":"https://unit.openai.azure.com", "MODEL_ID":"x"},
            {"MODEL_PROVIDER":"api", "MODEL_ID":"x"},
            {"MODEL_PROVIDER":"api", "MODEL_ID":"x", "MODEL_API_KEY":"dummy", "MODEL_BASE_URL":"http://unit.test/v1"},
            {"MODEL_PROVIDER":"local"},
        ):
            with self.subTest(provider=config["MODEL_PROVIDER"]), patch.dict(os.environ, config), \
                 patch.object(providers.urllib.request,"urlopen") as net:
                with self.assertRaises(providers.ModelError):
                    providers.review("Summarize.", self.report)
                net.assert_not_called()

    def test_review_sampling_keeps_totals_and_source_rows(self):
        report = {"summary":"60 rows", "metrics":{"Total":60}, "rows":[{"ID":i} for i in range(60)]}
        evidence = json.loads(providers.evidence_messages("Summarize.", report)[1]["content"])
        self.assertEqual(evidence["total_rows"], 60)
        self.assertEqual(len(evidence["rows"]), 40)
        self.assertEqual(len(report["rows"]), 60)
        self.assertEqual(evidence["metrics"], report["metrics"])
        self.assertEqual(evidence["summary"], report["summary"])


if __name__ == "__main__":
    unittest.main()
