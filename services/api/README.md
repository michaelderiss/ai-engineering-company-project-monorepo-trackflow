# API Configuration

The password recovery flow sends reset links through Resend. Copy the root `.env.example` to `.env`, then set `RESEND_API_KEY` and `RESEND_FROM_EMAIL` to credentials for a verified sender in your Resend account. Never commit `.env` or put provider keys in source code.

The API loads the root `.env` at startup. `PASSWORD_RESET_TOKEN_EXPIRE_MINUTES` defaults to 30, and `BACKOFFICE_URL` defaults to `http://localhost:3000`; the generated reset link points to the backoffice app. `NEXT_PUBLIC_INCIDENTS_API_BASE_URL` configures the backoffice API address.

For local development, Resend delivery failures (missing config, blocked network, rejected sender) automatically fall back to printing the reset link in the API console. This keeps the forgot/reset flow usable without a reachable email provider; real mail delivery still requires a verified Resend sender.

Run the API from the repository root with:

```powershell
uvicorn services.api.main:app --reload
```

The forgot-password endpoint always returns the same confirmation for known and unknown email addresses. Email delivery errors are logged server-side without exposing whether an account exists. Reset tokens are signed, expire at the configured interval, and are recorded as used after a successful password update.