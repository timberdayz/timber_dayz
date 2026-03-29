# Shopee Login V2 Design

**Date:** 2026-03-28

## Goal

Add a canonical Shopee China login component that uses `account.login_url` as the only entry, supports account/password submission, standard OTP pause-resume, forces OTP back to phone mode when the page lands on email verification, and only reports success after the seller homepage is actually ready.

## Evidence Summary

- Login page comes from `https://seller.shopee.cn/account/signin...` and is already stored in account management.
- Wrong credentials stay on the sign-in page and surface an inline form error.
- Correct credentials open an OTP overlay on the same page.
- OTP can switch between phone verification and email verification.
- Phone verification is the only supported runtime path for this component.
- A wrong OTP shows an inline OTP error and remains on the OTP overlay.
- A correct OTP reaches the seller homepage at `https://seller.shopee.cn/?cnsc_shop_id=...`.
- Homepage readiness can be observed from the seller top bar, account area, and left navigation.

## Component Boundaries

- Input source:
  - `ctx.account.login_url`
  - `ctx.account.username`
  - `ctx.account.password`
  - `ctx.config.params.captcha_code` or `ctx.config.params.otp`
- Output:
  - `LoginResult(success=True, message="ok")` only after homepage readiness
  - `LoginResult(success=False, message=...)` for credential or OTP failures
  - `VerificationRequiredError("otp", screenshot_path)` when OTP is required but no runtime OTP is supplied

## Runtime Flow

1. If current page already looks logged in, return success after best-effort post-login cleanup.
2. If resume params contain OTP, continue from the current OTP overlay instead of restarting login.
3. Navigate to `account.login_url`.
4. If navigation already lands on a logged-in homepage, return success.
5. Detect and fill the username and password form.
6. Submit the login form.
7. After submission:
   - If credential error text is visible, return failure.
   - If homepage is ready, return success.
   - If OTP overlay is visible, continue into OTP handling.
8. OTP handling:
   - If the page is in email verification mode, click the switch back to phone verification.
   - If no OTP value is supplied, capture a screenshot and raise `VerificationRequiredError("otp", screenshot_path)`.
   - If OTP value is supplied, fill it, confirm, and inspect the result.
9. After OTP submission:
   - If OTP error text is visible, return failure.
   - If homepage is ready, return success.
   - Otherwise report a concrete failure message.

## Detection Rules

### Login Ready

Treat the page as still unauthenticated when:
- URL contains `/account/signin`
- username/password form is still visible

### OTP Ready

Treat OTP overlay as ready when:
- OTP textbox is visible
- confirm button is visible
- mode label identifies phone or email verification

### Homepage Ready

Treat login as successful only when all of these conditions are met:
- URL host is `seller.shopee.cn`
- URL no longer contains `/account/signin`
- seller top bar or account area is visible
- left navigation is visible

## Error Handling

- Missing `login_url` returns a normal failure result.
- Missing username/password returns a normal failure result.
- Credential errors return explicit failure text.
- OTP errors return explicit failure text.
- Missing OTP at the OTP stage raises verification-required instead of guessing.
- Email OTP mode is not accepted as a terminal state; the component must switch back to phone mode first.

## Testing Strategy

- Unit-test success URL detection.
- Unit-test OTP mode detection helpers.
- Unit-test selection of the phone OTP path when email OTP mode is active.
- Unit-test `VerificationRequiredError("otp", ...)` when OTP is needed but absent.
- Unit-test homepage short-circuit for already logged-in sessions.
- Unit-test canonical file registration expectations by keeping the component at `modules/platforms/shopee/components/login.py`.
