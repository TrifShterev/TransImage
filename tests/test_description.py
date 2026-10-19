from types import SimpleNamespace

from PIL import Image

from transimage.description import (
    DEFAULT_LANGUAGE,
    LANGUAGES,
    build_description_prompt,
    describe_image,
)


def test_languages_offer_en_fi_bg_with_en_default() -> None:
    assert list(LANGUAGES) == ["EN", "FI", "BG"]
    assert DEFAULT_LANGUAGE == "EN"


def test_build_prompt_appends_language_instruction() -> None:
    base = "Describe this image."
    assert build_description_prompt(base, "EN").startswith(base)
    assert "in English" in build_description_prompt(base, "EN")
    assert "in Finnish" in build_description_prompt(base, "FI")
    assert "in Bulgarian" in build_description_prompt(base, "BG")


def test_build_prompt_unknown_language_falls_back_to_english() -> None:
    assert "in English" in build_description_prompt("Describe.", "XX")


def test_describe_image_sends_prompt(monkeypatch) -> None:
    captured = {}

    class _FakeChat:
        def send(self, **kwargs):
            captured.update(kwargs)
            message = SimpleNamespace(content="a red square")
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    class _FakeClient:
        def __init__(self, **kwargs):
            self.chat = _FakeChat()

    monkeypatch.setattr("transimage.description.OpenRouter", _FakeClient)
    prompt = build_description_prompt("Describe.", "FI")
    result = describe_image(
        Image.new("RGB", (8, 8), "red"), "key", prompt, model="m"
    )

    assert result == "a red square"
    content = captured["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": prompt}
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
