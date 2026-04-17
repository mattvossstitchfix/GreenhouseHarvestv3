from __future__ import annotations

import argparse
from typing import Any

from .config import GreenhouseConfig, RedshiftConfig
from .endpoints import ALL_KNOWN_LIST_ENDPOINTS, SMOKE_TEST_ENDPOINTS
from .harvest import HarvestClient
from .sinks import RedshiftSink


def _parse_filter_group(values: list[str]) -> dict[str, dict[str, Any]]:
    parsed: dict[str, dict[str, Any]] = {}
    for value in values:
        if "." not in value or "=" not in value:
            raise ValueError(
                f"Invalid filter '{value}'. Expected endpoint.key=value, for example applications.status=active."
            )
        endpoint_and_key, raw_value = value.split("=", 1)
        endpoint, key = endpoint_and_key.split(".", 1)
        parsed.setdefault(endpoint, {})[key] = raw_value
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Load a default set of Greenhouse Harvest v3 endpoints into Redshift."
    )
    parser.add_argument(
        "--endpoints",
        nargs="+",
        default=SMOKE_TEST_ENDPOINTS,
        help="Endpoints to load. Defaults to a small smoke-test set.",
    )
    parser.add_argument(
        "--all-endpoints",
        action="store_true",
        help="Load the full built-in catalog of known top-level Harvest v3 list endpoints.",
    )
    parser.add_argument(
        "--load-mode",
        choices=["append", "truncate", "upsert"],
        default="upsert",
        help="Redshift load behavior for every endpoint in this run.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional per-endpoint max record count for smoke testing.",
    )
    parser.add_argument(
        "--filter",
        action="append",
        default=[],
        help="Endpoint-specific filter in endpoint.key=value form. Repeat for multiple filters.",
    )
    parser.add_argument(
        "--table-prefix",
        default="",
        help="Optional prefix for output tables, e.g. raw_ gives raw_applications.",
    )
    parser.add_argument(
        "--continue-on-error",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Keep going when one endpoint fails. Enabled by default.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    greenhouse_config = GreenhouseConfig.from_env()
    redshift_config = RedshiftConfig.from_env()
    client = HarvestClient(greenhouse_config)
    sink = RedshiftSink(redshift_config)
    filters_by_endpoint = _parse_filter_group(args.filter)
    endpoints = ALL_KNOWN_LIST_ENDPOINTS if args.all_endpoints else args.endpoints

    total_records = 0
    failures: list[tuple[str, str]] = []
    for endpoint in endpoints:
        endpoint_filters = filters_by_endpoint.get(endpoint, {})
        try:
            records = client.fetch_endpoint(
                endpoint=endpoint,
                params=endpoint_filters,
                limit=args.limit,
            )
            extracted_at = client.extraction_timestamp()
            table_name = f"{args.table_prefix}{endpoint.replace('/', '_')}_raw"

            sink.write(
                table_name=table_name,
                records=records,
                extracted_at=extracted_at,
                endpoint=endpoint,
                load_mode=args.load_mode,
            )
            total_records += len(records)
            print(f"Wrote {len(records)} records from '{endpoint}' to redshift table '{table_name}'.")
        except Exception as exc:
            failures.append((endpoint, str(exc)))
            print(f"Failed endpoint '{endpoint}': {exc}")
            if not args.continue_on_error:
                raise

    print(
        f"Completed Redshift orchestration for {len(endpoints)} endpoint(s), "
        f"{total_records} record(s) total, {len(failures)} failure(s)."
    )
    if failures:
        print("Failed endpoints:")
        for endpoint, message in failures:
            print(f" - {endpoint}: {message}")


if __name__ == "__main__":
    main()
