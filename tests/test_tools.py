"""Champion tools return text to the model and paths on the artifact."""

from langchain_core.messages import ToolMessage

from app.assistant.tools import get_champion_build, get_champion_combos


def _tool_call(tool, args: dict, call_id: str = "call_1"):
    return tool.invoke(
        {
            "name": tool.name,
            "type": "tool_call",
            "id": call_id,
            "args": args,
        }
    )


def test_tool_call_puts_paths_on_the_artifact():
    message = _tool_call(get_champion_build, {"champion": "Aatrox", "role": "top"})
    assert isinstance(message, ToolMessage)
    assert message.artifact == ["champion-builds/aatrox/aatrox-build-top.toml"]
    assert "<build" in message.content


def test_plain_invoke_returns_the_xml_string():
    # Realtime calls tool.invoke(args) with no tool-call id. LangChain then
    # returns the content only, which is the string the relay already expects.
    text = get_champion_build.invoke({"champion": "Aatrox", "role": "top"})
    assert isinstance(text, str)
    assert text.startswith("<build")


def test_miss_has_an_empty_artifact():
    message = _tool_call(get_champion_combos, {"champion": "not-a-champion"})
    assert isinstance(message, ToolMessage)
    assert message.artifact == []
    assert message.content.startswith("No combo data")
