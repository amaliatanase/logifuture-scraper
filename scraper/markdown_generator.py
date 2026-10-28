"""Renders ``docs/jobs.md`` — company info + the current job listing.

Mirrors the JS template's ``scraper/markdown-generator.js``.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

_MD_SPECIAL = re.compile(r"([#*_\[\]`])")


def _escape_markdown(text: object) -> str:
    return _MD_SPECIAL.sub(r"\\\1", str(text))


def generate_jobs_markdown(company_data: dict, jobs: list[dict]) -> str:
    """``company_data``: id/company/brand/status/location[]/website[]/career[]/lastScraped.
    ``jobs``: url/title/workmode?/location?[]/tags?[]/status?."""
    now = datetime.now(timezone.utc).isoformat()
    lines: list[str] = []

    lines.append(f"# {_escape_markdown(company_data['company'])}")
    lines.append("")
    lines.append("## Company Info")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|-------|-------|")
    lines.append(f"| CIF | {company_data['id']} |")
    if company_data.get("brand"):
        lines.append(f"| Brand | {_escape_markdown(company_data['brand'])} |")
    if company_data.get("status"):
        lines.append(f"| Status | {_escape_markdown(company_data['status'])} |")
    if company_data.get("location"):
        lines.append(f"| Location | {', '.join(_escape_markdown(l) for l in company_data['location'])} |")
    if company_data.get("website"):
        lines.append(f"| Website | {', '.join(f'[{u}]({u})' for u in company_data['website'])} |")
    if company_data.get("career"):
        lines.append(f"| Careers | {', '.join(f'[{u}]({u})' for u in company_data['career'])} |")
    if company_data.get("lastScraped"):
        lines.append(f"| Last Scraped | {company_data['lastScraped']} |")

    lines.append("")
    lines.append(f"## Current Job Listings ({len(jobs)})")
    lines.append("")
    lines.append(f"_Generated: {now}_")
    lines.append("")

    for job in jobs:
        lines.append(f"### {_escape_markdown(job['title'])}")
        lines.append("")
        lines.append(f"- **URL:** [{job['url']}]({job['url']})")
        if job.get("workmode"):
            lines.append(f"- **Work Mode:** {_escape_markdown(job['workmode'])}")
        if job.get("location"):
            lines.append(f"- **Location:** {', '.join(_escape_markdown(l) for l in job['location'])}")
        if job.get("tags"):
            lines.append(f"- **Tags:** {', '.join(_escape_markdown(t) for t in job['tags'])}")
        if job.get("status"):
            lines.append(f"- **Status:** {_escape_markdown(job['status'])}")
        lines.append("")

    return "\n".join(lines)
