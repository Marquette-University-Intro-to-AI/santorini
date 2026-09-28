"""Tests for the ``run_santorini`` command-line interface.

Covers bot loading (valid, missing file, missing ``choose_action``),
argument defaults, the error path, and the per-game display output.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import run_santorini
from run_santorini import _build_parser, _load_bot, main

SRC = Path(run_santorini.__file__).resolve().parent

_QUICK_BOT = """\
def choose_action(state, legal_actions, time_limit):
    return legal_actions[0]
"""


def _write_bot(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


# --- _load_bot -----------------------------------------------------------


def test_load_bot_returns_choose_action(tmp_path: Path) -> None:
    bot = _write_bot(tmp_path, "quick_bot.py", _QUICK_BOT)

    choose_action = _load_bot(str(bot))

    assert callable(choose_action)
    assert choose_action.__name__ == "choose_action"


def test_load_bot_starter_bot_file() -> None:
    choose_action = _load_bot(str(SRC / "starter_bot.py"))

    assert callable(choose_action)


def test_load_bot_missing_file_raises(tmp_path: Path) -> None:
    # Characterization: for a path whose file does not exist, the importlib
    # loader raises FileNotFoundError; no module spec can be created, so the
    # documented ValueError is NOT produced. main() only catches ValueError,
    # so this propagates as an unhandled traceback (see test below).
    with pytest.raises(FileNotFoundError):
        _load_bot(str(tmp_path / "does_not_exist.py"))


def test_load_bot_without_choose_action_raises(tmp_path: Path) -> None:
    bot = _write_bot(tmp_path, "bad_bot.py", "x = 1\n")

    with pytest.raises(ValueError, match="choose_action"):
        _load_bot(str(bot))


# --- _build_parser -------------------------------------------------------


def test_parser_defaults() -> None:
    args = _build_parser().parse_args(["--bot1", "a.py", "--bot2", "b.py"])

    assert args.bot1 == "a.py"
    assert args.bot2 == "b.py"
    assert args.num_games == 1
    assert args.time_limit == 2.0
    assert args.seed == 0


def test_parser_explicit_values() -> None:
    args = _build_parser().parse_args(
        ["--bot1", "a.py", "--bot2", "b.py", "--num-games", "3", "--time-limit", "1.5", "--seed", "7"]
    )

    assert args.num_games == 3
    assert args.time_limit == 1.5
    assert args.seed == 7


def test_parser_requires_both_bots() -> None:
    with pytest.raises(SystemExit):
        _build_parser().parse_args(["--bot1", "a.py"])


# --- main ----------------------------------------------------------------


def test_main_runs_games_and_returns_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bot_a = _write_bot(tmp_path, "bot_a.py", _QUICK_BOT)
    bot_b = _write_bot(tmp_path, "bot_b.py", _QUICK_BOT)

    exit_code = main(["--bot1", str(bot_a), "--bot2", str(bot_b), "--num-games", "2", "--seed", "42"])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "=== Game 1 ===" in out
    assert "=== Game 2 ===" in out
    assert "Winner: " in out
    assert "Loser: " in out
    assert "Reason: " in out
    assert "Turns played: " in out


def test_main_prints_detail_line_when_present(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exploding = _write_bot(
        tmp_path,
        "exploding.py",
        "def choose_action(state, legal_actions, time_limit):\n    raise RuntimeError('boom')\n",
    )
    other = _write_bot(tmp_path, "other.py", _QUICK_BOT)

    exit_code = main(["--bot1", str(exploding), "--bot2", str(other), "--num-games", "1"])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "Detail: " in out


def test_main_missing_bot_file_propagates(tmp_path: Path) -> None:
    # Characterization: the documented error path (print "Error: ..." and
    # return 1) does NOT cover missing files, because _load_bot raises
    # FileNotFoundError, which main() does not catch. Observed today: an
    # unhandled exception escapes main(). If this is ever fixed to return 1
    # with a friendly message, this test must be updated accordingly.
    good = _write_bot(tmp_path, "good.py", _QUICK_BOT)

    with pytest.raises(FileNotFoundError):
        main(["--bot1", str(tmp_path / "missing.py"), "--bot2", str(good)])


def test_main_bot_without_choose_action_returns_one(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    good = _write_bot(tmp_path, "good.py", _QUICK_BOT)
    bad = _write_bot(tmp_path, "bad.py", "x = 1\n")

    exit_code = main(["--bot1", str(good), "--bot2", str(bad)])
    err = capsys.readouterr().err

    assert exit_code == 1
    assert "choose_action" in err
