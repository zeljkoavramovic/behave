"""Plan section 9, test 23: encoding (BOM + CRLF preservation)."""

B = b"<!-- BEGIN behave - installed by install.py; --remove uninstalls -->\n"
E = b"<!-- END behave -->\n"


# Test 23: BOM and CRLF/LF preserved outside blocks; block itself uses LF
def test_23_bom_crlf(run, env_for, fake_home, src_file):
    target = fake_home / ".codex" / "AGENTS.md"
    target.parent.mkdir(parents=True)
    original = b"\xef\xbb\xbf# Notes\r\n\r\nwindows text\r\n"
    target.write_bytes(original)

    r = run(["--agent", "codex", "--scope", "user", "--yes", "--source",
             str(src_file)], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr

    data = target.read_bytes()
    assert data.startswith(b"\xef\xbb\xbf")
    assert b"# Notes\r\n\r\nwindows text\r\n" in data
    assert B in data
    assert b"uninstalls -->\n" in data
    assert b"<!-- END behave -->\n\n# Notes\r\n" in data

    r2 = run(["--remove", "--agent", "codex", "--scope", "user", "--yes"],
             env=env_for(fake_home))
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert target.read_bytes() == original
