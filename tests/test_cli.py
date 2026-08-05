from pathlib import Path

from thread_room.cli import main


def test_cli_new_say_pump(tmp_path: Path, capsys):
    main(
        [
            "new",
            "--title",
            "CLI",
            "--dir",
            str(tmp_path),
            "--cwd",
            str(tmp_path),
            "--id",
            "cli-test",
        ]
    )
    meeting = tmp_path / "cli-test"
    assert (meeting / "room.yaml").is_file()
    main(["say", "-d", str(meeting), "hi", "@mock"])
    main(["pump", "-d", str(meeting)])
    main(["export", "-d", str(meeting)])
    main(["status", "-d", str(meeting)])
    main(["close", "-d", str(meeting)])
    assert (meeting / "export.md").is_file()
    assert (meeting / "thread.jsonl").read_text(encoding="utf-8").count("\n") >= 3
