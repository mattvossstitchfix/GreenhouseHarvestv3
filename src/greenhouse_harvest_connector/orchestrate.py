from __future__ import annotations

import argparse
from typing import Any

from .config import GreenhouseConfig, RedshiftConfig
from .harvest import HarvestClient
from .sinks import RedshiftSink


DEFAULT_ENDPOINTS = ["applications", "jobs", "candidates"]


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
        default=DEFAULT_ENDPOINTS,
        help="Endpoints to load. Defaults to applications jobs candidates.",
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
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    greenhouse_config = GreenhouseConfig.from_env()
    redshift_config = RedshiftConfig.from_env()
    client = HarvestClient(greenhouse_config)
    sink = RedshiftSink(redshift_config)
    filters_by_endpoint = _parse_filter_group(args.filter)

    total_records = 0
    for endpoint in args.endpoints:
        endpoint_filters = filters_by_endpoint.get(endpoint, {})
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

    print(f"Completed Redshift orchestration for {len(args.endpoints)} endpoint(s), {total_records} record(s) total.")


if __name__ == "__main__":
    main()
