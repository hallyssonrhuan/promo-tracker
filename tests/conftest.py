"""Fixtures pra testes — Store em memoria via tmp_path.

A fixture `store` substitui o `session` do mundo SQLModel: cada teste recebe
um Store novo apontando pra um arquivo temporario, isolado e descartavel.
"""

import pytest

from app.store import Store


@pytest.fixture
def store(tmp_path):
    """Store apontado pra um state.json temporario (limpa entre tests)."""
    return Store(tmp_path / "state.json")
