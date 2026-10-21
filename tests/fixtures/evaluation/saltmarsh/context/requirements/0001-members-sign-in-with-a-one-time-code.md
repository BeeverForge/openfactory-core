# REQ-0001 — Members sign in with a one-time code

- **Status:** accepted
- **Asked by:** joana
- **Date:** 2026-06-02
- **Supersedes:** —

## Why

The kitchen's members share devices at the counter, and a password nobody remembers is a queue at
the door.

## What must be true

- [ ] a member signs in with a six-digit code sent to the e-mail the kitchen holds for them
- [ ] a code works once, and for ten minutes

## Out of scope

- signing in with a social account

## Affects

- `saltmarsh/members.py`

## Decisions taken during execution

| date | decision | who decided, and where |
|---|---|---|
| 2026-06-10 | the code is sent by e-mail only, never by SMS | joana — the product's room |
