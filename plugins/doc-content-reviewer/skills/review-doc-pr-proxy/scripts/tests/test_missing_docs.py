from scripts import missing_docs, profile

PROXY = profile.load("proxy")


def test_docs_only_pr_runs_full_review():
    r = missing_docs.classify(["docs/content/reference/install-configuration/entrypoints.md"], PROXY)
    assert r["action"] == "full-review" and not r["run_missing_docs"]


def test_code_only_pr_runs_missing_docs_only():
    r = missing_docs.classify(["pkg/config/static/entrypoints.go"], PROXY)
    assert r["action"] == "missing-docs-only"
    assert r["user_facing_code"][0]["doc_targets"] == [
        "docs/content/reference/install-configuration/entrypoints.md"
    ]


def test_tests_and_refactors_are_silent():
    r = missing_docs.classify(
        ["pkg/middlewares/retry/retry_test.go", "pkg/server/server.go", "README.md"], PROXY
    )
    assert r["action"] == "silent"


def test_middleware_name_alias_maps_to_doc_page():
    r = missing_docs.classify(["pkg/middlewares/ratelimiter/rate_limiter.go"], PROXY)
    assert r["user_facing_code"][0]["doc_targets"] == [
        "docs/content/reference/routing-configuration/http/middlewares/ratelimit.md"
    ]


def test_docs_and_code_run_both_paths():
    r = missing_docs.classify(
        ["docs/content/reference/routing-configuration/http/middlewares/retry.md",
         "pkg/middlewares/retry/retry.go"], PROXY)
    assert r["action"] == "full-review" and r["run_missing_docs"]


def test_generated_file_edit_is_reported():
    r = missing_docs.classify(
        ["docs/content/reference/install-configuration/configuration-options.md"], PROXY)
    assert r["generated_touched"]


def test_muxer_and_acme_map_to_their_doc_areas():
    r = missing_docs.classify(["pkg/muxer/http/matcher.go", "pkg/provider/acme/provider.go"], PROXY)
    areas = {e["file"]: e["doc_targets"] for e in r["user_facing_code"]}
    assert any("rules-and-priority" in t for t in areas["pkg/muxer/http/matcher.go"])
    assert areas["pkg/provider/acme/provider.go"] == [
        "docs/content/reference/install-configuration/tls/certificate-resolvers/"
    ]
