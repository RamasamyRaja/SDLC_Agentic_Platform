"""Regression tests for the PARTIAL-validation fix: verdict semantics, classification, redaction, patch safety, ranking."""
from app.core.redaction import redact
from app.models.workflow import CheckStatus, ValidationVerdict
from app.workflow import qa
from app.workflow.development import normalize_path, syntax_error
from app.workflow.gitops import diagnose_http
from app.retrieval import ranking

S = CheckStatus


def r(name, status, *, required=True, kind="check", code=None, output=""):
    return qa.CheckResult(name=name, command=name, status=status, exit_code=code, output=output, required=required, kind=kind)


def verdict(results, **kw):
    return qa.evaluate(results, **kw)["verdict"]


def test_all_required_passed_is_passed():
    assert verdict([r("lint", S.PASSED), r("pytest", S.PASSED, kind="test")]) == "PASSED"


def test_failed_required_check_is_failed():
    assert verdict([r("lint", S.PASSED), r("pytest", S.FAILED, kind="test", code=1)]) == "FAILED"


def test_timeout_is_failed_never_success():
    assert verdict([r("pytest", S.TIMED_OUT, kind="test")]) != "PASSED"


def test_missing_dependency_is_partial_not_passed():
    assert verdict([r("lint", S.PASSED), r("pytest", S.DEPENDENCY_MISSING, kind="test")]) == "PARTIAL"


def test_zero_tests_is_not_success():
    assert verdict([r("pytest", S.NO_TESTS, kind="test")]) != "PASSED"


def test_nothing_executed_is_not_run():
    assert verdict([]) in ("NOT_RUN", "PARTIAL")
    assert verdict([r("pytest", S.BLOCKED, kind="test")]) != "PASSED"


def test_optional_check_failure_does_not_fail_but_is_reported():
    out = qa.evaluate([r("pytest", S.PASSED, kind="test"), r("npm-lint", S.FAILED, required=False, code=1)])
    assert out["verdict"] == "PASSED"
    assert out["advisory"], "advisory failure must still be visible"


def test_expected_tests_missing_blocks_pass():
    assert verdict([r("lint", S.PASSED)], expects_tests=True) != "PASSED"


def test_summary_is_explainable():
    out = qa.evaluate([r("pytest", S.DEPENDENCY_MISSING, kind="test"), r("lint", S.PASSED)])
    assert out["headline"] and out["reasons"]
    assert set(("counts", "required", "executed", "passed")) <= set(out)


def test_legacy_explanation_does_not_rewrite_verdict():
    class C:
        name = "pytest"; status = S.DEPENDENCY_MISSING; exit_code = 1; required = None; kind = None
    out = qa.explain_legacy([C()], verdict="PARTIAL")
    assert out["verdict"] == "PARTIAL"


def test_classify_exit5_is_no_tests():
    assert qa.classify(5, "", kind="test") == S.NO_TESTS


def test_classify_zero_passed_is_no_tests():
    assert qa.classify(0, "============ no tests ran in 0.01s ============", kind="test") in (S.NO_TESTS, S.PASSED)


def test_classify_timeout():
    assert qa.classify(None, "", timed_out=True) == S.TIMED_OUT


def test_classify_local_module_missing_is_failure():
    out = "ModuleNotFoundError: No module named 'mypkg'"
    assert qa.classify(1, out, kind="test", local_modules={"mypkg"}) == S.FAILED


def test_classify_third_party_missing_without_deps_is_dependency_gap():
    out = "ModuleNotFoundError: No module named 'requests'"
    assert qa.classify(1, out, kind="test", local_modules={"mypkg"}, deps_ready=False) == S.DEPENDENCY_MISSING


def test_classify_third_party_missing_with_deps_installed_is_failure():
    out = "ModuleNotFoundError: No module named 'requests'"
    assert qa.classify(1, out, kind="test", local_modules=set(), deps_ready=True) == S.FAILED


def test_redaction_patterns():
    assert "ghp_" not in redact("token ghp_" + "a" * 36)
    assert "secretvalue" not in redact("https://user:secretvalue@github.com/x")
    assert "abcdefghijklmnop" not in redact("Authorization: Bearer abcdefghijklmnop")
    assert redact(None) == "" and redact("plain text") == "plain text"


def test_normalize_path_preserves_dot_dirs():
    assert normalize_path("./a//b.py") == "a/b.py"
    assert normalize_path(".github/x.yml") == ".github/x.yml"


def test_syntax_error_detection():
    assert syntax_error("a.py", "def f(:\n") is not None
    assert syntax_error("a.py", "x = 1\n") is None
    assert syntax_error("a.json", "{bad") is not None
    assert syntax_error("a.txt", "anything (") is None


def test_diagnose_http_messages_are_actionable_and_scrubbed():
    assert "401" in diagnose_http(401, {"message": "Bad credentials"})
    assert "rate limit" in diagnose_http(403, {"message": "API rate limit exceeded"}).lower()
    assert "write access" in diagnose_http(403, {"message": "forbidden"})
    assert "404" in diagnose_http(404, {})
    assert "ghp_" not in diagnose_http(422, {"message": "bad ghp_" + "b" * 36})


def test_rerank_dedupes_and_caps_per_file():
    C = ranking.Candidate
    cands = [C("1", "a.py", None, "def login(): pass", "h1", 0.9), C("2", "a.py", None, "def login(): pass", "h1", 0.89),
             C("3", "a.py", None, "x one", "h3", 0.8), C("4", "a.py", None, "x two", "h4", 0.7), C("5", "a.py", None, "x three", "h5", 0.6),
             C("6", "b.py", None, "other", "h6", 0.5)]
    out = ranking.rerank("login", cands, top_k=10, max_per_file=2)
    ids = [c.chunk_id for c, _ in out]
    assert not ({"1", "2"} <= set(ids))                    # duplicate content collapsed
    assert sum(1 for c, _ in out if c.file_path == "a.py") <= 2
    assert ids[0] in ("1", "2")                            # lexical + vector agree
