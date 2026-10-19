"""`python -m app.cli sync` must exit non-zero when a source fails, so a
broken career site shows red in GitHub Actions instead of passing silently."""
import pytest

from app import cli


@pytest.mark.parametrize(
    ("outcomes", "expected"),
    [([True, True], True), ([True, False], False), ([], True)],
)
async def test_sync_company_reports_any_failure(monkeypatch, outcomes, expected) -> None:
    targets = [{"n": i} for i in range(len(outcomes))]
    ran: list[int] = []

    async def fake_load(slug):
        return targets

    async def fake_sync_one(target):
        ran.append(target["n"])
        return outcomes[target["n"]]

    monkeypatch.setattr(cli, "_load_targets", fake_load)
    monkeypatch.setattr(cli, "_sync_one", fake_sync_one)

    assert await cli.sync_company("all") is expected
    # A failure doesn't stop the remaining targets.
    assert ran == list(range(len(outcomes)))


def test_main_exits_nonzero_when_a_sync_fails(monkeypatch) -> None:
    async def failing(slug):
        return False

    monkeypatch.setattr(cli, "sync_company", failing)
    monkeypatch.setattr(cli, "configure_logging", lambda: None)
    monkeypatch.setattr("sys.argv", ["app.cli", "sync", "--company", "acme"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 1
