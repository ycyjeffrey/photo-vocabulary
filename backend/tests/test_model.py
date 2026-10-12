import json

import httpx
import pytest

from backend import model
from backend.schemas import Card


@pytest.mark.parametrize("response,valid", [
    ({"cards": [{"id": "c1", "definition": "資源"}]}, True),
    ({"cards": [{"id": "c1", "definition": "资源"}]}, True),
    ({"cards": []}, False),
    ({"cards": [{"id": "wrong", "definition": "資源"}]}, False),
    ({"cards": [{"id": "c1", "definition": "resources"}]}, False),
    ({"cards": [{"id": "c1", "definition": "資源"}, {"id": "c1", "definition": "來源"}]}, False),
    ({"cards": [{"id": "c1", "definition": "資源", "unexpected": "field"}]}, False),
])
def test_local_model_schema_and_provenance(monkeypatch, response, valid):
    monkeypatch.setenv("OLLAMA_MODEL", "test-model")
    monkeypatch.setenv("OLLAMA_URL", "http://127.0.0.1:11434")
    real_client = httpx.Client
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json={"response": json.dumps(response)})

    monkeypatch.setattr(model.httpx, "Client",
                        lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs))
    cards = [Card(id="one", term="resource", definition="", part_of_speech="n.", confirmed=True)]
    if valid:
        result = model.enrich(cards)
        assert result[0].definition == "資源"
        assert result[0].id == "one"
        assert result[0].definitionOrigin == "model"
        assert result[0].part_of_speech == "n." and result[0].partOfSpeechOrigin == "photo"
        assert result[0].needs_review and not result[0].selected and not result[0].confirmed
        assert "multiple meanings" in result[0].review_reason
        assert cards[0].definition == ""
    else:
        with pytest.raises(ValueError):
            model.enrich(cards)
    assert len(requests) == 1
    request = requests[0]
    assert request.url.host == "127.0.0.1"
    payload = json.loads(request.content)
    assert payload["model"] == "test-model" and payload["stream"] is False
    assert payload["think"] is False
    assert payload["format"]["$defs"]["EnrichedFields"]["properties"]["id"]["enum"] == ["c1"]
    assert payload["format"]["properties"]["cards"]["minItems"] == 1
    assert payload["format"]["properties"]["cards"]["maxItems"] == 1
    variant = payload["format"]["properties"]["cards"]["items"]["anyOf"][0]
    assert variant["properties"]["id"]["const"] == "c1"
    assert variant["properties"]["definition"]["minLength"] == 1
    assert variant["properties"]["part_of_speech"]["const"] == ""
    assert set(variant["required"]) == {"id", "definition", "part_of_speech"}
    assert "untrusted data" in payload["prompt"]


def test_generated_definitions_use_traditional_chinese(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:4b")
    real_client = httpx.Client

    def handle(request):
        return httpx.Response(200, json={
            "response": json.dumps({"cards": [{"id": "c1", "definition": "栖息地"}]}),
        })

    monkeypatch.setattr(model.httpx, "Client",
                        lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs))
    original = Card(id="habitat", term="habitat", part_of_speech="n.", confirmed=True)
    result = model.enrich([original])
    assert result[0].definition == "棲息地"
    assert result[0].definitionOrigin == "model"
    assert original.definition == ""


@pytest.mark.parametrize("definition,pos,expected_definition,expected_pos,definition_origin,pos_origin", [
    ("資源（手動校正）", "", "資源（手動校正）", "n.", "manual", "model"),
    ("", "adj.", "資源", "adj.", "model", "manual"),
    ("", "", "資源", "n.", "model", "model"),
])
def test_fill_missing_fields_only(monkeypatch, definition, pos, expected_definition, expected_pos,
                                  definition_origin, pos_origin):
    monkeypatch.setenv("OLLAMA_MODEL", "test-model")
    real_client = httpx.Client
    inputs = []

    def handle(request):
        payload = json.loads(request.content)
        inputs.append(json.loads(payload["prompt"].split("Data:\n")[1])[0])
        variant = payload["format"]["properties"]["cards"]["items"]["anyOf"][0]
        if not pos:
            assert "" not in variant["properties"]["part_of_speech"]["enum"]
        if definition:
            assert variant["properties"]["definition"]["const"] == ""
        # Even if the model returns both fields, existing content must be untouched.
        return httpx.Response(200, json={"response": json.dumps({
            "cards": [{"id": "c1", "definition": "资源", "part_of_speech": "n."}],
        })})

    monkeypatch.setattr(model.httpx, "Client",
                        lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs))
    original = Card(id="one", term="resource", definition=definition, part_of_speech=pos,
                    definitionOrigin="manual", partOfSpeechOrigin="manual", confirmed=True)
    result = model.enrich([original])[0]
    assert (result.definition, result.part_of_speech) == (expected_definition, expected_pos)
    assert (result.definitionOrigin, result.partOfSpeechOrigin) == (definition_origin, pos_origin)
    assert (original.definition, original.part_of_speech) == (definition, pos)
    assert result.needs_review and not result.selected and not result.confirmed
    assert inputs[0]["fields_to_fill"] == model.missing_fields(original)
    assert inputs[0]["id"] == "c1" and result.id == "one"
    assert inputs[0]["definition"] == definition and inputs[0]["part_of_speech"] == pos


@pytest.mark.parametrize("generated_pos", ["", "noun", "made-up."])
def test_reject_missing_or_invalid_generated_pos(monkeypatch, generated_pos):
    monkeypatch.setenv("OLLAMA_MODEL", "test-model")
    real_client = httpx.Client

    def handle(request):
        return httpx.Response(200, json={"response": json.dumps({
            "cards": [{"id": "c1", "part_of_speech": generated_pos}],
        })})

    monkeypatch.setattr(model.httpx, "Client",
                        lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs))
    with pytest.raises(ValueError):
        model.enrich([Card(id="one", term="resource", definition="資源", confirmed=True)])


def test_requested_fields_cannot_overwrite_content(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "test-model")
    card = Card(id="one", term="resource", definition="資源", part_of_speech="n.", confirmed=True)
    assert model.missing_fields(card) == []
    with pytest.raises(ValueError, match="No missing fields"):
        model.enrich([card])
    with pytest.raises(ValueError, match="Only empty fields"):
        model.enrich([card], {"one": ["part_of_speech"]})
