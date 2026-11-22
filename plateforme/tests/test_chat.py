"""Chat du dashboard, avec un faux binaire `claude` (aucun appel réel)."""
import json
import time

import pytest

FAKE = r"""#!/usr/bin/env python3
import json, sys
args = sys.argv[1:]
prompt = sys.stdin.read()
with open(__LOG__, "a") as f:
    f.write(json.dumps({"args": args, "prompt": prompt}) + "\n")
sid = args[args.index("--resume") + 1] if "--resume" in args else "sess-123"
def out(d): print(json.dumps(d), flush=True)
out({"type": "system", "subtype": "init", "session_id": sid})
out({"type": "stream_event", "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Je regarde."}}})
out({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t1", "name": "Bash",
     "input": {"command": ".venv/bin/python -m engine regen PB-2026-10-21-2", "description": "Régénère PB-2026-10-21-2"}}]}})
out({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]}})
out({"type": "assistant", "message": {"content": [{"type": "text", "text": "C'est fait : **PB-2026-10-21-2** régénérée."}]}})
out({"type": "result", "subtype": "success", "is_error": False, "result": "C'est fait", "session_id": sid})
"""


@pytest.fixture()
def chat_env(tmp_path, monkeypatch):
    from engine import chat, config

    s = config.settings()
    monkeypatch.setitem(s.raw, "db_path", str(tmp_path / "test.db"))
    log = tmp_path / "calls.jsonl"
    fake = tmp_path / "claude"
    fake.write_text(FAKE.replace("__LOG__", repr(str(log))))
    fake.chmod(0o755)
    monkeypatch.setattr(chat, "_claude_bin", lambda: str(fake))
    return chat, log


def _wait(chat, cid, timeout=10):
    end = time.time() + timeout
    while cid in chat.RUNS and time.time() < end:
        time.sleep(0.05)
    assert cid not in chat.RUNS


def test_conversation_resumes_its_session(chat_env):
    chat, log = chat_env
    c = chat.create()
    chat.send(c["id"], "Régénère la vidéo 2 de mercredi\nplus courte")
    _wait(chat, c["id"])
    conv = chat.get(c["id"])
    assert conv["title"] == "Régénère la vidéo 2 de mercredi"
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant"]
    bot = conv["messages"][1]
    assert "PB-2026-10-21-2" in bot["content"] and not bot["is_error"]
    assert bot["tools"] == [{"label": "Régénère PB-2026-10-21-2", "ok": True}]
    assert "claude_session_id" not in conv

    chat.send(c["id"], "Merci")
    _wait(chat, c["id"])
    calls = [json.loads(l) for l in log.read_text().splitlines()]
    assert "--resume" not in calls[0]["args"]                       # 1er message : repart de zéro
    assert calls[1]["args"][calls[1]["args"].index("--resume") + 1] == "sess-123"   # ensuite : même session
    assert calls[1]["prompt"] == "Merci"


def test_new_conversation_starts_fresh_and_lists(chat_env):
    chat, log = chat_env
    a = chat.create()
    chat.send(a["id"], "Bonjour")
    _wait(chat, a["id"])
    b = chat.create()
    assert chat.get(b["id"])["messages"] == []
    ids = [c["id"] for c in chat.list_conversations()]
    assert set(ids) == {a["id"], b["id"]}
    chat.delete(a["id"])
    assert [c["id"] for c in chat.list_conversations()] == [b["id"]]


def test_command_is_scoped(chat_env):
    chat, _ = chat_env
    cmd = chat.build_cmd(None)
    assert "--resume" not in cmd and "acceptEdits" in cmd and "--strict-mcp-config" in cmd
    assert "Bash(git push:*)" in cmd[cmd.index("--disallowedTools"):]
    assert "Bash(.venv/bin/python -m engine:*)" in cmd
    with pytest.raises(ValueError):
        chat.send(chat.create()["id"], "   ")
