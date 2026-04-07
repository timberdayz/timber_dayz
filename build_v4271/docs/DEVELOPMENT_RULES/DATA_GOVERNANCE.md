# Data Governance & Sensitive Access

**Version**: v4.20.0
**Standard**: Data Classification + Sensitive Access Control + Audit Retention

---

## Part A: Data Classification (D5)

### Four-Level Classification Table

| Level | Definition | Examples | Access Requirement |
|---|---|---|---|
| **public** | Publicly disclosable | Platform names, product categories, public announcements | No restriction |
| **internal** | Internal use only | Order statistics, collection configurations, system logs | Login required |
| **sensitive** | Business-sensitive data | Sales revenue, profit, GMV, customer contact info, employee department | RBAC + audit log |
| **restricted** | Highly sensitive personal/financial data | Salary, performance scores, ID card numbers, phone numbers, passwords, API tokens, OAuth credentials | RBAC + audit log + export approval |

---

## Part B: Restricted Data Inventory (Current System)

The following tables and fields in this system contain **restricted** level data:

### HR / Salary Data

| Table | Schema | Restricted Fields |
|---|---|---|
| `salary_structures` | `a_class` | `base_salary`, `position_salary`, `commission_ratio`, `performance_ratio` |
| `employee_incomes` | `c_class` | `base_salary`, `position_salary`, `performance_salary`, `commission`, `gross_salary`, `net_salary` |
| `employees` | `a_class` | `id_type`, `id_number` (identity document), `phone`, `emergency_phone`, `salary` (column) |
| `salary_structure_templates` | `a_class` | `min_salary`, `max_salary`, `base_salary`, `position_salary` |

### Performance Data

| Table | Schema | Restricted Fields |
|---|---|---|
| `employee_performance` | `c_class` | `performance_score` (personal performance score) |
| `employee_commissions` | `c_class` | `commission_amount`, `commission_rate` |
| `performance_scores` | `c_class` | `total_score`, `rank` (individual shop-level scores) |

### Authentication / Credential Data

| Table | Schema | Restricted Fields |
|---|---|---|
| `users` | `public` | `password_hash` |
| `platform_accounts` | `a_class` | `password_encrypted`, `session_cookies`, `capabilities` |
| `user_sessions` | `public` | `session_id` (token hash) |

### Sensitive (Not Restricted) Data

| Table | Schema | Sensitive Fields |
|---|---|---|
| `users` | `public` | `phone`, `email` |
| `shop_profiles` | `a_class` | `contact_phone` |
| `sales_targets` | `a_class` | All target values (revenue, profit targets) |

---

## Part C: Sensitive Data Access Rules

### Viewing Rules

| Level | Who Can View | Condition |
|---|---|---|
| sensitive | Any authenticated user with appropriate RBAC role | Role check via `require_permission()` |
| restricted | Admin role **or** data owner only | Explicit ownership check required |

### Export Rules

| Level | Requirements |
|---|---|
| sensitive | RBAC role check + export logged to audit |
| restricted | RBAC role check + **second confirmation** dialog + audit log entry with `export_reason` |

### Logger Desensitization Patterns

**Rule: restricted fields MUST NOT appear in plaintext in any log output.**

Desensitization patterns:

| Data Type | Display Pattern | Example |
|---|---|---|
| Phone number | Keep first 3 and last 4 digits | `186****9999` |
| ID card number | Keep first 6 and last 4 digits | `440301****1234` |
| Password / token | Never log; replace with `[REDACTED]` | `[REDACTED]` |
| Salary amount | Replace with `[SALARY_REDACTED]` | `[SALARY_REDACTED]` |
| Bank account | Keep last 4 digits | `****6789` |
| Email address | Mask local part after first 3 chars | `use***@example.com` |

**Implementation pattern:**

```python
import re

def mask_phone(phone: str) -> str:
    if not phone or len(phone) < 7:
        return "[REDACTED]"
    return phone[:3] + "****" + phone[-4:]

def mask_id_card(id_card: str) -> str:
    if not phone or len(id_card) < 10:
        return "[REDACTED]"
    return id_card[:6] + "****" + id_card[-4:]

def mask_salary(amount) -> str:
    return "[SALARY_REDACTED]"
```

### Audit Log Retention

| Data Level | Minimum Retention |
|---|---|
| restricted access/export operations | **>= 180 days** |
| sensitive access/export operations | >= 90 days |
| Authentication events (login/logout) | >= 90 days |

Audit logs must include: timestamp (UTC), user_id, action type, resource type + id, IP address, result (success/fail).

---

## Part D: Implementation Guidelines

### For Backend Developers

1. When exposing HR/salary/performance endpoints, always check:
   - Is the user `admin` or the data owner? (`require_admin` or ownership check)
   - Is the audit log written before returning data?

2. When writing to log output, filter restricted fields:
   ```python
   logger.info("Processing employee %s income", employee_code)
   # NOT: logger.info("Salary for %s: %s", employee_code, salary_amount)
   ```

3. Export APIs must:
   - Require explicit `export_reason` parameter
   - Write to `audit_logs` before streaming response
   - For restricted data: require re-authentication or 2FA confirmation

### For Agent / AI Developers

When generating code that touches these tables, the agent must:
- Never include raw salary/performance/credential values in log statements
- Always inject `get_current_user` and verify authorization level
- Use `mask_phone()`, `mask_id_card()` utilities when logging user identifiers

### New Table Classification Protocol

When adding a new table via Alembic migration:
1. Review each column against the classification table above
2. Add a comment on restricted/sensitive columns: `comment="[RESTRICTED] ..."`
3. Update this document's inventory if the table contains restricted data
