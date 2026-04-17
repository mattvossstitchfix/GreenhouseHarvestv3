from __future__ import annotations

# This catalog is intentionally limited to top-level Harvest v3 list endpoints
# that can be called generically as GET /v3/<endpoint> without path params.
# Some may still require specific scopes or tenant features to return data.
ALL_KNOWN_LIST_ENDPOINTS = [
    "application_stages",
    "applications",
    "approvers",
    "attachments",
    "candidate_educations",
    "candidate_employments",
    "candidates",
    "custom_field_options",
    "custom_fields",
    "default_interviewers",
    "demographic_answer_options",
    "departments",
    "interviews",
    "job_posts",
    "jobs",
    "offers",
    "offices",
    "openings",
    "prospective_jobs",
    "referrers",
    "scorecards",
    "sources",
    "tracking_links",
    "users",
]

SMOKE_TEST_ENDPOINTS = ["applications", "jobs", "candidates"]
