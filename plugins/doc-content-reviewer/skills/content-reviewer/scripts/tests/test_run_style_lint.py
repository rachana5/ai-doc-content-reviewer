from __future__ import annotations
import json
import subprocess
from pathlib import Path
from unittest import mock

from scripts import run_style_lint

VALE_SAMPLE = json.dumps({
    "docs/foo.md": [
        {
            "Line": 3, "Message": "Use 'use' instead of 'utilize'.",
            "Match": "utilize", "Severity": "warning", "CheckID": "Traefik.Wordiness",
        }
    ]
})

ALEX_SAMPLE = json.dumps([
    {
        "messages": [
            {"line": 5, "message": "\"guys\" may be insensitive", "reason": "guys"}
        ]
    }
])


def test_parse_vale_json_produces_findings():
    findings = run_style_lint.parse_vale_json(VALE_SAMPLE, file="docs/foo.md")
    assert len(findings) == 1
    f = findings[0]
    assert f["layer"] == "style"
    assert f["line"] == 3
    assert "utilize" in f["quote"]
    # Vale flags a violation, it doesn't produce replacement text — this
    # must never be auto-applied regardless of confidence.
    assert f["auto_fixable"] is False


def test_parse_alex_json_produces_findings():
    findings = run_style_lint.parse_alex_json(ALEX_SAMPLE, file="docs/foo.md")
    assert len(findings) == 1
    assert findings[0]["layer"] == "style"
    assert findings[0]["line"] == 5
    assert findings[0]["auto_fixable"] is False


def test_run_degrades_gracefully_when_tools_missing(tmp_path, monkeypatch):
    doc = tmp_path / "foo.md"
    doc.write_text("hello")
    monkeypatch.setattr(run_style_lint, "check_lint_tools", lambda repo_root: {"vale": False, "alex": False})
    result = run_style_lint.run([doc], tmp_path)
    assert result == {"findings": [], "vale_ran": False, "alex_ran": False}


def test_run_invokes_vale_and_alex_when_present(tmp_path, monkeypatch):
    doc = tmp_path / "foo.md"
    doc.write_text("You should utilize this.")
    monkeypatch.setattr(run_style_lint, "check_lint_tools", lambda repo_root: {"vale": True, "alex": True})

    def fake_subprocess_run(cmd, capture_output, text):
        if cmd[0] == "vale":
            return mock.Mock(returncode=0, stdout=VALE_SAMPLE.replace("docs/foo.md", str(doc)), stderr="")
        if cmd[0] == "alex":
            return mock.Mock(returncode=0, stdout=ALEX_SAMPLE, stderr="")
        raise AssertionError(f"unexpected command {cmd}")

    monkeypatch.setattr(run_style_lint.subprocess, "run", fake_subprocess_run)
    result = run_style_lint.run([doc], tmp_path)
    assert result["vale_ran"] is True
    assert result["alex_ran"] is True
    assert len(result["findings"]) == 2


def test_main_prints_json_result(tmp_path, monkeypatch, capsys):
    doc = tmp_path / "foo.md"
    doc.write_text("hello")
    monkeypatch.setattr(run_style_lint, "check_lint_tools", lambda repo_root: {"vale": False, "alex": False})
    exit_code = run_style_lint.main([str(doc), "--repo-root", str(tmp_path)])
    assert exit_code == 0
    result = json.loads(capsys.readouterr().out)
    assert result == {"findings": [], "vale_ran": False, "alex_ran": False}


def test_run_degrades_gracefully_when_vale_subprocess_crashes(tmp_path, monkeypatch, capsys):
    """When vale subprocess.run raises, continue processing; vale_ran stays True but findings not added."""
    doc = tmp_path / "foo.md"
    doc.write_text("hello")
    monkeypatch.setattr(run_style_lint, "check_lint_tools", lambda repo_root: {"vale": True, "alex": False})

    def fake_subprocess_run(cmd, capture_output, text):
        if cmd[0] == "vale":
            raise subprocess.CalledProcessError(1, cmd, output="Vale crashed")
        raise AssertionError(f"unexpected command {cmd}")

    monkeypatch.setattr(run_style_lint.subprocess, "run", fake_subprocess_run)
    result = run_style_lint.run([doc], tmp_path)
    # vale_ran stays True (it was available per check_lint_tools), but findings list is empty
    # because the subprocess crashed
    assert result["vale_ran"] is True
    assert result["findings"] == []
    # Verify warning was printed
    captured = capsys.readouterr()
    assert "[run_style_lint] WARNING: vale failed on" in captured.out
    assert "continuing" in captured.out


def test_run_degrades_gracefully_when_alex_returns_malformed_json(tmp_path, monkeypatch, capsys):
    """When alex returns malformed JSON, json.loads fails; continue processing."""
    doc = tmp_path / "foo.md"
    doc.write_text("hello")
    monkeypatch.setattr(run_style_lint, "check_lint_tools", lambda repo_root: {"vale": False, "alex": True})

    def fake_subprocess_run(cmd, capture_output, text):
        if cmd[0] == "alex":
            # Return malformed JSON
            return mock.Mock(returncode=0, stdout='{"invalid": json}', stderr="")
        raise AssertionError(f"unexpected command {cmd}")

    monkeypatch.setattr(run_style_lint.subprocess, "run", fake_subprocess_run)
    result = run_style_lint.run([doc], tmp_path)
    # alex_ran stays True, but findings list is empty because JSON parsing failed
    assert result["alex_ran"] is True
    assert result["findings"] == []
    # Verify warning was printed
    captured = capsys.readouterr()
    assert "[run_style_lint] WARNING: alex failed on" in captured.out
    assert "continuing" in captured.out


def test_run_continues_processing_other_files_when_one_fails(tmp_path, monkeypatch, capsys):
    """When vale fails on file1 but works on file2, findings from file2 are included."""
    doc1 = tmp_path / "foo.md"
    doc2 = tmp_path / "bar.md"
    doc1.write_text("hello")
    doc2.write_text("You should utilize this.")
    monkeypatch.setattr(run_style_lint, "check_lint_tools", lambda repo_root: {"vale": True, "alex": False})

    call_count = {"vale": 0}

    def fake_subprocess_run(cmd, capture_output, text):
        if cmd[0] == "vale":
            call_count["vale"] += 1
            if call_count["vale"] == 1:
                # First file: raise an error
                raise subprocess.TimeoutExpired(cmd, 30)
            else:
                # Second file: return valid findings
                return mock.Mock(returncode=0, stdout=VALE_SAMPLE.replace("docs/foo.md", str(doc2)), stderr="")
        raise AssertionError(f"unexpected command {cmd}")

    monkeypatch.setattr(run_style_lint.subprocess, "run", fake_subprocess_run)
    result = run_style_lint.run([doc1, doc2], tmp_path)
    # vale_ran is True, and we got findings from the second file
    assert result["vale_ran"] is True
    assert len(result["findings"]) == 1
    # Verify warning was printed for file1
    captured = capsys.readouterr()
    assert "[run_style_lint] WARNING: vale failed on" in captured.out
    assert str(doc1) in captured.out
