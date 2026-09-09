# Product Profit Finalization Security Review

## Scope

- Product-center logistics bill, cost assumption, and baseline profit APIs
- Feishu projection configuration, outbox, and HTTP client
- Current-schema migration `20260910_product_profit_finalization`

## OWASP Review

| Category | Status | Notes |
| --- | --- | --- |
| A01 Access control | Pass | Router requires login; product edits require admin/manager/finance; Feishu initialization and retry are admin-only. |
| A02 Sensitive data | Pass | App credentials are read only from environment variables; no secrets are stored in tables or source. |
| A03 Injection | Pass | SQLAlchemy predicates and bound text parameters are used; table identifiers come from persisted configuration. |
| A04 Insecure design | Pass | Estimated profit remains separate from B-class actual settlement data; confirmed bills are immutable. |
| A05 Misconfiguration | Pass | Shared examples contain blank credential placeholders only. |
| A06 Dependencies | Blocked | npm audit is unavailable through the configured mirror audit endpoint. |
| A07 Authentication | Pass | Existing authentication dependency applies to all routes. |
| A08 Data integrity | Pass | Bill total reconciliation, immutable confirmation, outbox dedupe key, and append-only delivery logs are enforced. |
| A09 Logging | Pass | Failed delivery attempts are persisted without secrets. |
| A10 SSRF | Pass | Feishu base URL is environment-owned, never API input. |

## Findings

No critical or high-severity issue remains. Feishu projection initialization and retry were restricted to administrators during review.
