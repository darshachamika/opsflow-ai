from unittest.mock import Mock
import pytest
from fastapi import HTTPException
from app.core.approval_auth import Actor
from app.services import approval_resume
from app import approval_resume_worker as cli


@pytest.mark.parametrize("role", ["OPERATOR", "ADMIN"])
def test_nonmanager_never_opens_database(monkeypatch, role):
    engine = Mock()
    monkeypatch.setattr(approval_resume, "engine", engine)
    with pytest.raises(PermissionError):
        approval_resume.process_next(Actor("test", role))
    engine.connect.assert_not_called()


def test_authentication_failure_prevents_execution(monkeypatch):
    monkeypatch.setattr("sys.argv", ["worker", "--once"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: "private")
    monkeypatch.setattr(cli, "checked_actor", Mock(side_effect=HTTPException(401)))
    process = Mock()
    monkeypatch.setattr(cli, "process_next", process)
    monkeypatch.setattr(cli, "engine", Mock())
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 1
    process.assert_not_called()


def test_single_run_passes_authenticated_actor(monkeypatch):
    actor = Actor("manager", "PROCUREMENT_MANAGER")
    monkeypatch.setattr("sys.argv", ["worker", "--once"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: "private")
    monkeypatch.setattr(cli, "checked_actor", lambda _: actor)
    process = Mock(return_value=None)
    monkeypatch.setattr(cli, "process_next", process)
    monkeypatch.setattr(cli, "engine", Mock())
    cli.main()
    process.assert_called_once_with(actor)
