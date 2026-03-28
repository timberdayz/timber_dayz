# Database Schema Cleanup Wave 1

## Goal

Define the first executable cleanup wave with a strictly bounded scope after the proof audit reset.

## Approved scope

- `public.target_breakdown`

## Operation strategy

- first migration shape: `archive_rename`
- do not use direct `DROP TABLE` in the first production-facing wave
- rehearse archive/rename on a temporary PostgreSQL database before any production execution

## Explicitly blocked from wave 1

- `public.performance_config`
- `public.sales_campaigns`
- `public.sales_campaign_shops`

## Blocker reason

- current ORM/runtime mapping for those tables still resolves to default schema
- no authoritative `a_class.<table>` runtime proof has been established
- cleanup must wait for schema alignment plus regression coverage

## Required next checks before a real migration file

1. add a migration contract test that allows only `public.target_breakdown`
2. implement a reversible archive/rename migration
3. rehearse upgrade on a temporary PostgreSQL database
4. confirm schema completeness still passes after the rehearsal

## Current status

- completed:
  - migration contract test
  - reversible archive/rename migration file
  - temporary PostgreSQL rehearsal
  - post-rehearsal schema completeness verification
- pending:
  - execution decision for a real environment
