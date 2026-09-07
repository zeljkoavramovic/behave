"""Plan section 9, tests 1-6: inline upsert (the risk center)."""

import json

B = b"<!-- BEGIN behave - installed by install.py; --remove uninstalls -->\n"
E = b"<!-- END behave -->\n"


def codex_args(src, extra=()):
    return ["--agent", "codex", "--scope", "user", "--yes",
            "--source", str(src)] + list(extra)


def target_file(fake_home):
    return fake_home / ".codex" / "AGENTS.md"


# Test 1: create new file (did not exist) -> block + trailing newline
def test_1_create_new_file(run, env_for, fake_home, src_file):
    r = run(codex_args(src_file), env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    data = target_file(fake_home).read_bytes()
    assert data.startswith(B)
    assert b"# RULES\nrules body line\n" in data
    assert data.endswith(E)
    assert data.count(b"<!-- BEGIN behave ") == 1


# Test 2: prepend to existing file without trailing newline -> old content intact
def test_2_prepend_without_trailing_newline(run, env_for, fake_home, src_file):
    target = target_file(fake_home)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"original user notes")
    r = run(codex_args(src_file), env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    data = target.read_bytes()
    assert data.startswith(B)
    assert data.count(b"<!-- BEGIN behave ") == 1
    assert b"original user notes" in data
    # plan 4.1 step 4: a trailing newline is added when the file lacked one
    assert data.endswith(b"original user notes\n")


# Test 3: idempotency: run twice -> identical output, single block
def test_3_double_run_idempotent(run, env_for, fake_home, src_file):
    env = env_for(fake_home)
    run(codex_args(src_file), env=env)
    first = target_file(fake_home).read_bytes()
    r = run(codex_args(src_file), env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    second = target_file(fake_home).read_bytes()
    assert first == second
    assert second.count(b"<!-- BEGIN behave ") == 1


# Test 4: upgrade: old block with different content -> replaced, rest intact
def test_4_upgrade_replaces_old_block(run, env_for, fake_home, tmp_path,
                                      src_file):
    target = target_file(fake_home)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"user text before\n")
    src_a = tmp_path / "a.md"
    src_a.write_bytes(b"# SOURCE A\naaa content\n")
    src_b = tmp_path / "b.md"
    src_b.write_bytes(b"# SOURCE B\nbbb content\n")
    env = env_for(fake_home)
    r1 = run(codex_args(src_a), env=env)
    assert r1.returncode == 0, r1.stdout + r1.stderr
    r2 = run(codex_args(src_b), env=env)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    data = target.read_bytes()
    assert data.count(b"<!-- BEGIN behave ") == 1
    assert b"# SOURCE B" in data
    assert b"# SOURCE A" not in data
    assert b"user text before\n" in data


# Test 5: unrelated `<!-- BEGIN other-id ... -->` blocks untouched
def test_5_foreign_block_untouched(run, env_for, fake_home, src_file):
    foreign = (b"<!-- BEGIN other-id - installed by install.py; "
               b"--remove uninstalls -->\nFOREIGN BODY\n"
               b"<!-- END other-id -->\n")
    target = target_file(fake_home)
    target.parent.mkdir(parents=True)
    target.write_bytes(foreign + b"user tail\n")
    r = run(codex_args(src_file), env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    data = target.read_bytes()
    assert data.startswith(B)
    assert foreign in data
    assert b"user tail\n" in data
    assert data.count(b"<!-- BEGIN behave ") == 1
    assert data.count(b"<!-- BEGIN other-id ") == 1


# Test 6: size check: upserted content > 30 KiB -> warning present, written
def test_6_size_warning(run, env_for, fake_home, tmp_path):
    big = tmp_path / "big.md"
    big.write_bytes(b"# BIG\n" + b"x" * 32000 + b"\n")
    env = env_for(fake_home)
    r = run(codex_args(big), env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "30 KiB" in (r.stdout + r.stderr)
    data = target_file(fake_home).read_bytes()
    assert len(data) > 30720
    assert b"x" * 1000 in data
    home2 = tmp_path / "h2"
    home2.mkdir()
    r2 = run(codex_args(big, ["--json"]), env=env_for(home2))
    assert r2.returncode == 0, r2.stdout + r2.stderr
    payload = json.loads(r2.stdout)
    assert payload["targets"][0]["warning"]
