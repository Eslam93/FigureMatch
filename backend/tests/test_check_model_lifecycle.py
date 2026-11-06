"""`app.scripts.check_model_lifecycle` — offline checks, the deprecations
parser, and the CLI's exit codes.

No network: the page fetch is always monkeypatched, and the parser runs on
the small synthetic page below (written for these tests, shaped like the
tables OpenAI's deprecations page uses).
"""

from __future__ import annotations

import dataclasses
import io
from datetime import date
from typing import TYPE_CHECKING, Any

import httpx
import pytest

from app.core import model_catalog
from app.scripts import check_model_lifecycle as lifecycle
from app.scripts.check_model_lifecycle import ConfiguredModel, DeprecationRow, Finding

if TYPE_CHECKING:
    from pytest import CaptureFixture, MonkeyPatch

_TODAY = date(2026, 11, 6)
_URL = "https://deprecations.example.test/"

_PAGE = """
<html><body>
<h3>Image models</h3>
<table>
  <thead><tr><th>Shutdown date</th><th>Model snapshot</th><th>Substitute model</th></tr></thead>
  <tbody>
    <tr><td>October 23, 2026</td><td><code>gpt-image-1</code></td>
        <td><code>gpt-image-2.5-sunburst</code> or <code>gpt-image-2.5-flare</code></td></tr>
    <tr><td>Dec 1, 2026</td>
        <td><code>gpt-image-1.5</code> | <code>gpt-image-1.5-2025-12-16</code></td>
        <td><code>gpt-image-2.6-flare</code></td></tr>
    <tr><td>Dec 1, 2026</td><td><code>gpt-image-1-mini</code></td>
        <td><code>gpt-image-2.6-flare</code></td></tr>
    <tr><td>Dec 1, 2026</td><td><code>chatgpt-image-latest</code></td>
        <td><code>gpt-image-2.6-flare</code></td></tr>
  </tbody>
</table>
<h3>DALL-E models</h3>
<table>
  <tr><th>Shutdown date</th><th>Model / system</th><th>Recommended replacement</th></tr>
  <tr><td>2026-05-12</td><td><code>dall-e-2</code></td><td><code>gpt-image-2</code></td></tr>
  <tr><td>2026-05-12</td><td><code>dall-e-3</code></td><td><code>gpt-image-2</code></td></tr>
</table>
<h3>Legacy text models</h3>
<table>
  <tr><th>Shutdown date</th><th>Deprecated model</th><th>Deprecated model price</th>
      <th>Recommended replacement</th></tr>
  <tr><td>2026&#8209;05&#8209;12</td><td>legacy-text-001, legacy-text-002</td><td>$1.00</td>
      <td><code>gpt-5.4-mini</code></td></tr>
  <tr><td>2026-06-01</td></tr>
</table>
<h3>Changelog</h3>
<table>
  <tr><th>Date</th><th>Update</th></tr>
  <tr><td>2026-01-01</td><td><code>gpt-5.4-mini</code> launched</td></tr>
</table>
<table>
  <tr><th>Shutdown date</th><th>System</th><th>Recommended replacement</th></tr>
  <tr><td>2026-08-26</td><td>Old API</td><td>New API</td></tr>
</table>
</body></html>
"""

_DEFAULT_MODELS = (
    ConfiguredModel("OPENAI_TEXT_MODEL", "gpt-5.4-mini-2026-03-17", "text"),
    ConfiguredModel("OPENAI_IMAGE_MODEL", "gpt-image-2.5-flare", "image"),
)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: MonkeyPatch) -> None:
    """Shipped defaults, a pinned clock, and no ambient CI annotations."""
    for var in (
        "OPENAI_TEXT_MODEL",
        "OPENAI_IMAGE_MODEL",
        "AI_PROVIDER_MODE",
        "ENVIRONMENT",
        "GITHUB_ACTIONS",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(model_catalog, "today", lambda: _TODAY)


def _serve(monkeypatch: MonkeyPatch, page: str) -> list[str]:
    """Make the fetch return `page`; returns the list of URLs requested."""
    requested: list[str] = []

    def _fetch(url: str) -> str:
        requested.append(url)
        return page

    monkeypatch.setattr(lifecycle, "fetch_deprecations_page", _fetch)
    return requested


def _levels(findings: list[Finding]) -> list[str]:
    return [finding.level for finding in findings]


# ── parser ─────────────────────────────────────────────────────────────


def test_parser_reads_the_deprecated_model_column_with_dates_and_substitutes() -> None:
    assert lifecycle.parse_deprecations(_PAGE) == [
        DeprecationRow(
            model_ids=("gpt-image-1",),
            shutdown="2026-10-23",
            substitute="gpt-image-2.5-sunburst or gpt-image-2.5-flare",
        ),
        DeprecationRow(
            model_ids=("gpt-image-1.5", "gpt-image-1.5-2025-12-16"),
            shutdown="2026-12-01",
            substitute="gpt-image-2.6-flare",
        ),
        DeprecationRow(
            model_ids=("gpt-image-1-mini",), shutdown="2026-12-01", substitute="gpt-image-2.6-flare"
        ),
        DeprecationRow(
            model_ids=("chatgpt-image-latest",),
            shutdown="2026-12-01",
            substitute="gpt-image-2.6-flare",
        ),
        DeprecationRow(model_ids=("dall-e-2",), shutdown="2026-05-12", substitute="gpt-image-2"),
        DeprecationRow(model_ids=("dall-e-3",), shutdown="2026-05-12", substitute="gpt-image-2"),
        # No <code> in the cell: its text is split into ids. The price
        # column also says "model" but is never taken for the model column.
        DeprecationRow(
            model_ids=("legacy-text-001", "legacy-text-002"),
            shutdown="2026-05-12",
            substitute="gpt-5.4-mini",
        ),
    ]


def test_parser_tolerates_omitted_end_tags() -> None:
    page = (
        "<table><tr><th>Shutdown date<th>Model<th>Replacement"
        "<tr><td>2026-01-02<td><code>old-model</code><td>new-model</table>"
    )
    assert lifecycle.parse_deprecations(page) == [
        DeprecationRow(model_ids=("old-model",), shutdown="2026-01-02", substitute="new-model")
    ]


def test_parser_skips_noise_inside_tables() -> None:
    page = (
        "<table>"
        "<tr><th>Shutdown date</th><th>Model</th><th>Replacement</th></tr>"
        "<tr><th>A second</th><th>header row</th><th>is ignored</th></tr>"
        "<td>a stray cell outside any row</td>"
        "<tr><td>2026-01-01</td><td><code></code></td><td>empty model cell</td></tr>"
        "<tr><td>2026-01-02</td><td><code>real-model</code><code> </code></td><td>y</td></tr>"
        "</table>"
    )
    assert lifecycle.parse_deprecations(page) == [
        DeprecationRow(model_ids=("real-model",), shutdown="2026-01-02", substitute="y")
    ]


def test_parser_handles_tables_without_date_or_substitute_columns() -> None:
    page = "<table><tr><th>Model</th></tr><tr><td><code>lonely-model</code></td></tr></table>"
    assert lifecycle.parse_deprecations(page) == [
        DeprecationRow(model_ids=("lonely-model",), shutdown="", substitute="")
    ]


def test_parser_ignores_pages_without_tables() -> None:
    assert lifecycle.parse_deprecations("<html><p><code>gpt-image-1</code></p></html>") == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2026-05-12", "2026-05-12"),
        ("October 23, 2026", "2026-10-23"),
        ("Dec 1, 2026", "2026-12-01"),
        ("Sept 30, 2026", "2026-09-30"),
        ("at earliest 2024-06-13", "2024-06-13"),
        ("Feb 30, 2026", "Feb 30, 2026"),  # not a real day: left as is
        ("Smarch 3, 2026", "Smarch 3, 2026"),  # not a month
        ("TBD", "TBD"),
    ],
)
def test_shutdown_dates_normalise_to_iso(text: str, expected: str) -> None:
    assert lifecycle._iso_date(text) == expected


# ── online check ───────────────────────────────────────────────────────


def test_model_listed_only_as_a_substitute_is_not_flagged(monkeypatch: MonkeyPatch) -> None:
    """gpt-image-2.5-flare and gpt-5.4-mini appear on the page only as
    replacements (and in a changelog), never as deprecated models."""
    models = (*_DEFAULT_MODELS, ConfiguredModel("OPENAI_TEXT_MODEL", "gpt-5.4-mini", "text"))
    requested = _serve(monkeypatch, _PAGE)

    findings = lifecycle.online_findings(models, url=_URL)

    assert requested == [_URL]
    assert _levels(findings) == ["ok", "ok", "ok"]
    assert "7 rows checked" in findings[0].message


def test_listed_model_is_flagged_with_its_shutdown_and_replacement(
    monkeypatch: MonkeyPatch,
) -> None:
    _serve(monkeypatch, _PAGE)
    model = ConfiguredModel("OPENAI_IMAGE_MODEL", "gpt-image-1", "image")

    findings = lifecycle.online_findings([model], url=_URL)

    assert findings == [
        Finding(
            "error",
            f"OPENAI_IMAGE_MODEL=gpt-image-1 is listed as deprecated on {_URL}: shutdown "
            "2026-10-23, replacement gpt-image-2.5-sunburst or gpt-image-2.5-flare.",
        )
    ]


def test_matching_is_exact_not_by_prefix(monkeypatch: MonkeyPatch) -> None:
    _serve(monkeypatch, _PAGE)
    models = [
        ConfiguredModel("OPENAI_IMAGE_MODEL", "gpt-image", "image"),
        ConfiguredModel("OPENAI_IMAGE_MODEL", "gpt-image-1.5-2025", "image"),
    ]
    assert _levels(lifecycle.online_findings(models, url=_URL)) == ["ok", "ok"]


def test_row_without_a_shutdown_or_substitute_says_so(monkeypatch: MonkeyPatch) -> None:
    bare_table = "<table><tr><th>Model</th></tr><tr><td>dead-model</td></tr></table>"
    _serve(monkeypatch, _PAGE.replace("</body>", f"{bare_table}</body>"))
    model = ConfiguredModel("OPENAI_TEXT_MODEL", "dead-model", "text")

    [finding] = lifecycle.online_findings([model], url=_URL)

    assert finding.level == "error"
    assert "shutdown not given, replacement not given" in finding.message


def test_fetch_failure_cannot_verify(monkeypatch: MonkeyPatch) -> None:
    def _fail(url: str) -> str:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(lifecycle, "fetch_deprecations_page", _fail)

    [finding] = lifecycle.online_findings(_DEFAULT_MODELS, url=_URL)

    assert finding.level == "error"
    assert finding.message.startswith(f"Could not verify against {_URL}: fetch failed")
    assert "ConnectError" in finding.message


def test_http_error_status_is_reported_on_one_line(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    """httpx's HTTPStatusError message contains a newline; the ERROR line
    must still be one line, with no dangling continuation."""

    def _get(url: str, **kwargs: Any) -> httpx.Response:
        return httpx.Response(403, request=httpx.Request("GET", url))

    monkeypatch.setattr(lifecycle.httpx, "get", _get)

    assert lifecycle.main(["--deprecations-url", _URL]) == 1

    lines = capsys.readouterr().out.splitlines()
    prefixes = ("OK: ", "WARNING: ", "ERROR: ", "FAIL: ", "PASS: ")
    assert all(line.startswith(prefixes) for line in lines), lines
    [error] = [line for line in lines if line.startswith("ERROR: ")]
    assert error.startswith(
        f"ERROR: Could not verify against {_URL}: fetch failed (HTTPStatusError: "
    )
    assert "403" in error


def test_page_without_parsable_rows_cannot_verify(monkeypatch: MonkeyPatch) -> None:
    _serve(monkeypatch, "<html><body><p>Something else entirely</p></body></html>")

    [finding] = lifecycle.online_findings(_DEFAULT_MODELS, url=_URL)

    assert finding.level == "error"
    assert "Could not verify" in finding.message
    assert "no deprecation table rows" in finding.message


def test_reworded_table_header_cannot_verify_instead_of_passing(
    monkeypatch: MonkeyPatch,
) -> None:
    """A reworded header makes the parser skip that whole table. The other
    tables still yield rows, so without a canary gpt-image-1 would pass as
    "not listed". The catalogued shutdowns that table held are missing."""
    _serve(monkeypatch, _PAGE.replace("<th>Model snapshot</th>", "<th>Deprecated snapshot</th>"))
    model = ConfiguredModel("OPENAI_IMAGE_MODEL", "gpt-image-1", "image")

    assert lifecycle.online_findings([model], url=_URL) == [
        Finding(
            "error",
            f"Could not verify against {_URL}: models the catalog lists with a shutdown "
            "date are missing from every parsed deprecated-model column (gpt-image-1, "
            "gpt-image-1.5, gpt-image-1.5-2025-12-16, gpt-image-1-mini, chatgpt-image-latest), "
            "so the page layout may have changed.",
        )
    ]


def test_one_missing_catalogued_shutdown_cannot_verify(monkeypatch: MonkeyPatch) -> None:
    dall_e_3_row = (
        "<tr><td>2026-05-12</td><td><code>dall-e-3</code></td>"
        "<td><code>gpt-image-2</code></td></tr>"
    )
    assert dall_e_3_row in _PAGE
    _serve(monkeypatch, _PAGE.replace(dall_e_3_row, ""))

    [finding] = lifecycle.online_findings(_DEFAULT_MODELS, url=_URL)

    assert finding.level == "error"
    assert finding.message.endswith(
        "missing from every parsed deprecated-model column (dall-e-3), "
        "so the page layout may have changed."
    )


def test_fetch_sends_a_browser_user_agent_with_timeout_and_redirects(
    monkeypatch: MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def _get(url: str, **kwargs: Any) -> httpx.Response:
        calls.append((url, kwargs))
        return httpx.Response(200, text="<html></html>", request=httpx.Request("GET", url))

    monkeypatch.setattr(lifecycle.httpx, "get", _get)

    assert lifecycle.fetch_deprecations_page(_URL) == "<html></html>"

    [(url, kwargs)] = calls
    assert url == _URL
    assert kwargs["headers"]["User-Agent"].startswith("Mozilla/5.0")
    assert kwargs["timeout"] == 30.0
    assert kwargs["follow_redirects"] is True


def test_fetch_raises_on_http_error_status(monkeypatch: MonkeyPatch) -> None:
    def _get(url: str, **kwargs: Any) -> httpx.Response:
        return httpx.Response(503, request=httpx.Request("GET", url))

    monkeypatch.setattr(lifecycle.httpx, "get", _get)

    with pytest.raises(httpx.HTTPStatusError):
        lifecycle.fetch_deprecations_page(_URL)


# ── offline check ──────────────────────────────────────────────────────


def test_shipped_defaults_pass_offline() -> None:
    findings = lifecycle.offline_findings(_DEFAULT_MODELS, days=30, on=_TODAY)
    assert _levels(findings) == ["ok", "ok"]


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        (
            ConfiguredModel("OPENAI_TEXT_MODEL", "gpt-9-imaginary", "text"),
            "OPENAI_TEXT_MODEL=gpt-9-imaginary is not in app/core/model_catalog.py",
        ),
        (
            ConfiguredModel("OPENAI_IMAGE_MODEL", "gpt-image-1", "image"),
            "OPENAI_IMAGE_MODEL=gpt-image-1 was shut down by OpenAI on 2026-10-23; "
            "switch to gpt-image-2.5-flare.",
        ),
        (
            ConfiguredModel("OPENAI_TEXT_MODEL", "gpt-image-2.5-flare", "text"),
            "OPENAI_TEXT_MODEL=gpt-image-2.5-flare is catalogued as kind=image, but this "
            "setting needs kind=text.",
        ),
    ],
    ids=["unknown", "retired", "wrong-kind"],
)
def test_offline_problems_are_errors(model: ConfiguredModel, expected: str) -> None:
    [finding] = lifecycle.offline_findings([model], days=30, on=_TODAY)
    assert finding.level == "error"
    assert finding.message.startswith(expected)


def test_shut_down_model_in_the_wrong_slot_is_pointed_at_the_slots_default() -> None:
    """dall-e-3's replacement is an image model, so suggesting it for the
    text setting would be wrong advice."""
    model = ConfiguredModel("OPENAI_TEXT_MODEL", "dall-e-3", "text")

    assert lifecycle.offline_findings([model], days=30, on=_TODAY) == [
        Finding(
            "error",
            "OPENAI_TEXT_MODEL=dall-e-3 was shut down by OpenAI on 2026-05-12; "
            "switch to gpt-5.4-mini-2026-03-17 (the shipped text default).",
        )
    ]


def test_shutting_down_model_in_the_wrong_slot_is_pointed_at_the_slots_default() -> None:
    model = ConfiguredModel("OPENAI_TEXT_MODEL", "gpt-image-1.5", "text")

    assert lifecycle.offline_findings([model], days=30, on=_TODAY) == [
        Finding(
            "error",
            "OPENAI_TEXT_MODEL=gpt-image-1.5 is catalogued as kind=image, but this setting "
            "needs kind=text.",
        ),
        Finding(
            "error",
            "OPENAI_TEXT_MODEL=gpt-image-1.5 shuts down on 2026-12-01, in 25 days; "
            "switch to gpt-5.4-mini-2026-03-17 (the shipped text default).",
        ),
    ]


def test_unpriced_model_inside_the_window_reports_both_problems() -> None:
    model = ConfiguredModel("OPENAI_IMAGE_MODEL", "gpt-image-1.5", "image")

    findings = lifecycle.offline_findings([model], days=30, on=_TODAY)

    assert findings == [
        Finding(
            "error",
            "OPENAI_IMAGE_MODEL=gpt-image-1.5 has no verified price in app/core/model_catalog.py.",
        ),
        Finding(
            "error",
            "OPENAI_IMAGE_MODEL=gpt-image-1.5 shuts down on 2026-12-01, in 25 days; "
            "switch to gpt-image-2.6-flare.",
        ),
    ]


def test_shutdown_beyond_the_window_is_only_a_warning() -> None:
    model = ConfiguredModel("OPENAI_IMAGE_MODEL", "gpt-image-1.5", "image")
    findings = lifecycle.offline_findings([model], days=24, on=_TODAY)
    assert _levels(findings) == ["error", "warning"]


# ── CLI ────────────────────────────────────────────────────────────────


def _give_default_image_model_a_shutdown(monkeypatch: MonkeyPatch, shutdown_on: date) -> None:
    entry = model_catalog.MODEL_CATALOG["gpt-image-2.5-flare"]
    shutting_down = dataclasses.replace(
        entry, shutdown_on=shutdown_on, replacement="gpt-image-2.6-flare"
    )
    patched = {**model_catalog.MODEL_CATALOG, entry.model_id: shutting_down}
    monkeypatch.setattr(model_catalog, "MODEL_CATALOG", patched)


def test_main_passes_offline_with_the_shipped_defaults(capsys: CaptureFixture[str]) -> None:
    assert lifecycle.main(["--no-fetch"]) == 0
    out = capsys.readouterr().out
    assert "OK: OPENAI_TEXT_MODEL=gpt-5.4-mini-2026-03-17" in out
    assert "OK: OPENAI_IMAGE_MODEL=gpt-image-2.5-flare" in out
    assert out.rstrip().endswith("PASS: no problems with the configured OpenAI models.")
    assert "::" not in out


def test_main_fetches_the_default_url_and_passes_when_not_listed(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    requested = _serve(monkeypatch, _PAGE)

    assert lifecycle.main([]) == 0

    # OpenAI's canonical host, so CI doesn't depend on the platform.openai.com redirect.
    assert requested == ["https://developers.openai.com/api/docs/deprecations"]
    assert "is not listed as deprecated" in capsys.readouterr().out


def test_main_fails_when_the_page_lists_a_configured_model(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    flare_row = (
        "<tr><td>2027-01-04</td><td><code>gpt-image-2.5-flare</code></td>"
        "<td><code>gpt-image-2.6-flare</code></td></tr>"
    )
    requested = _serve(monkeypatch, _PAGE.replace("</tbody>", f"{flare_row}</tbody>"))

    assert lifecycle.main(["--deprecations-url", _URL]) == 1

    assert requested == [_URL]
    out = capsys.readouterr().out
    assert "ERROR: OPENAI_IMAGE_MODEL=gpt-image-2.5-flare is listed as deprecated" in out
    assert "FAIL: 1 problem(s)" in out


def test_main_fails_when_it_cannot_verify(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    def _fail(url: str) -> str:
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(lifecycle, "fetch_deprecations_page", _fail)

    assert lifecycle.main([]) == 1
    assert "Could not verify" in capsys.readouterr().out


def test_main_fails_when_settings_refuse_the_configured_model(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    monkeypatch.setenv("OPENAI_IMAGE_MODEL", "gpt-image-1")

    assert lifecycle.main(["--no-fetch"]) == 1

    out = capsys.readouterr().out
    assert "Settings refused the current configuration" in out
    assert "OPENAI_IMAGE_MODEL='gpt-image-1' was shut down by OpenAI on 2026-10-23" in out


def test_main_reads_the_configured_model_from_the_environment(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    # Unknown ids pass `Settings` in local, so the offline check must catch them.
    monkeypatch.setenv("OPENAI_TEXT_MODEL", "gpt-9-imaginary")

    assert lifecycle.main(["--no-fetch"]) == 1
    assert "OPENAI_TEXT_MODEL=gpt-9-imaginary is not in" in capsys.readouterr().out


def test_days_option_sets_the_failure_window(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    _give_default_image_model_a_shutdown(monkeypatch, date(2026, 12, 16))  # 40 days out

    assert lifecycle.main(["--no-fetch"]) == 0
    assert (
        "WARNING: OPENAI_IMAGE_MODEL=gpt-image-2.5-flare shuts down on 2026-12-16, in 40 days"
        in capsys.readouterr().out
    )

    assert lifecycle.main(["--no-fetch", "--days", "45"]) == 1
    assert "ERROR: OPENAI_IMAGE_MODEL=gpt-image-2.5-flare shuts down" in capsys.readouterr().out


def test_github_actions_gets_annotations(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    _give_default_image_model_a_shutdown(monkeypatch, date(2026, 12, 16))
    monkeypatch.setenv("OPENAI_TEXT_MODEL", "gpt-9-imaginary")

    assert lifecycle.main(["--no-fetch"]) == 1

    out = capsys.readouterr().out.splitlines()
    assert any(line.startswith("::error::OPENAI_TEXT_MODEL=gpt-9-imaginary") for line in out)
    assert any(line.startswith("::warning::OPENAI_IMAGE_MODEL=gpt-image-2.5-flare") for line in out)
    assert not any(line.startswith("::ok::") for line in out)


def test_annotation_messages_are_escaped() -> None:
    finding = Finding("error", "100% broken\r\nsecond line")
    assert lifecycle._annotation(finding) == "::error::100%25 broken%0D%0Asecond line"


def test_output_survives_a_console_that_cannot_encode_it(monkeypatch: MonkeyPatch) -> None:
    raw = io.BytesIO()
    ascii_console = io.TextIOWrapper(raw, encoding="ascii", newline="\n")
    monkeypatch.setattr(lifecycle.sys, "stdout", ascii_console)

    lifecycle._emit("replacement gpt-image-2.5-flare \u2192 fine")

    ascii_console.flush()
    assert raw.getvalue() == b"replacement gpt-image-2.5-flare \\u2192 fine\n"
