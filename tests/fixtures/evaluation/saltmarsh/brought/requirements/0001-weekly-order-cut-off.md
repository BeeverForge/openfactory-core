# REQ-0001 — Weekly order cut-off

- **Status:** proposed
- **Asked by:** joana
- **Date:** 2026-10-09
- **Supersedes:** —

## Why

The kitchen buys its ingredients on Friday morning, for orders placed until then. An order changed
after that is food bought for nobody.

## What must be true

- [ ] a member can place or change the week's order until Thursday at 18:00
- [ ] after the cut-off the order is shown as closed, with the time it closed

## Out of scope

- orders for more than one week ahead

## Affects

- `saltmarsh/orders.py`

## Open questions

- Is the cut-off the same for every member, or later for the volunteers who cook?

## Decisions taken during execution

| date | decision | who decided, and where |
|---|---|---|
