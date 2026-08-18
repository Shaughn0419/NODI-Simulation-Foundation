import nodi_foundation
from nodi_foundation import __version__, api


def test_package_version() -> None:
    assert __version__ == "5.0.0"


def test_package_root_is_a_thin_canonical_api_reexport() -> None:
    assert nodi_foundation.__all__ is api.__all__
    assert len(api.__all__) == len(set(api.__all__))
    for name in api.__all__:
        assert getattr(nodi_foundation, name) is getattr(api, name)
