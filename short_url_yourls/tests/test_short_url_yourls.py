# Copyright 2022 Yiğit Budak (https://github.com/yibudak)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from unittest.mock import Mock, patch

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestShortURLYourls(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, lang="en_US"))

    def test_create_with_valid_http_url(self):
        """Test creating shortener with valid HTTP URL"""
        shortener = self.env["short.url.yourls"].create(
            {
                "hostname": "http://example.com",
                "username": "testuser",
                "password": "testpass",
            }
        )
        self.assertEqual(shortener.hostname, "http://example.com")
        self.assertEqual(shortener.name, "example.com")

    def test_create_with_invalid_url_raises_error(self):
        """Test that invalid URL raises ValidationError"""
        with self.assertRaises(ValidationError) as cm:
            self.env["short.url.yourls"].create(
                {
                    "hostname": "not-a-valid-url",
                    "username": "testuser",
                    "password": "testpass",
                }
            )
        self.assertIn("Hostname must be a valid URL", str(cm.exception))

    def test_create_auto_generates_name_from_hostname(self):
        """Test that name is auto-generated from hostname if not provided"""
        shortener = self.env["short.url.yourls"].create(
            {
                "hostname": "https://my-shortener.com",
                "username": "testuser",
                "password": "testpass",
            }
        )
        self.assertEqual(shortener.name, "my-shortener.com")

    def test_compute_total_shortened_urls_with_lines(self):
        """Test compute function with shortened URLs"""
        shortener = self.env["short.url.yourls"].create(
            {
                "hostname": "https://example.com",
                "username": "testuser",
                "password": "testpass",
            }
        )
        # Create some shortened URL lines
        self.env["short.url.yourls.line"].create(
            {
                "short_url": "https://example.com/abc",
                "long_url": "https://very-long-url.com/path/to/page",
                "shorter_id": shortener.id,
            }
        )
        self.env["short.url.yourls.line"].create(
            {
                "short_url": "https://example.com/def",
                "long_url": "https://another-long-url.com/page",
                "shorter_id": shortener.id,
            }
        )
        shortener._compute_total_shortened_urls()
        self.assertEqual(shortener.total_shortened_urls, 2)

    @patch("requests.get")
    def test_shorten_url_success(self, mock_get):
        """Test successful URL shortening"""
        shortener = self.env["short.url.yourls"].create(
            {
                "hostname": "https://example.com",
                "username": "testuser",
                "password": "testpass",
            }
        )

        # Mock successful API response
        mock_response = Mock()
        mock_response.json.return_value = {
            "status": "success",
            "shorturl": "https://example.com/abc123",
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = shortener.shorten_url("https://very-long-url.com/path/to/page")

        self.assertEqual(result, "https://example.com/abc123")
        # Verify the line was created
        line = self.env["short.url.yourls.line"].search(
            [("short_url", "=", "https://example.com/abc123")]
        )
        self.assertEqual(len(line), 1)
        self.assertEqual(line.long_url, "https://very-long-url.com/path/to/page")

    @patch("requests.get")
    def test_shorten_url_returns_existing_if_already_shortened(self, mock_get):
        """Test that already shortened URL is returned without API call"""
        shortener = self.env["short.url.yourls"].create(
            {
                "hostname": "https://example.com",
                "username": "testuser",
                "password": "testpass",
            }
        )

        # Create existing shortened URL
        self.env["short.url.yourls.line"].create(
            {
                "short_url": "https://example.com/existing",
                "long_url": "https://test-url.com/page",
                "shorter_id": shortener.id,
            }
        )

        result = shortener.shorten_url("https://test-url.com/page")

        # Should return existing short URL without making API call
        self.assertEqual(result, "https://example.com/existing")
        mock_get.assert_not_called()

    @patch("requests.get")
    def test_shorten_url_failure_returns_false(self, mock_get):
        """Test that failed URL shortening returns False"""
        shortener = self.env["short.url.yourls"].create(
            {
                "hostname": "https://example.com",
                "username": "testuser",
                "password": "testpass",
            }
        )

        # Mock failed API response
        mock_response = Mock()
        mock_response.json.return_value = {
            "status": "fail",
            "message": "Invalid credentials",
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = shortener.shorten_url("https://very-long-url.com/path/to/page")

        self.assertFalse(result)
