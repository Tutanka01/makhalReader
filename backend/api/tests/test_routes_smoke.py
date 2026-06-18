def test_app_exposes_briefing_routes():
    import main
    paths = {r.path for r in main.app.routes}
    assert "/api/briefings/latest" in paths
    assert "/api/briefings/generate" in paths
