import shutil

import pytest

from pathlib import Path

from wfx_panel import updater


def test_find_repo_root_walks_up(tmp_path):
    root = tmp_path / "repo"
    nested = root / "dist" / "WFX-Panel"
    nested.mkdir(parents=True)
    (root / ".git").mkdir()
    assert updater.find_repo_root(nested) == root


def test_check_for_updates_reports_available(monkeypatch, tmp_path):
    (tmp_path / ".git").mkdir()
    outputs = {
        ("branch", "--show-current"): "main",
        ("status", "--porcelain"): "",
        ("rev-parse", "HEAD"): "a" * 40,
        ("fetch", "--quiet", "origin", "main"): "",
        ("rev-parse", "refs/remotes/origin/main"): "b" * 40,
        ("cat-file", "-e", f"{'b' * 40}^{{commit}}"): "",
        ("remote", "get-url", "origin"): "https://example.test/repo.git",
        ("rev-parse", "refs/heads/main"): "a" * 40,
        ("rev-list", "--count", f"{'a' * 40}..{'b' * 40}"): "3",
    }
    monkeypatch.setattr(updater.shutil, "which", lambda _name: "git")
    monkeypatch.setattr(
        updater, "_git", lambda _root, *args, **_kwargs: outputs[args]
    )
    result = updater.check_for_updates(tmp_path)
    assert result["code"] == "UPDATE_AVAILABLE"
    assert result["can_update"] is True
    assert result["behind"] == 3


def test_dirty_worktree_never_auto_updates(monkeypatch, tmp_path):
    (tmp_path / ".git").mkdir()
    outputs = {
        ("branch", "--show-current"): "main",
        ("status", "--porcelain"): " M local.py",
        ("rev-parse", "HEAD"): "a" * 40,
        ("fetch", "--quiet", "origin", "main"): "",
        ("rev-parse", "refs/remotes/origin/main"): "b" * 40,
        ("cat-file", "-e", f"{'b' * 40}^{{commit}}"): "",
        ("remote", "get-url", "origin"): "https://example.test/repo.git",
        ("rev-parse", "refs/heads/main"): "a" * 40,
        ("rev-list", "--count", f"{'a' * 40}..{'b' * 40}"): "1",
    }
    monkeypatch.setattr(updater.shutil, "which", lambda _name: "git")
    monkeypatch.setattr(
        updater, "_git", lambda _root, *args, **_kwargs: outputs[args]
    )
    result = updater.check_for_updates(tmp_path)
    assert result["code"] == "WORKTREE_DIRTY"
    assert result["can_update"] is False


def test_schedule_update_builds_from_git_without_release(
    monkeypatch, tmp_path
):
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".git").mkdir()
    (root / "build-panel.ps1").write_text("# build", encoding="utf-8")
    local_data = tmp_path / "local"
    monkeypatch.setenv("LOCALAPPDATA", str(local_data))
    monkeypatch.setattr(updater.tempfile, "gettempdir", lambda: str(tmp_path))
    launched = []
    monkeypatch.setattr(
        updater.subprocess,
        "Popen",
        lambda args, **kwargs: launched.append((args, kwargs)),
    )
    state = {
        "can_update": True,
        "repo_root": str(root),
        "branch": "main",
        "target_branch": "main",
        "previous_branch": "main",
        "previous_sha": "a" * 40,
        "expected_sha": "b" * 40,
    }
    helper = updater.schedule_update(
        state,
        current_pid=123,
        executable=root / "dist" / "WFX-Panel" / "WFX-Panel.exe",
    )
    content = helper.read_text(encoding="utf-8-sig")
    assert "git pull --ff-only origin $targetBranch" in content
    assert "Remote commit changed" in content
    assert "git reset --hard $previousSha" in content
    assert "UPDATE_ROLLED_BACK" in content
    assert "Fast-forward pull failed" in content
    assert "New version build failed" in content
    assert "build-panel.ps1" in content
    assert "release" not in content.lower()
    assert launched


def test_stable_channel_targets_main_from_feature_branch(monkeypatch, tmp_path):
    (tmp_path / ".git").mkdir()
    outputs = {
        ("branch", "--show-current"): "feature",
        ("status", "--porcelain"): "",
        ("rev-parse", "HEAD"): "a" * 40,
        ("fetch", "--quiet", "origin", "main"): "",
        ("rev-parse", "refs/remotes/origin/main"): "b" * 40,
        ("cat-file", "-e", f"{'b' * 40}^{{commit}}"): "",
        ("remote", "get-url", "origin"): "https://example.test/repo.git",
        ("rev-parse", "refs/heads/main"): "c" * 40,
        ("rev-list", "--count", f"{'c' * 40}..{'b' * 40}"): "2",
    }
    monkeypatch.setattr(updater.shutil, "which", lambda _name: "git")
    monkeypatch.setattr(
        updater, "_git", lambda _root, *args, **_kwargs: outputs[args]
    )
    result = updater.check_for_updates(tmp_path, channel="stable")
    assert result["can_update"] is True
    assert result["target_branch"] == "main"
    assert result["previous_branch"] == "feature"
    assert result["expected_sha"] == "b" * 40


def test_consume_update_result_is_one_shot(tmp_path):
    path = tmp_path / "update-result.json"
    path.write_text(
        '{"ok": true, "code": "UPDATE_INSTALLED"}',
        encoding="utf-8",
    )
    result = updater.consume_update_result(tmp_path)
    assert result["code"] == "UPDATE_INSTALLED"
    assert updater.consume_update_result(tmp_path) is None


def test_real_git_repository_detects_exact_remote_commit(tmp_path):
    if shutil.which("git") is None:
        pytest.skip("git unavailable")

    remote = tmp_path / "remote.git"
    seed = tmp_path / "seed"
    installed = tmp_path / "installed"

    def git(cwd, *args):
        return updater._git(cwd, *args)

    try:
        git(tmp_path, "init", "--bare", str(remote))
    except OSError as error:
        # Python 3.14 trên một số Windows CI không duplicate được pytest's
        # captured std handles (WinError 6). Unit tests SHA/rollback vẫn chạy;
        # chỉ bỏ qua integration tiến trình Git trong đúng môi trường đó.
        if getattr(error, "winerror", None) == 6:
            pytest.skip("Windows subprocess capture handle unavailable")
        raise
    seed.mkdir()
    git(seed, "init", "-b", "main")
    git(seed, "config", "user.email", "test@example.invalid")
    git(seed, "config", "user.name", "Updater Test")
    (seed / "version.txt").write_text("v1", encoding="utf-8")
    git(seed, "add", "version.txt")
    git(seed, "commit", "-m", "v1")
    git(seed, "remote", "add", "origin", str(remote))
    git(seed, "push", "-u", "origin", "main")
    git(tmp_path, "clone", "--branch", "main", str(remote), str(installed))

    (seed / "version.txt").write_text("v2", encoding="utf-8")
    git(seed, "add", "version.txt")
    git(seed, "commit", "-m", "v2")
    git(seed, "push")
    expected = git(seed, "rev-parse", "HEAD")

    state = updater.check_for_updates(installed, channel="stable")
    assert state["code"] == "UPDATE_AVAILABLE"
    assert state["can_update"] is True
    assert state["expected_sha"] == expected
    assert state["version"] == expected[:10]
