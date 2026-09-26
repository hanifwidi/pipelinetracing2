import copy
import pytest
from config import cfg

@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    original = copy.deepcopy(cfg.__dict__)
    for name, value in original.items():
        if name.endswith('_FOLDER') or name.endswith('_DIR'):
            monkeypatch.setattr(cfg, name, tmp_path / value.name)
    for key in ('GEMINI_API_KEY','OPENROUTER_API_KEY','GROQ_API_KEY','MISTRAL_API_KEY'):
        monkeypatch.delenv(key, raising=False)
    yield
    cfg.__dict__.clear()
    cfg.__dict__.update(original)
