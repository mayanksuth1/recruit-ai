"""LinkedIn sourcing connector — INTENTIONALLY A STUB.

LinkedIn has no public API for profile search or outreach automation, and
scraping or automating a LinkedIn account violates LinkedIn's User Agreement
and risks permanent account bans. Do not implement scraping here.

The supported path is the LinkedIn Recruiter System Connect / Talent
Solutions partner API, which is partner-only (not self-serve): the client
must have a LinkedIn Recruiter contract and apply for API access through
LinkedIn's partner program. If/when the client has those credentials, this
module is the integration point — implement `search_candidates()` against
the partner API and register it alongside the CSV importer.

Until then, sourcing works via CSV/paste import of exported search results
(see app/routers/talent_pool.py), which keeps a human in the loop and stays
within LinkedIn's terms.
"""


class LinkedInNotConfigured(Exception):
    pass


def search_candidates(query: str) -> list[dict]:
    raise LinkedInNotConfigured(
        "LinkedIn sourcing requires partner-tier LinkedIn Recruiter API access. "
        "Export search results to CSV and import them via the Talent Pool page instead."
    )
