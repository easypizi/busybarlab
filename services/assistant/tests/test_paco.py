import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from toy_lair_assistant.agent import AgentResult, ToolCall
from toy_lair_assistant.paco import PacoAgent
from toy_lair_assistant.paco_vault import PacoVault
from toy_lair_assistant.store import MemoryStore
from toy_lair_assistant.zayka_write import ZaykaWrite

ZONE = ZoneInfo("America/Los_Angeles")
NOW = datetime(2026, 9, 22, 15, 4, tzinfo=ZONE)


class ScriptedLLM:
    def __init__(self, scripts: list[AgentResult]) -> None:
        self.scripts = list(scripts)
        self.seen: list[list[dict]] = []

    def complete(self, messages, tools, schemas=None):
        self.seen.append(messages)
        return self.scripts.pop(0)


def _agent(tmp_path: Path, llm: ScriptedLLM, fail: str = "") -> PacoAgent:
    calls: list[list[str]] = []

    def runner(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        calls.append(list(args))
        code = 0
        stderr = ""
        if fail == "push" and args == ["git", "push"]:
            code = 1
        if fail == "auth" and args[:2] == ["git", "pull"]:
            code = 1
            stderr = "Authentication failed for https://github.com/easypizi/zayka.git"
        result = subprocess.CompletedProcess(args, code)
        result.stderr = stderr
        return result

    vault = PacoVault(tmp_path, ZONE)
    writer = ZaykaWrite(tmp_path, runner, ZONE)
    agent = PacoAgent(llm, vault, writer, lambda: NOW, store=MemoryStore())
    agent.git_calls = calls
    return agent


def test_system_prompt_is_paco_without_task_catalog(tmp_path: Path) -> None:
    llm = ScriptedLLM([AgentResult(reply="ok")])
    agent = _agent(tmp_path, llm)
    agent.handle_text("hi")
    system = llm.seen[0][0]["content"]
    assert system.startswith("You are Paco.")
    assert "Inbox:" in system
    assert "t1 " not in system
    assert "Todoist" not in system


def test_inbox_create_tool_reports_write_and_peek_is_inbox(tmp_path: Path) -> None:
    llm = ScriptedLLM(
        [
            AgentResult(
                reply="",
                tool_calls=[
                    ToolCall(
                        "zayka_inbox_create",
                        {
                            "title": "Hire",
                            "body": "A thought",
                            "filename_hint": "hire scope idea",
                        },
                        "c1",
                    )
                ],
            ),
            AgentResult(reply="Записал."),
        ]
    )
    agent = _agent(tmp_path, llm)
    result = agent.handle_text("запиши")
    assert "saved" not in result.reply.lower()
    assert (tmp_path / "00 Inbox" / "2026-09-22-hire-scope-idea.md").exists()
    assert result.peek["kind"] == "inbox"
    assert result.action == "saved"
    note = agent._inbox_create("Hire", "A thought", "other idea")
    assert note == "Wrote to Inbox: Hire"


def test_git_auth_failure_says_to_update_the_token(tmp_path: Path) -> None:
    agent = _agent(tmp_path, ScriptedLLM([]), fail="auth")
    agent._user_text = "запиши"
    note = agent._inbox_create("Hire", "A thought", "hire")
    assert note == "GitHub token expired. Update ZAYKA_REPO_URL."


def test_push_failure_keeps_the_draft(tmp_path: Path) -> None:
    agent = _agent(tmp_path, ScriptedLLM([]), fail="push")
    agent._draft_update(title="Hire", body="keep me")
    agent._user_text = "запиши"
    note = agent._inbox_create("Hire", "keep me", "hire")
    assert note == "Push failed."
    assert "Wrote to Inbox" not in note
    assert agent.store.get_draft("r1-paco", NOW)["body"] == "keep me"
    missed = _agent(
        tmp_path / "miss",
        ScriptedLLM(
            [
                AgentResult(
                    reply="",
                    tool_calls=[
                        ToolCall(
                            "zayka_inbox_create",
                            {"title": "Hire", "body": "keep me", "filename_hint": "hire"},
                            "c1",
                        )
                    ],
                ),
                AgentResult(reply="no"),
            ]
        ),
        fail="push",
    )
    assert missed.handle_text("запиши").action == ""


def test_search_sets_hit_peek(tmp_path: Path) -> None:
    (tmp_path / "10 Evergreen").mkdir()
    (tmp_path / "10 Evergreen" / "atomic-notes.md").write_text(
        "Hiring product for founders.\n",
        encoding="utf-8",
    )
    llm = ScriptedLLM(
        [
            AgentResult(
                reply="",
                tool_calls=[ToolCall("zayka_search", {"query": "hiring"}, "c1")],
            ),
            AgentResult(reply="Three notes, look at the peek."),
        ]
    )
    result = _agent(tmp_path, llm).handle_text("where is hiring")
    assert result.peek["kind"] == "hits"
    assert result.peek["items"][0]["path"].endswith("atomic-notes.md")


def test_agent_has_no_calendar_or_evergreen_tool(tmp_path: Path) -> None:
    agent = _agent(tmp_path, ScriptedLLM([]))
    assert "todoist_add" not in agent.tools
    assert "zayka_evergreen_create" not in agent.tools
    assert set(agent.tools) == {
        "zayka_search",
        "zayka_read",
        "zayka_list_inbox",
        "draft_update",
        "zayka_inbox_create",
        "zayka_daily_append",
    }


def test_draft_update_skips_git_and_keeps_title(tmp_path: Path) -> None:
    agent = _agent(tmp_path, ScriptedLLM([AgentResult(reply="ok")]))
    assert agent._draft_update(title="Hire", body="first") == "Draft updated."
    assert agent._draft_update(body="second") == "Draft updated."
    draft = agent.store.get_draft("r1-paco", NOW)
    assert draft["title"] == "Hire"
    assert draft["body"] == "second"
    assert agent.git_calls == []
    agent.handle_text("ещё мысль")
    system = agent.llm.seen[0][0]["content"]
    assert "title: Hire" in system
    assert "body: second" in system
    long_body = "a" * 1600 + "TAIL"
    agent._draft_update(body=long_body)
    prompt = agent.system_prompt(NOW)
    assert "TAIL" not in prompt
    assert "a" * 1500 in prompt


def test_write_without_save_phrase_does_not_touch_git(tmp_path: Path) -> None:
    agent = _agent(tmp_path, ScriptedLLM([]))
    agent._draft_update(title="Hire", body="long thought")
    agent._user_text = "давай подумаем"
    note = agent._inbox_create(title="Hire", body="long thought")
    assert note == "Not saved. Draft only."
    assert list((tmp_path / "00 Inbox").glob("*.md")) == [] if (tmp_path / "00 Inbox").exists() else True
    assert agent.git_calls == []


def test_save_phrase_writes_draft_body_and_clears_it(tmp_path: Path) -> None:
    agent = _agent(tmp_path, ScriptedLLM([]))
    agent._draft_update(title="Hire", body="full thought", filename_hint="hire scope idea")
    agent._user_text = "запиши"
    note = agent._inbox_create(title="запиши", body="запиши")
    assert note == "Wrote to Inbox: Hire"
    text = (tmp_path / "00 Inbox" / "2026-09-22-hire-scope-idea.md").read_text(encoding="utf-8")
    assert "full thought" in text
    assert agent.store.get_draft("r1-paco", NOW) is None


def test_daily_phrase_appends_draft_body(tmp_path: Path) -> None:
    agent = _agent(tmp_path, ScriptedLLM([]))
    agent._draft_update(body="evening thought")
    agent._user_text = "в дневник"
    note = agent._daily_append("nope")
    assert note == "Added to daily."
    text = (tmp_path / "60 Daily" / "2026" / "09" / "2026-09-22.md").read_text(encoding="utf-8")
    assert "evening thought" in text
    assert "nope" not in text


def test_one_shot_save_without_draft(tmp_path: Path) -> None:
    agent = _agent(tmp_path, ScriptedLLM([]))
    agent._user_text = "запиши: купить молоко"
    note = agent._inbox_create(title="Milk", body="купить молоко", filename_hint="buy milk")
    assert note == "Wrote to Inbox: Milk"
    text = (tmp_path / "00 Inbox" / "2026-09-22-buy-milk.md").read_text(encoding="utf-8")
    assert "купить молоко" in text
