import pytest

from mbft_api.main import app
from mbft_api.rate_limit import get_limitador


def pytest_configure(config):
    config.addinivalue_line("markers", "limite_real: mantém o rate limit real (PMS-011) no teste")


@pytest.fixture(autouse=True)
def _desligar_limitador(request):
    """Nos testes antigos o limitador é desligado (override devolve None => routers ignoram)."""
    if request.node.get_closest_marker("limite_real"):
        yield
        return
    app.dependency_overrides[get_limitador] = lambda: None
    yield
    app.dependency_overrides.pop(get_limitador, None)
