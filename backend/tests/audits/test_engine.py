from app.domains.audits.engine import AuditPageInput, audit_page


def test_audit_flags_missing_title_and_long_slug() -> None:
    result = audit_page(
        AuditPageInput(
            title="",
            slug="x" * 76,
            status="publish",
            post_type="page",
            url="https://example.com/" + ("x" * 76),
            site_url="https://example.com",
        )
    )

    assert result.score < 80
    assert {issue.issue_type for issue in result.issues} == {
        "missing_title",
        "slug_too_long",
    }
