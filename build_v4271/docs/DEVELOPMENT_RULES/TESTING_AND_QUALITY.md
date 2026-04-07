# Testing Strategy & Code Quality

**Version**: v4.20.0
**Standard**: Enterprise-grade testing and code quality standards

---

## 1. Test Pyramid

| Layer | Coverage | Speed | Scope |
|-------|----------|-------|-------|
| Unit tests | 70% | Milliseconds | Individual functions/classes |
| Integration tests | 20% | Seconds | Module interactions, DB, API |
| E2E tests | 10% | Minutes | Critical business flows end-to-end |

---

## 2. Test Types

### Functional Tests
- Business logic correctness
- Data processing accuracy
- Business rule enforcement

### Performance Tests
- Load testing (normal load)
- Stress testing (extreme load)
- Benchmark testing
- Tools: locust, JMeter, k6

### Security Tests
- Vulnerability scanning
- Penetration testing
- Permission control testing

### Compatibility Tests
- Browser compatibility (mainstream browsers)
- Platform: Windows, macOS, Linux
- Python version compatibility

---

## 3. Test Data Management

### Isolation
- Each test uses independent data
- Auto-cleanup after tests
- Use factory pattern for test data generation

### Data Factory Example

```python
import factory
from modules.core.db import FactOrder

class FactOrderFactory(factory.Factory):
    class Meta:
        model = FactOrder

    order_id = factory.Sequence(lambda n: f"ORD{n:06d}")
    platform_code = "shopee"
    shop_id = "shop123"
    total_amount = factory.Faker("pydecimal", left_digits=5, right_digits=2, positive=True)
```

### Cleanup Strategies
- Transaction rollback (preferred)
- pytest fixture cleanup
- Separate test database

---

## 4. Test Tools

| Tool | Purpose |
|------|---------|
| pytest | Unit testing, fixtures, parameterization |
| pytest-asyncio | Async function testing |
| pytest-cov | Coverage reporting |
| FastAPI TestClient | API endpoint testing |
| Playwright | E2E browser automation |
| Vitest | Vue 3 component testing |
| Vue Test Utils | Vue component testing utilities |
| @testing-library/vue | Vue component testing library |

---

## 5. Test Best Practices

### Naming Convention

Format: `test_<feature>_<scenario>_<expected_result>`

```python
def test_create_order_with_valid_data_should_succeed():
    pass

def test_create_order_with_invalid_order_id_should_fail():
    pass
```

### Structure: AAA Pattern

- **Arrange**: Set up test data and preconditions
- **Act**: Execute the action being tested
- **Assert**: Verify the outcome

### Coverage Requirements

- Each test must be independent and repeatable
- Test boundary values (max, min)
- Test error cases (bad input, null values)
- Test normal/happy path

---

## 6. Coverage Targets

### Backend

| Module | Target |
|--------|--------|
| Core modules (DB, ETL, API core) | >= 80% |
| Utility modules (helpers, UI components) | >= 50% |
| Critical business (finance, orders) | 100% |

### Frontend

| Module | Target |
|--------|--------|
| Core components | >= 70% |
| Utility functions | >= 80% |
| Pinia stores | >= 80% |
| API wrappers | >= 60% |

### Configuration

```ini
[coverage:run]
source = backend,modules
omit = */tests/*,*/migrations/*

[coverage:report]
precision = 2
show_missing = True
skip_covered = False
```

---

## 7. Code Review Process

### Peer Review Requirements
- All code changes require at least 1 reviewer
- Use GitHub Pull Request or GitLab Merge Request
- Checklist: correctness, standards, performance, security
- CI must pass before merge

### Review Checklist

- [ ] Feature correctly implemented?
- [ ] Code follows project standards?
- [ ] No performance issues?
- [ ] No security issues?
- [ ] Test coverage adequate?
- [ ] Documentation updated?

---

## 8. Static Analysis Tools

### Backend (Python)

| Tool | Purpose | Key Config |
|------|---------|------------|
| Ruff | PEP 8, imports, unused vars | `line-length = 88`, `target-version = "py311"` |
| Pylint | Complexity, naming, style | Default |
| mypy | Type checking | `python_version = 3.11`, `warn_return_any = True` |
| bandit | Security vulnerabilities | SQL injection, hardcoded passwords |
| Black | Code formatting | `line-length = 88` |
| isort | Import ordering | `profile = "black"` |

### Frontend (JavaScript/Vue)

| Tool | Purpose |
|------|---------|
| ESLint | Vue 3 + JS code standards |
| Prettier | Unified formatting (semi: false, singleQuote: true, tabWidth: 2) |

### Pre-commit Hooks

```yaml
repos:
  - repo: https://github.com/psf/black
    hooks:
      - id: black
  - repo: https://github.com/pycqa/isort
    hooks:
      - id: isort
```

---

## 9. Code Complexity Limits

### Backend

| Metric | Limit |
|--------|-------|
| Function cyclomatic complexity | <= 10 |
| Function length | <= 50 lines |
| Class complexity | <= 50 |
| Class length | <= 500 lines |

### Frontend (Vue)

| Metric | Limit |
|--------|-------|
| Component lines | <= 500 |
| Computed properties | <= 10 |
| Methods | <= 20 |
| Props | <= 10 |

---

## 10. Performance Benchmarks

### API Benchmarks

| Metric | Target |
|--------|--------|
| Response time (P95) | < 500ms |
| Throughput (QPS) | > 100 |
| Concurrent users | 100 |

### Database Benchmarks

| Metric | Target |
|--------|--------|
| Slow queries | < 100ms |
| All queries use indexes | Yes |
| Connection pool | properly configured |

### Batch Processing Benchmarks

| Operation | Target |
|-----------|--------|
| File scanning | >= 500 files/sec |
| Excel parsing | >= 1000 rows/sec |
| Data ingestion | >= 1000 rows/sec |

### Frontend Performance

| Metric | Target |
|--------|--------|
| First paint | < 3s |
| Component render | < 100ms |
| API response (P95) | < 500ms |
| Bundle size (gzipped) | < 2MB |

---

## 11. Documentation Requirements

### Function Documentation (Google-style docstring)

```python
def create_order(order_data: dict, db: AsyncSession) -> FactOrder:
    """Create an order.

    Args:
        order_data: Order data dict with order_id, total_amount, etc.
        db: Async database session.

    Returns:
        FactOrder: Created order object.

    Raises:
        ValidationError: Data validation failure.
        BusinessError: Business rule violation (e.g., insufficient stock).
    """
    pass
```

### Type Annotations
- All function signatures must have type hints (PEP 484)
- Key variables should have type annotations
- Return types must be explicit

### API Documentation
- All APIs must have OpenAPI docs
- Include request and response examples

### Architecture Documentation
- Major changes must update architecture docs
- Record important design decisions (ADR)

---

## 12. CI Pipeline

### Checks Run on Every PR

1. Backend: Ruff, Pylint, mypy
2. Frontend: ESLint, Prettier
3. Unit tests
4. Coverage check (fail if below target)
5. Security scan (bandit)

---

## 13. Frontend Code Quality

### Vue Component Quality

- Use single-file components (.vue)
- Prefer Composition API
- Split components > 500 lines
- All Props must have types and defaults

### Frontend Code Review Checklist

**Component review**:
- [ ] Clear structure (template, script, style)
- [ ] Composition API used
- [ ] Props typed with defaults
- [ ] Computed properties return valid values
- [ ] Critical logic has error handling
- [ ] Null-safety (optional chaining, defaults)

**Quality review**:
- [ ] Prettier-formatted
- [ ] No ESLint errors/warnings
- [ ] No unused variables/imports
- [ ] Function complexity <= 10
- [ ] Component <= 500 lines

**Performance review**:
- [ ] Route lazy-loading
- [ ] Image lazy-loading
- [ ] Debounce/throttle used appropriately
- [ ] No unnecessary re-renders

**Security review**:
- [ ] No XSS vulnerabilities (avoid innerHTML, use v-text)
- [ ] No sensitive data leaks
- [ ] Dependencies have no known vulnerabilities

---

**Last updated**: 2026-03-16
**Status**: Production-ready (v4.20.0)
