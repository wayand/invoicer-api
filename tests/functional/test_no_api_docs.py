"""
The API publishes no interactive docs or machine-readable spec: they listed
every route to anyone who asked, and documented only one of them.
"""

import pytest

DOC_PATHS = [
    "/apidocs",
    "/apidocs/",
    "/apidocs/index.html",
    "/apispec_1.json",
    "/flasgger_static/swagger-ui.css",
    "/swagger.json",
    "/docs",
]


@pytest.mark.parametrize("path", DOC_PATHS)
def test_api_docs_are_not_served(client, path):
    assert client.get(path).status_code == 404


def test_no_route_serves_docs(app):
    paths = {rule.rule for rule in app.url_map.iter_rules()}

    assert not {p for p in paths if "apidocs" in p or "flasgger" in p}
