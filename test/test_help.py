"""Cheap insurance: --help exits 0 and mentions every flag."""

FLAGS = [
    "--agent", "--all-detected", "--scope", "--claude-variant",
    "--claude-mode", "--source", "--block-id", "--project-dir",
    "--copy-only", "--remove", "--interactive", "--list", "--json",
    "--yes", "--quiet", "--help",
]


def test_help_exits_zero_and_mentions_every_flag(run):
    r = run(["--help"])
    assert r.returncode == 0
    for flag in FLAGS:
        assert flag in r.stdout, flag
