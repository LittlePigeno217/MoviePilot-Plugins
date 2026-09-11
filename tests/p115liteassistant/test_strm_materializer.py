from pathlib import Path
import importlib.util
import inspect
import logging
import sys
import types

try:
    from app.plugins.p115liteassistant import strm, strm_core
except ModuleNotFoundError:
    repository = Path(__file__).resolve().parents[2]
    app = sys.modules.setdefault("app", types.ModuleType("app"))
    app.__path__ = []
    log = types.ModuleType("app.log")
    log.logger = logging.getLogger("test")
    sys.modules["app.log"] = log
    plugins = types.ModuleType("app.plugins")
    plugins.__path__ = [str(repository / "plugins")]
    sys.modules["app.plugins"] = plugins
    package = types.ModuleType("app.plugins.p115liteassistant")
    package.__path__ = [str(repository / "plugins" / "p115liteassistant")]
    sys.modules["app.plugins.p115liteassistant"] = package

    def load(name):
        path = repository / "plugins" / "p115liteassistant" / f"{name}.py"
        spec = importlib.util.spec_from_file_location(
            f"app.plugins.p115liteassistant.{name}", path
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module

    strm_core = load("strm_core")
    client = types.ModuleType("app.plugins.p115liteassistant.client")
    client.U115AccessLimitError = type("U115AccessLimitError", (Exception,), {})
    client.U115AuthError = type("U115AuthError", (Exception,), {})
    sys.modules[client.__name__] = client
    p115pickcode = types.ModuleType("p115pickcode")
    p115pickcode.is_valid_pickcode = lambda value: bool(value)
    sys.modules["p115pickcode"] = p115pickcode
    strm = load("strm")


def test_strm_reexports_authoritative_materializer():
    assert strm.StrmMaterializer is strm_core.StrmMaterializer
    assert strm.StrmOwnershipConflict is strm_core.StrmOwnershipConflict


def test_structured_materializer_has_no_legacy_surface():
    prepare = inspect.signature(strm.StrmMaterializer.prepare)
    remove = inspect.signature(strm.StrmMaterializer.remove_if_owned)

    assert prepare.parameters["request"].annotation in (
        strm.MaterializeRequest,
        "MaterializeRequest",
    )
    assert "legacy" not in prepare.parameters
    assert "allow_candidate_winner" not in inspect.signature(
        strm.StrmMaterializer.validate_collision
    ).parameters
    assert "reservation" in prepare.parameters
    assert prepare.parameters["reservation"].default is inspect.Parameter.empty
    assert not hasattr(strm.StrmMaterializer, "materialize")
    assert "args" not in remove.parameters
    assert "record_ref" in remove.parameters
    assert not hasattr(strm.StrmMaterializer, "update_record")
    assert not hasattr(strm.StrmMaterializer, "_legacy_materialize")

