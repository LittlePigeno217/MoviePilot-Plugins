from plugins.u115mediaupload import U115MediaUpload


def make_plugin():
    plugin = U115MediaUpload()
    plugin._stored = {}
    plugin.get_config = lambda: {}
    plugin.update_config = lambda config: plugin._stored.update({"config": config}) or True
    plugin.save_data = lambda key, value: plugin._stored.update({key: value})
    plugin.get_data = lambda key=None: plugin._stored.get(key) if key else plugin._stored
    return plugin


def test_plugin_saves_config_and_exposes_vue_render_mode():
    plugin = make_plugin()
    plugin.init_plugin({"enabled": True})

    result = plugin._save_config_api(
        {
            "enabled": True,
            "auth_mode": "cookie",
            "cookie": "UID=1",
            "path_mappings": [
                {"enabled": True, "source": "D:/Media", "target": "/Media"}
            ],
            "concurrency": 0,
        }
    )

    assert result["success"] is True
    assert plugin.get_render_mode() == ("vue", "dist/assets")
    assert plugin._stored["config"]["concurrency"] == 1
    assert plugin._stored["config"]["path_mappings"][0]["target"] == "/Media"


def test_plugin_status_masks_runtime_shape():
    plugin = make_plugin()
    plugin.init_plugin({"enabled": True, "cookie": "UID=1"})

    status = plugin._get_status_api()

    assert status["success"] is True
    assert status["data"]["enabled"] is True
    assert status["data"]["authorized"] is True
    assert status["data"]["phase"] == "idle"
