"""
Runs every sample reply through the checker and prints, for each case:
  - PASSED cases: the Explanation
  - FAILED cases: the Explanation (if the reply could be parsed), every
    failure reason, and the retry message that would be sent back to the model

Also cross-checks check_explanation() against check_alert() and compares the
outcome with the case's expected_ok / expected_rules from replySamples.py.
"""

from __future__ import annotations

from app.ai.Reply_checker import (
    check_alert,
    check_explanation,
    retry_feedback,
    CheckResult,
    Failure,
)
from app.ai.Reply_checker.orchestrator import parse_explanation
from app.ai.explanation import Explanation

from .replySamples import CASES

LINE = "=" * 78
THIN = "-" * 78


def run_cases(cases: list[dict]) -> tuple[
    list[tuple[dict, Explanation]],
    list[tuple[dict, Explanation | None, list[Failure]]],
]:
    """Returns (passed, failed).

    passed: (case, Explanation)
    failed: (case, Explanation or None if the reply couldn't be parsed, failures)
    """
    passed: list[tuple[dict, Explanation]] = []
    failed: list[tuple[dict, Explanation | None, list[Failure]]] = []

    for case in cases:
        result: CheckResult = check_alert(
            reply=case["reply"],
            evidence=case["evidence"],
            lang=case["lang"],
            must_mention=case["must_mention"],
        )

        if result.ok:
            passed.append((case, result.explanation))
        else:
            failed.append((case, result.explanation, result.failures))

        _cross_check(case, result)

    return passed, failed


def _cross_check(case: dict, alert_result: CheckResult) -> None:
    """check_explanation() on the parsed Explanation must agree with check_alert()."""
    exp, parse_failures = parse_explanation(case["reply"])
    if exp is None:
        # Nothing to hand to check_explanation; check_alert must report the parse failures.
        assert alert_result.failures == parse_failures, f"{case['id']}: parse failures differ"
        return
    failures = check_explanation(
        exp,
        case["lang"],
        evidence=case["evidence"],
        must_mention=case["must_mention"],
    )
    assert failures == alert_result.failures, f"{case['id']}: check_explanation != check_alert"


def _print_explanation(exp: Explanation | None) -> None:
    if exp is None:
        print("  Explanation: None (reply could not be parsed into an Explanation)")
        return
    print(f"  Title:              {exp.title}")
    print(f"  Explanation:        {exp.explanation}")
    print(f"  Recommended action: {exp.recommended_action}")


def print_report(
    passed: list[tuple[dict, Explanation]],
    failed: list[tuple[dict, Explanation | None, list[Failure]]],
) -> None:
    print(LINE)
    print(f"PASSED CASES ({len(passed)})")
    print(LINE)
    for case, exp in passed:
        print(f"\n[PASS] {case['id']}  (lang={case['lang']})")
        _print_explanation(exp)

    print()
    print(LINE)
    print(f"FAILED CASES ({len(failed)})")
    print(LINE)
    for case, exp, failures in failed:
        print(f"\n[FAIL] {case['id']}  (lang={case['lang']})")
        _print_explanation(exp)
        print("  Failure reasons:")
        for f in failures:
            print(f"    - [{f.rule}] {f.detail}")
        print(f"  Retry message: {retry_feedback(failures)}")

    print()
    print(LINE)
    print("SUMMARY")
    print(LINE)
    print(f"passed: {len(passed)}   failed: {len(failed)}   total: {len(passed) + len(failed)}")

    # Compare actual results with what replySamples.py says should happen.
    mismatches = []
    for case, _exp in passed:
        if not case["expected_ok"]:
            mismatches.append((case["id"], "expected FAIL but passed"))
    for case, _exp, failures in failed:
        rules = {f.rule for f in failures}
        if case["expected_ok"]:
            mismatches.append((case["id"], f"expected PASS but failed: {sorted(rules)}"))
        elif rules != case["expected_rules"]:
            mismatches.append((case["id"], f"rules {sorted(rules)} != expected {sorted(case['expected_rules'])}"))
    if mismatches:
        print("Differences from expectations:")
        for case_id, why in mismatches:
            print(f"  - {case_id}: {why}")
    else:
        print("All results match the expectations in replySamples.py.")


if __name__ == "__main__":
    passed_cases, failed_cases = run_cases(CASES)
    print_report(passed_cases, failed_cases)