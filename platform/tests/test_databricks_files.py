import io
import unittest
from urllib.error import HTTPError

from social_intelligence.connectors.databricks_files import DatabricksFilesClient


class FakeResponse:
    def __init__(self, content=b""):
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return self.content


class DatabricksFilesClientTests(unittest.TestCase):
    def test_download_uses_encoded_volume_path_and_bearer_auth(self):
        requests = []

        def opener(request, timeout):
            requests.append((request, timeout))
            return FakeResponse(b'{"ok": true}')

        client = DatabricksFilesClient(
            "https://dbc.example.com/",
            "secret-token",
            opener=opener,
        )
        payload = client.download(
            "/Volumes/dev/social_intelligence_dev/raw_social/a file.json"
        )

        self.assertEqual(payload, b'{"ok": true}')
        request, timeout = requests[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertIn("a%20file.json", request.full_url)
        self.assertEqual(request.get_header("Authorization"), "Bearer secret-token")
        self.assertEqual(timeout, 30)

    def test_upload_overwrites_binary_content(self):
        requests = []

        def opener(request, timeout):
            requests.append(request)
            return FakeResponse()

        client = DatabricksFilesClient(
            "https://dbc.example.com",
            "secret-token",
            opener=opener,
        )
        client.upload("/Volumes/dev/schema/volume/events/batch.json", b"payload")

        request = requests[0]
        self.assertEqual(request.get_method(), "PUT")
        self.assertTrue(request.full_url.endswith("?overwrite=true"))
        self.assertEqual(request.data, b"payload")

    def test_missing_download_returns_none(self):
        def opener(request, timeout):
            raise HTTPError(request.full_url, 404, "missing", {}, io.BytesIO())

        client = DatabricksFilesClient(
            "https://dbc.example.com",
            "secret-token",
            opener=opener,
        )
        self.assertIsNone(client.download("/Volumes/dev/schema/volume/missing.json"))

    def test_rejects_non_volume_and_parent_paths(self):
        client = DatabricksFilesClient(
            "https://dbc.example.com",
            "secret-token",
            opener=lambda *_args, **_kwargs: FakeResponse(),
        )
        with self.assertRaises(ValueError):
            client.download("/Workspace/file.json")
        with self.assertRaises(ValueError):
            client.download("/Volumes/dev/schema/volume/../secret.json")


if __name__ == "__main__":
    unittest.main()
