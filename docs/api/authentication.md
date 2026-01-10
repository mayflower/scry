# Authentication

Scry supports LLM-driven authentication for scraping pages that require login.

## How It Works

When `login_params` are provided, the LLM will:

1. **Detect login forms** by analyzing page elements (password inputs, username/email fields, login buttons)
2. **Fill credentials** using the provided username/password
3. **Submit the form** automatically
4. **Proceed with the main task** after authentication

## Usage

Include `login_params` in your scrape request:

```bash
curl -X POST http://localhost:8000/scrape \
  -H 'Content-Type: application/json' \
  -d '{
    "nl_request": "Extract my recent orders",
    "output_schema": {
      "type": "object",
      "properties": {
        "orders": {"type": "array", "items": {"type": "string"}}
      }
    },
    "target_urls": ["https://example-shop.com"],
    "login_params": {
      "username": "user@example.com",
      "password": "secret123"
    }
  }'
```

## Login Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `username` | string | Username or email for login |
| `password` | string | Password for login |

## Form Detection

The LLM looks for common login indicators:

- Input with `type="password"`
- Input with name/id/autocomplete containing "user", "email", "login", "username"
- Buttons with text "Login", "Sign in", "Submit", "Enter"

## Supported Login Types

### Form-Based Login

Standard HTML forms with username/password fields. This is the most common type.

### Multi-Step Login

Some sites split login across multiple pages (email first, then password). The LLM handles this automatically.

## Security Notes

!!! warning "Credential Handling"
    Credentials are only used during exploration. They are **never** embedded in generated scripts.

- Credentials are passed to the LLM for form filling
- Generated Playwright scripts contain no secrets
- Scripts can be safely stored and shared
- Re-running scripts requires fresh credentials

## Troubleshooting

### Login Not Detected

If the LLM doesn't detect a login form:

- Ensure the login page is accessible from the start URL
- Try including "login" or "sign in" in your `nl_request`
- Check if the site uses non-standard login mechanisms

### Authentication Failures

Common causes:

- Incorrect credentials
- CAPTCHA or 2FA requirements
- Rate limiting
- Cookie consent blocking the form
