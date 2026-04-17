# Greenhouse Harvest v3 Connector Starter

This is a small Python starter that:

- Authenticates to Greenhouse Harvest v3 using OAuth 2.0 client credentials.
- Reads paginated list endpoints from Harvest v3.
- Writes records either to Amazon Redshift or Google Sheets.

It is meant to be the thin ingestion layer. If you want analytics-ready models in Redshift, you would usually land raw data first and then transform it with dbt.

## Why this shape

Greenhouse's current documentation says:

- Harvest v3 uses OAuth 2.0 client credentials for custom integrations.
- Access tokens are minted from `https://auth.greenhouse.io/token`.
- List endpoints are cursor-paginated through the `Link` response header.
- List endpoints may require a Site Admin authorizing user.
- Harvest v1 and v2 are deprecated after August 31, 2026.

## Project layout

```text
greenhouse_harvest_connector/
  pyproject.toml
  README.md
  src/greenhouse_harvest_connector/
    cli.py
    config.py
    harvest.py
    sinks.py
```

## Setup

### 1. Create Harvest v3 credentials in Greenhouse

In Greenhouse:

1. Go to `Configure` -> `Dev Center` -> `API Credential Management`.
2. Create `Harvest V3 (OAuth)` credentials.
3. Grant only the scopes you need.
4. Copy the client ID and client secret.

If you want requests attributed to a real Greenhouse user instead of the automatically generated ISU, also capture that Greenhouse `user_id` and set `GREENHOUSE_USER_ID`.

### 2. Create a virtual environment and install dependencies

```bash
cd /Users/matthewvoss/Documents/GitHub/greenhouse_harvest_connector
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 3. Set environment variables

Common Greenhouse variables:

```bash
export GREENHOUSE_CLIENT_ID='your-client-id'
export GREENHOUSE_CLIENT_SECRET='your-client-secret'
export GREENHOUSE_USER_ID='1234567890'   # optional, but often useful
export GREENHOUSE_PER_PAGE='200'         # optional, max 500
```

Redshift variables:

```bash
export REDSHIFT_HOST='your-redshift-host'
export REDSHIFT_DATABASE='analytics'
export REDSHIFT_USER='your-user'
export REDSHIFT_PASSWORD='your-password'
export REDSHIFT_PORT='5439'
export REDSHIFT_SCHEMA='greenhouse_raw'
```

Google Sheets variables:

```bash
export GOOGLE_SERVICE_ACCOUNT_JSON='/absolute/path/to/service-account.json'
export GOOGLE_SHEETS_SPREADSHEET_ID='spreadsheet-id'
export GOOGLE_SHEETS_WORKSHEET='applications_raw'
```

## Usage

### Smoke test against a Harvest endpoint

```bash
python -m greenhouse_harvest_connector.cli \
  --endpoint applications \
  --sink sheets \
  --limit 10
```

### Load applications into Redshift

```bash
python -m greenhouse_harvest_connector.cli \
  --endpoint applications \
  --sink redshift \
  --table-name applications_raw \
  --load-mode upsert
```

### Filtered extract

```bash
python -m greenhouse_harvest_connector.cli \
  --endpoint applications \
  --sink redshift \
  --filter status=active \
  --filter job_ids=12345,67890
```

### Orchestrate the common Redshift loads in one command

```bash
python -m greenhouse_harvest_connector.orchestrate \
  --load-mode upsert \
  --limit 10
```

This loads `applications`, `jobs`, and `candidates` into:

- `applications_raw`
- `jobs_raw`
- `candidates_raw`

You can override the endpoints:

```bash
python -m greenhouse_harvest_connector.orchestrate \
  --endpoints applications jobs candidates interviews \
  --load-mode upsert
```

You can also pass endpoint-specific filters:

```bash
python -m greenhouse_harvest_connector.orchestrate \
  --endpoints applications jobs \
  --filter applications.status=active \
  --filter jobs.status=open
```

## Redshift storage pattern

This starter stores:

- `greenhouse_id` as a top-level lookup column
- `endpoint` so multiple entities can share the same raw pattern safely
- `extracted_at` for load auditing
- `payload` as Redshift `SUPER`

The Redshift writer also creates:

- the target schema if it does not exist
- an `_ingestion_manifest` table in that schema
- optional `upsert` behavior keyed by `greenhouse_id` plus `endpoint`
- optional `truncate` behavior for full refresh loads

That keeps the ingestion layer resilient even if Greenhouse changes nested response shapes. You can then build typed downstream models from `payload`.

### Recommended Redshift schema

Use a dedicated raw schema such as `greenhouse_raw`. Example:

```bash
export REDSHIFT_SCHEMA='greenhouse_raw'
```

Then run:

```bash
python -m greenhouse_harvest_connector.cli \
  --endpoint jobs \
  --sink redshift \
  --table-name jobs_raw \
  --load-mode upsert
```

### dbt handoff pattern

If you want to model these landed tables in dbt, declare them as sources and then flatten from `payload`.

Example source declaration:

```yml
version: 2

sources:
  - name: greenhouse_raw
    database: pnc_prod
    schema: greenhouse_raw
    tables:
      - name: applications_raw
      - name: jobs_raw
      - name: candidates_raw
```

Example staging model:

```sql
with source as (
  select * from {{ source('greenhouse_raw', 'applications_raw') }}
),

renamed as (
  select
    greenhouse_id as application_id,
    extracted_at,
    payload:id::bigint as payload_id,
    payload:status::varchar as status,
    payload:created_at::timestamp as created_at,
    payload:updated_at::timestamp as updated_at,
    payload:candidate_id::bigint as candidate_id,
    payload:job_id::bigint as job_id
  from source
)

select * from renamed
```

## Google Sheets storage pattern

This starter writes:

- one header row
- one row per Greenhouse record
- nested objects and arrays serialized as compact JSON strings

That is good for quick validation, stakeholder review, and low-volume operational reporting, but it is not the best long-term warehouse destination.

## Recommended path

If your goal is durable analytics:

1. Land raw Harvest data in Redshift.
2. Build modeled tables on top with dbt.
3. Publish curated slices to Google Sheets only when a business user really needs them there.

Your workspace already includes Greenhouse-focused dbt packages in `/Users/matthewvoss/Documents/GitHub/pnc_datamart/pnc_datamart/prebuilt_packages`, so Redshift plus dbt is likely the stronger long-term route.

## Good first endpoints

These are usually the first ones to ingest for recruiting analytics:

- `jobs`
- `job_posts`
- `candidates`
- `applications`
- `interviews`
- `users`
- `departments`
- `offices`

## Next improvements

- Add incremental sync windows using `updated_at` filters where supported.
- Batch Redshift writes with staging files and `COPY` for larger extracts.
- Add structured table flattening for a few high-value entities.
- Run the job on a schedule with Airflow, GitHub Actions, ECS, or Lambda.
- Add dbt sources and staging models on top of the raw landing tables.

## Sources

- [Greenhouse Support: Harvest API overview](https://support.greenhouse.io/hc/en-us/articles/360029266032-Harvest-API-overview)
- [Greenhouse Harvest v3 Authentication](https://harvestdocs.greenhouse.io/docs/authentication)
- [Greenhouse Harvest v3 Pagination](https://harvestdocs.greenhouse.io/docs/pagination)
- [Greenhouse Harvest v3 Rate Limiting](https://harvestdocs.greenhouse.io/docs/api-rate-limiting)
