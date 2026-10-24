# Running SpendSense as a public service

SpendSense can be opened to anyone: they create an account, upload a bank-statement CSV and get charts and saving tips. Because strangers will upload real financial data, read this first.

## What the code already does
| Concern | Safeguard | Setting |
|---|---|---|
| Sign-up spam | 5 sign-ups per hour per address; password blocklist | `RATE_LIMIT_ENABLED`, `PASSWORD_BLOCKLIST_ENABLED` |
| Password guessing | 20 logins/min per address; 5 failures per email locks it for 15 min | |
| Database filling up | Account cap, per-user transaction cap, 2 MB upload limit, 30 imports/hour | `MAX_USERS`, `MAX_TRANSACTIONS_PER_USER` |
| Abuse emergency | Close sign-ups instantly (existing users unaffected) | `ALLOW_REGISTRATION=false` |
| Privacy | Statement file is never stored; only date, shop, amount, category. Download-my-data and delete-account | `/account` page |
| Leaks | Tokens redacted from logs; security headers on API and frontend | |
| Rate limits behind Render's proxy | Reads the real visitor address | `TRUST_PROXY=true` |

## Must-do before real users
1. **Move the database off Render's free Postgres.** It expires 30 days after creation (then is deleted after a grace period). Options:
   - Neon free tier (does not expire): create a project, copy the **direct (non-pooled)** connection string, and set it as `DATABASE_URL` in the Render service's environment. Paste it only in Render, never in chat or Git. Redeploy; migrations run automatically.
   - Or upgrade the Render database to a paid plan.
2. **Set the env vars** from `render.yaml` (`TRUST_PROXY`, `MAX_USERS`, `ALLOW_REGISTRATION`) on the existing service, since a Blueprint only applies them when synced.
3. **Take backups** (`pg_dump` periodically). Free tiers give little or no restore protection.
4. **Read `/privacy`** and make sure it says what you are comfortable promising. Replace the contact (GitHub issues) with a real email if you have one.

## Known limits (be honest about them)
- No email verification or password reset: a forgotten password means the account is lost.
- Login token lives in browser storage; there is no Content-Security-Policy.
- Rate limits and live updates are in memory, so they assume a single server instance.
- Free hosting sleeps when idle (about a minute to wake) and has monthly hour limits.
- Savings tips are rule-based estimates, not financial advice.
- Not audited or legally reviewed. For anything beyond a portfolio project, get a security and privacy review (India: DPDP Act obligations apply to personal data).

## Operating it
- Close sign-ups: set `ALLOW_REGISTRATION=false` in Render.
- Raise capacity: change `MAX_USERS`.
- Remove one person's data on request: they can self-delete in Account.
