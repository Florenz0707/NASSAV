"""Legacy FlareSolverr compatibility entry point, with no external requests."""

from unittest.mock import MagicMock, patch

from nassav.flaresolverr_client import FlareSolverrClient


def test_legacy_client_does_not_send_target_proxy_to_control_api():
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "status": "ok",
        "solution": {
            "status": 200,
            "url": "https://example.com/",
            "response": "<html>ok</html>",
        },
    }
    client = FlareSolverrClient("http://localhost:8191", proxy="http://127.0.0.1:7077")
    with patch.object(client._client._session, "post", return_value=response) as post:
        result = client.get("https://example.com/")
    assert result["response"] == "<html>ok</html>"
    assert "proxy" not in post.call_args.kwargs["json"]
