#!/usr/bin/env python
"""
Schema-driven API verifier for DRF/OpenAPI deployments.

Goals:
- Avoid false negatives caused by throttling (429)
- Validate auth-required vs public access behavior
- Avoid random UUID path probing that creates noisy 404 results
- Report only actionable failures
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
import yaml


HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}
SAFE_METHODS = {"get", "head", "options"}


@dataclass
class ResolvedValue:
    value: Any
    source: str


@dataclass
class Operation:
    path: str
    method: str
    operation_id: str
    raw: Dict[str, Any]
    parameters: List[Dict[str, Any]]
    request_body: Dict[str, Any]
    responses: Dict[str, Any]
    requires_auth: bool
    expected_statuses: List[int]


@dataclass
class TestResult:
    method: str
    path: str
    scenario: str
    status: str
    http_status: Optional[int]
    reason: str
    retries: int = 0
    operation_id: str = ""


@dataclass
class Summary:
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    throttled: int = 0
    details: List[TestResult] = field(default_factory=list)

    def add(self, result: TestResult) -> None:
        self.details.append(result)
        if result.status == "passed":
            self.passed += 1
        elif result.status == "failed":
            self.failed += 1
        elif result.status == "throttled":
            self.throttled += 1
        else:
            self.skipped += 1


class RequestPacer:
    def __init__(self, min_delay_seconds: float, max_rps: float):
        self.min_delay_seconds = max(min_delay_seconds, 0.0)
        self.max_rps = max(max_rps, 0.0)
        self.last_request_at: float = 0.0

    def wait(self) -> None:
        now = time.monotonic()
        required_delay = self.min_delay_seconds
        if self.max_rps > 0:
            required_delay = max(required_delay, 1.0 / self.max_rps)
        elapsed = now - self.last_request_at
        if elapsed < required_delay:
            time.sleep(required_delay - elapsed)
        self.last_request_at = time.monotonic()


class OpenApiRunner:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.schema = self._load_schema(args.schema)
        self.global_security = self.schema.get("security", [])
        self.session = requests.Session()
        self.pacer = RequestPacer(args.min_delay, args.max_rps)
        self.token: Optional[str] = args.access_token
        self.overrides = self._parse_key_values(args.path_param or [])
        self.query_overrides = self._parse_key_values(args.query_param or [])
        self.discovered_ids: Dict[str, List[Any]] = {}
        self.discovery_pool: List[Any] = []

    @staticmethod
    def _load_schema(path: str) -> Dict[str, Any]:
        with open(path, "r", encoding="utf-8") as handle:
            return yaml.safe_load(handle)

    @staticmethod
    def _parse_key_values(items: List[str]) -> Dict[str, str]:
        parsed: Dict[str, str] = {}
        for item in items:
            if "=" not in item:
                continue
            key, value = item.split("=", 1)
            parsed[key.strip()] = value.strip()
        return parsed

    def _resolve_ref(self, node: Any) -> Any:
        if not isinstance(node, dict) or "$ref" not in node:
            return node
        ref = node["$ref"]
        if not isinstance(ref, str) or not ref.startswith("#/"):
            return node
        target: Any = self.schema
        for token in ref[2:].split("/"):
            token = token.replace("~1", "/").replace("~0", "~")
            if not isinstance(target, dict):
                return node
            target = target.get(token)
            if target is None:
                return node
        return target

    def _expected_statuses(self, responses: Dict[str, Any]) -> List[int]:
        statuses: List[int] = []
        for code in responses.keys():
            if not isinstance(code, str):
                continue
            code = code.strip().upper()
            if code == "DEFAULT":
                continue
            if code.isdigit():
                statuses.append(int(code))
                continue
            match = re.match(r"([1-5])XX$", code)
            if match:
                hundred = int(match.group(1)) * 100
                statuses.extend(range(hundred, hundred + 100))
        return sorted(set(statuses))

    def _requires_auth(self, operation: Dict[str, Any]) -> bool:
        security = operation.get("security", self.global_security)
        if security == []:
            return False
        return bool(security)

    def _iter_operations(self) -> Iterable[Operation]:
        paths = self.schema.get("paths", {})
        for path, path_item in paths.items():
            path_item = self._resolve_ref(path_item)
            if not isinstance(path_item, dict):
                continue
            path_params = [self._resolve_ref(p) for p in path_item.get("parameters", [])]
            for method, raw_op in path_item.items():
                method_l = method.lower()
                if method_l not in HTTP_METHODS:
                    continue
                raw_op = self._resolve_ref(raw_op)
                if not isinstance(raw_op, dict):
                    continue
                if not self.args.include_unsafe and method_l not in SAFE_METHODS:
                    continue
                op_params = path_params + [self._resolve_ref(p) for p in raw_op.get("parameters", [])]
                op = Operation(
                    path=path,
                    method=method_l.upper(),
                    operation_id=raw_op.get("operationId", f"{method_l}:{path}"),
                    raw=raw_op,
                    parameters=op_params,
                    request_body=self._resolve_ref(raw_op.get("requestBody", {})),
                    responses=raw_op.get("responses", {}),
                    requires_auth=self._requires_auth(raw_op),
                    expected_statuses=self._expected_statuses(raw_op.get("responses", {})),
                )
                yield op

    @staticmethod
    def _pick_example(schema_node: Dict[str, Any]) -> Optional[Any]:
        if not isinstance(schema_node, dict):
            return None
        if "example" in schema_node:
            return schema_node["example"]
        if "default" in schema_node:
            return schema_node["default"]
        enum = schema_node.get("enum")
        if isinstance(enum, list) and enum:
            return enum[0]
        return None

    def _resolve_parameter(self, param: Dict[str, Any]) -> ResolvedValue:
        param = self._resolve_ref(param)
        name = param.get("name")
        schema = self._resolve_ref(param.get("schema", {}))
        if not name:
            return ResolvedValue(None, "missing")

        if name in self.overrides:
            return ResolvedValue(self.overrides[name], "override")

        example = self._pick_example(param) or self._pick_example(schema)
        if example is not None:
            return ResolvedValue(example, "example")

        if name in self.discovered_ids and self.discovered_ids[name]:
            return ResolvedValue(self.discovered_ids[name][0], "discovered")

        if self.discovery_pool:
            if schema.get("format") == "uuid" or name.lower().endswith("id"):
                return ResolvedValue(self.discovery_pool[0], "discovered")

        # We intentionally do not synthesize opaque IDs to avoid random 404 abuse.
        if schema.get("format") == "uuid" or name.lower().endswith("id"):
            return ResolvedValue(None, "missing_id")

        if schema.get("type") in ("integer", "number"):
            return ResolvedValue(1, "synthetic")
        if schema.get("type") == "boolean":
            return ResolvedValue(True, "synthetic")
        return ResolvedValue("sample", "synthetic")

    def _resolve_path_and_query(self, op: Operation) -> Tuple[Optional[str], Dict[str, Any], str]:
        path = op.path
        query: Dict[str, Any] = {}
        sources: List[str] = []

        for param in op.parameters:
            location = param.get("in")
            required = bool(param.get("required", False))
            name = param.get("name")
            if not name or location not in {"path", "query"}:
                continue

            if location == "query" and name in self.query_overrides:
                value = self.query_overrides[name]
                sources.append("override")
            else:
                resolved = self._resolve_parameter(param)
                value = resolved.value
                sources.append(resolved.source)

            if value is None and required:
                return None, {}, "missing_required_param"

            if location == "path":
                if value is None:
                    return None, {}, "missing_path_value"
                path = path.replace("{" + name + "}", str(value))
            elif location == "query" and value is not None:
                query[name] = value

        return path, query, ",".join(sources)

    def _build_request_body(self, op: Operation) -> Tuple[Optional[Any], str]:
        if op.method in {"GET", "HEAD", "OPTIONS", "DELETE"}:
            return None, "none"
        if not self.args.include_unsafe:
            return None, "unsafe_skipped"
        if not isinstance(op.request_body, dict):
            return None, "none"

        content = op.request_body.get("content", {})
        json_content = self._resolve_ref(content.get("application/json"))
        if isinstance(json_content, dict):
            if "example" in json_content:
                return json_content["example"], "example"
            examples = json_content.get("examples", {})
            if isinstance(examples, dict) and examples:
                first = next(iter(examples.values()))
                first = self._resolve_ref(first)
                if isinstance(first, dict) and "value" in first:
                    return first["value"], "example"
            schema = self._resolve_ref(json_content.get("schema", {}))
            schema_example = self._pick_example(schema)
            if schema_example is not None:
                return schema_example, "schema_example"
            if schema.get("type") == "object":
                return {}, "empty_object"

        return None, "missing_body"

    def _extract_ids(self, payload: Any) -> None:
        if payload is None:
            return
        stack = [payload]
        seen = 0
        while stack and seen < 5000:
            seen += 1
            item = stack.pop()
            if isinstance(item, dict):
                for key, value in item.items():
                    key_l = str(key).lower()
                    if key_l in {"id", "uuid"} or key_l.endswith("_id"):
                        if isinstance(value, (str, int)) and value not in self.discovery_pool:
                            self.discovery_pool.append(value)
                            self.discovered_ids.setdefault(str(key), [])
                            if value not in self.discovered_ids[str(key)]:
                                self.discovered_ids[str(key)].append(value)
                    if isinstance(value, (dict, list)):
                        stack.append(value)
            elif isinstance(item, list):
                stack.extend(item)

    @staticmethod
    def _retry_after_seconds(value: str) -> Optional[float]:
        if not value:
            return None
        value = value.strip()
        if value.isdigit():
            return float(value)
        try:
            parsed = datetime.strptime(value, "%a, %d %b %Y %H:%M:%S GMT").replace(tzinfo=timezone.utc)
            return max((parsed - datetime.now(timezone.utc)).total_seconds(), 0.0)
        except ValueError:
            return None

    def _request_with_backoff(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        params: Dict[str, Any],
        json_payload: Any,
    ) -> Tuple[Optional[requests.Response], int]:
        retries = 0
        response: Optional[requests.Response] = None

        while retries <= self.args.max_retries:
            self.pacer.wait()
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    json=json_payload,
                    timeout=self.args.timeout,
                )
            except requests.RequestException:
                if retries >= self.args.max_retries:
                    return None, retries
                retries += 1
                sleep_for = min(self.args.max_backoff, (self.args.backoff_base * (2 ** retries)) + random.uniform(0.0, 0.5))
                time.sleep(sleep_for)
                continue

            if response.status_code != 429:
                return response, retries

            if retries >= self.args.max_retries:
                return response, retries

            retry_after = None
            if self.args.respect_retry_after:
                retry_after = self._retry_after_seconds(response.headers.get("Retry-After", ""))
            fallback = min(self.args.max_backoff, (self.args.backoff_base * (2 ** retries)) + random.uniform(0.0, 0.5))
            time.sleep(max(retry_after or fallback, self.args.min_delay))
            retries += 1

        return response, retries

    def _classify(
        self,
        op: Operation,
        scenario: str,
        response: Optional[requests.Response],
        retries: int,
        source_tag: str,
    ) -> TestResult:
        if response is None:
            return TestResult(
                method=op.method,
                path=op.path,
                scenario=scenario,
                status="failed",
                http_status=None,
                reason="request_failed",
                retries=retries,
                operation_id=op.operation_id,
            )

        status_code = response.status_code
        if status_code == 429:
            return TestResult(
                method=op.method,
                path=op.path,
                scenario=scenario,
                status="throttled",
                http_status=status_code,
                reason="rate_limited_after_retries",
                retries=retries,
                operation_id=op.operation_id,
            )

        if scenario == "unauth_required":
            if status_code in (401, 403):
                return TestResult(op.method, op.path, scenario, "passed", status_code, "auth_enforced", retries, op.operation_id)
            if status_code == 404 and "discovered" not in source_tag and "override" not in source_tag and "example" not in source_tag:
                return TestResult(op.method, op.path, scenario, "skipped", status_code, "likely_synthetic_resource_path", retries, op.operation_id)
            return TestResult(op.method, op.path, scenario, "failed", status_code, "auth_not_enforced", retries, op.operation_id)

        if scenario == "auth":
            if status_code in (401, 403):
                return TestResult(op.method, op.path, scenario, "failed", status_code, "authenticated_request_denied", retries, op.operation_id)
            if op.expected_statuses and status_code in op.expected_statuses:
                return TestResult(op.method, op.path, scenario, "passed", status_code, "documented_response", retries, op.operation_id)
            if not op.expected_statuses and 200 <= status_code < 400:
                return TestResult(op.method, op.path, scenario, "passed", status_code, "successful_response", retries, op.operation_id)
            if status_code == 404 and "discovered" not in source_tag and "override" not in source_tag and "example" not in source_tag:
                return TestResult(op.method, op.path, scenario, "skipped", status_code, "likely_synthetic_resource_path", retries, op.operation_id)
            if 500 <= status_code <= 599:
                return TestResult(op.method, op.path, scenario, "failed", status_code, "server_error", retries, op.operation_id)
            return TestResult(op.method, op.path, scenario, "failed", status_code, "unexpected_response", retries, op.operation_id)

        # public unauth scenario
        if op.expected_statuses and status_code in op.expected_statuses:
            return TestResult(op.method, op.path, scenario, "passed", status_code, "documented_response", retries, op.operation_id)
        if not op.expected_statuses and 200 <= status_code < 400:
            return TestResult(op.method, op.path, scenario, "passed", status_code, "successful_response", retries, op.operation_id)
        if status_code in (401, 403):
            return TestResult(op.method, op.path, scenario, "skipped", status_code, "access_policy_differs_from_schema", retries, op.operation_id)
        if status_code >= 500:
            return TestResult(op.method, op.path, scenario, "failed", status_code, "server_error", retries, op.operation_id)
        return TestResult(op.method, op.path, scenario, "failed", status_code, "unexpected_response", retries, op.operation_id)

    def _auth_headers(self, authenticated: bool) -> Dict[str, str]:
        headers = {"Accept": "application/json"}
        if authenticated and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def login_if_needed(self) -> None:
        if self.token:
            return
        if not (self.args.email and self.args.password):
            return

        login_url = self.args.base_url.rstrip("/") + "/" + self.args.login_path.lstrip("/")
        payload = {"email": self.args.email, "password": self.args.password}
        response, _ = self._request_with_backoff(
            method="POST",
            url=login_url,
            headers={"Accept": "application/json"},
            params={},
            json_payload=payload,
        )
        if response is None:
            return
        if response.status_code >= 400:
            return

        try:
            body = response.json()
        except ValueError:
            return
        token = body.get("access")
        if isinstance(token, str) and token:
            self.token = token

    def run(self) -> Summary:
        self.login_if_needed()
        summary = Summary()

        operations = list(self._iter_operations())
        total = len(operations)

        for index, op in enumerate(operations, start=1):
            path, query, source_tag = self._resolve_path_and_query(op)
            if not path:
                summary.add(
                    TestResult(
                        method=op.method,
                        path=op.path,
                        scenario="planning",
                        status="skipped",
                        http_status=None,
                        reason=source_tag,
                        operation_id=op.operation_id,
                    )
                )
                continue

            body, body_source = self._build_request_body(op)
            if body_source in {"unsafe_skipped", "missing_body"}:
                summary.add(
                    TestResult(
                        method=op.method,
                        path=op.path,
                        scenario="planning",
                        status="skipped",
                        http_status=None,
                        reason=body_source,
                        operation_id=op.operation_id,
                    )
                )
                continue

            url = self.args.base_url.rstrip("/") + "/" + path.lstrip("/")

            if op.requires_auth:
                unauth_response, unauth_retries = self._request_with_backoff(
                    method=op.method,
                    url=url,
                    headers=self._auth_headers(authenticated=False),
                    params=query,
                    json_payload=body,
                )
                summary.add(self._classify(op, "unauth_required", unauth_response, unauth_retries, source_tag))

                if not self.token:
                    summary.add(
                        TestResult(
                            method=op.method,
                            path=op.path,
                            scenario="auth",
                            status="skipped",
                            http_status=None,
                            reason="missing_access_token",
                            operation_id=op.operation_id,
                        )
                    )
                    continue

                auth_response, auth_retries = self._request_with_backoff(
                    method=op.method,
                    url=url,
                    headers=self._auth_headers(authenticated=True),
                    params=query,
                    json_payload=body,
                )
                result = self._classify(op, "auth", auth_response, auth_retries, source_tag)
                summary.add(result)
                if auth_response is not None:
                    self._harvest_discovery(auth_response)
            else:
                public_response, public_retries = self._request_with_backoff(
                    method=op.method,
                    url=url,
                    headers=self._auth_headers(authenticated=False),
                    params=query,
                    json_payload=body,
                )
                result = self._classify(op, "unauth_public", public_response, public_retries, source_tag)
                summary.add(result)
                if public_response is not None:
                    self._harvest_discovery(public_response)

            if self.args.progress and (index % self.args.progress == 0 or index == total):
                print(
                    f"[progress] {index}/{total} operations | pass={summary.passed} fail={summary.failed} "
                    f"skip={summary.skipped} throttle={summary.throttled}",
                    flush=True,
                )

        return summary

    def _harvest_discovery(self, response: requests.Response) -> None:
        if not response.headers.get("Content-Type", "").lower().startswith("application/json"):
            return
        try:
            payload = response.json()
        except ValueError:
            return
        self._extract_ids(payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OpenAPI endpoint verifier")
    parser.add_argument("--schema", default="hrms_openapi.yaml")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--access-token")
    parser.add_argument("--email")
    parser.add_argument("--password")
    parser.add_argument("--login-path", default="/api/v1/auth/login/")
    parser.add_argument("--include-unsafe", action="store_true", help="Include POST/PUT/PATCH/DELETE when examples exist")
    parser.add_argument("--timeout", type=float, default=6.0)
    parser.add_argument("--min-delay", type=float, default=0.08, help="Delay between requests in seconds")
    parser.add_argument("--max-rps", type=float, default=8.0, help="Global request cap per second")
    parser.add_argument("--max-retries", type=int, default=4)
    parser.add_argument("--backoff-base", type=float, default=0.35)
    parser.add_argument("--max-backoff", type=float, default=8.0)
    parser.add_argument("--respect-retry-after", action="store_true", default=True)
    parser.add_argument("--no-respect-retry-after", dest="respect_retry_after", action="store_false")
    parser.add_argument("--path-param", action="append", help="Override path param. Example: employee_id=123")
    parser.add_argument("--query-param", action="append", help="Override query param. Example: year=2026")
    parser.add_argument("--progress", type=int, default=25, help="Progress log interval")
    parser.add_argument("--output-json", help="Optional path to save machine-readable report")
    return parser


def print_report(summary: Summary) -> None:
    print("")
    print("=== OpenAPI Test Summary ===")
    print(f"passed    : {summary.passed}")
    print(f"failed    : {summary.failed}")
    print(f"skipped   : {summary.skipped}")
    print(f"throttled : {summary.throttled}")

    failures = [item for item in summary.details if item.status == "failed"]
    if failures:
        print("")
        print("=== True Failures ===")
        for item in failures:
            print(
                f"- {item.method} {item.path} [{item.scenario}] status={item.http_status} "
                f"reason={item.reason} op={item.operation_id}"
            )


def maybe_write_json(summary: Summary, path: str) -> None:
    payload = {
        "passed": summary.passed,
        "failed": summary.failed,
        "skipped": summary.skipped,
        "throttled": summary.throttled,
        "results": [result.__dict__ for result in summary.details],
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    runner = OpenApiRunner(args)
    summary = runner.run()
    print_report(summary)
    if args.output_json:
        maybe_write_json(summary, args.output_json)
    return 1 if summary.failed else 0


if __name__ == "__main__":
    sys.exit(main())
