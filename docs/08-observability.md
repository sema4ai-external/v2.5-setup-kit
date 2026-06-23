# Observability

**TL;DR**: observability is owned by your hosting platform. This page
points to the native tooling per target and lists the few things your
MCP code should do to play well with it.

## Platform-native tooling

| Target | Logs | Traces |
| --- | --- | --- |
| **Google Cloud Run** | Cloud Logging — captures container stdout automatically. | Cloud Trace — instrument with OpenTelemetry. |
| **AWS ECS Fargate** | CloudWatch Logs — `awslogs` driver captures stdout. | AWS X-Ray — instrument with OpenTelemetry or the X-Ray SDK. |
| **Azure Container Apps** | Log Analytics workspace attached to the Container Apps environment. | Application Insights — instrument with OpenTelemetry. |

Every platform handles log retention, search, and alerting out of the
box. Use them.

## What to log in your MCP

A short list, not a framework:

- **Tool name and duration** — one line per tool invocation. Helps
  identify slow tools without external tracing.
- **Request ID** — read or generate one per request; include it on
  every log line for that request. Makes multi-line traces
  reconstructible.
- **Auth failures** — log that auth *failed* (and why, at a high
  level: "missing bearer", "expired token"). Don't log the token
  value.
- **Vendor API failures** — status code and the vendor's error
  message. Don't log full response bodies (often contain PII).

Keep it to stdout, structured (JSON) if your platform parses it,
plain text otherwise. Don't invent a custom logging stack.

## What NOT to log

- **Tokens or API keys.** Ever. Redact `Authorization`, `X-Api-Key`,
  and `agent_server_api_token` before logging any headers.
- **File bytes.** Filename + size only.
- **Full `X-Tool-Invocation-Context`** decoded. Log `agent_id` +
  `thread_id` if useful; never `agent_server_api_token`.
- **User prompts or tool inputs that may contain PII.** Identify the
  tool call, don't archive the content.

## Tracing (optional)

If you need per-request traces (latency breakdowns, vendor-call
spans), instrument with **OpenTelemetry**. Every platform above has
an OTel exporter; configure it via env vars, and the standard
`opentelemetry-instrumentation-*` packages capture the hot path
automatically.

This is overkill for most migrations — add it when you've shipped,
not before.
