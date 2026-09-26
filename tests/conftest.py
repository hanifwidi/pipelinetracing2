import copy
import pytest
from config import cfg

@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    original = copy.deepcopy(cfg.__dict__)
    for name, value in original.items():
        if name.endswith('_FOLDER') or name.endswith('_DIR'):
            monkeypatch.setattr(cfg, name, tmp_path / value.name)
    for key in ('GEMINI_API_KEY','OPENROUTER_API_KEY','GROQ_API_KEY','MISTRAL_API_KEY',
                'GEMINI_MODEL','GEMINI_FALLBACK_MODELS','OPENROUTER_MODEL'):
        monkeypatch.delenv(key, raising=False)
    import utils.metadata_ai as metadata
    for state in (metadata._next_request, metadata._cooldowns, metadata._disabled, metadata._provider_locks):
        state.clear()
    metadata._openrouter_models.cache_clear()
    yield
    cfg.__dict__.clear()
    cfg.__dict__.update(original)
