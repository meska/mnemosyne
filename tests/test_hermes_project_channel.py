"""Opt-in project scoping: MNEMOSYNE_PROJECT_CHANNEL=1 puts sessions run inside one git repository
(any of its worktrees) in the channel ``project:<repo>``, so they recall each other's rows and no
other project's."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from mnemosyne_hermes import MnemosyneMemoryProvider, _project_channel_from_cwd


def _git_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "i"], check=True)
    return path


def test_project_from_plain_repo_and_subdir(tmp_path):
    repo = _git_repo(tmp_path / "gnobbi")
    (repo / "src" / "ui").mkdir(parents=True)
    assert _project_channel_from_cwd(repo) == "project:gnobbi"
    assert _project_channel_from_cwd(repo / "src" / "ui") == "project:gnobbi"


def test_linked_worktree_maps_to_main_repository(tmp_path):
    repo = _git_repo(tmp_path / "gnobbi")
    wt = tmp_path / "wt" / "t_1234"
    subprocess.run(["git", "-C", str(repo), "worktree", "add", "-q", "-b", "task", str(wt)], check=True)
    assert (wt / ".git").is_file()
    assert _project_channel_from_cwd(wt) == "project:gnobbi"


def test_no_project_outside_repo_or_for_bad_input(tmp_path):
    plain = tmp_path / "scratch"
    plain.mkdir()
    assert _project_channel_from_cwd(plain) == ""
    assert _project_channel_from_cwd("") == ""
    assert _project_channel_from_cwd(None) == ""


def test_home_rooted_repository_is_not_a_project(tmp_path, monkeypatch):
    home = _git_repo(tmp_path / "home")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    (home / "sub").mkdir()
    assert _project_channel_from_cwd(home / "sub") == ""


def _provider(tmp_path, session, cwd, monkeypatch, enabled=True):
    monkeypatch.setenv("MNEMOSYNE_PROJECT_CHANNEL", "1" if enabled else "0")
    p = MnemosyneMemoryProvider()
    p.initialize(session_id=session, hermes_home=str(tmp_path / "hh"), platform="cli", cwd=str(cwd))
    return p


def test_sessions_of_one_project_share_memory_other_projects_do_not(tmp_path, monkeypatch):
    a = _git_repo(tmp_path / "gnobbi")
    b = _git_repo(tmp_path / "other")
    s1 = _provider(tmp_path, "sess-1", a, monkeypatch)
    assert s1._project_channel == "project:gnobbi"
    s1._beam.remember(content="gnobbi renders avatars with the matrix sdk heroes fallback", source="conversation")

    s2 = _provider(tmp_path, "sess-2", a, monkeypatch)        # new session, same project
    assert "matrix sdk heroes" in s2.prefetch("matrix sdk heroes avatars gnobbi", session_id="sess-2")

    s3 = _provider(tmp_path, "sess-3", b, monkeypatch)        # other project
    assert "matrix sdk heroes" not in s3.prefetch("matrix sdk heroes avatars gnobbi", session_id="sess-3")


def test_global_facts_stay_visible_inside_a_project(tmp_path, monkeypatch):
    a = _git_repo(tmp_path / "gnobbi")
    s1 = _provider(tmp_path, "sess-1", a, monkeypatch)
    s1._beam.remember(content="marco prefers terse italian replies always", source="preference", scope="global")
    s2 = _provider(tmp_path, "sess-2", a, monkeypatch)
    assert "terse italian replies" in s2.prefetch("marco terse italian replies", session_id="sess-2")


def test_disabled_by_default_keeps_session_isolation(tmp_path, monkeypatch):
    a = _git_repo(tmp_path / "gnobbi")
    s1 = _provider(tmp_path, "sess-1", a, monkeypatch, enabled=False)
    assert s1._project_channel == ""
    s1._beam.remember(content="gnobbi renders avatars with the matrix sdk heroes fallback", source="conversation")
    s2 = _provider(tmp_path, "sess-2", a, monkeypatch, enabled=False)
    assert "matrix sdk heroes" not in s2.prefetch("matrix sdk heroes avatars gnobbi", session_id="sess-2")


def test_explicit_channel_id_wins(tmp_path, monkeypatch):
    a = _git_repo(tmp_path / "gnobbi")
    monkeypatch.setenv("MNEMOSYNE_PROJECT_CHANNEL", "1")
    p = MnemosyneMemoryProvider()
    p.initialize(session_id="s", hermes_home=str(tmp_path / "hh"), platform="cli", cwd=str(a), channel_id="team-x")
    assert p._project_channel == ""
