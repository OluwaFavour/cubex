"""
Test suite for Renderer template service.

This module contains comprehensive tests for the Jinja2 template rendering service including:
- Template environment initialization
- Async template rendering
- Context variable handling
- Error handling for missing templates

Run all tests:
    pytest app/tests/services/test_template.py -v

Run with coverage:
    pytest app/tests/services/test_template.py --cov=app.core.services.template --cov-report=term-missing -v
"""

from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from jinja2 import TemplateNotFound

from app.core.services.template import Renderer


class TestRendererInitialization:
    """Test suite for Renderer initialization."""

    def test_initialize_sets_environment(self):
        """Test that initialize creates Jinja2 environment."""
        with patch("app.core.services.template.Environment") as mock_env_class:
            mock_env_instance = MagicMock()
            mock_env_class.return_value = mock_env_instance

            Renderer.initialize(template_dir="/templates")

            mock_env_class.assert_called_once()
            assert Renderer._env == mock_env_instance

    def test_initialize_with_file_system_loader(self):
        """Test that initialize configures FileSystemLoader."""
        with patch("app.core.services.template.FileSystemLoader") as mock_loader:
            Renderer.initialize(template_dir="/path/to/templates")

            mock_loader.assert_called_once_with("/path/to/templates")

    def test_initialize_enables_autoescape(self):
        """Test that initialize enables autoescape for security."""
        with patch("app.core.services.template.Environment") as mock_env_class:
            Renderer.initialize(template_dir="/templates")

            call_kwargs = mock_env_class.call_args[1]
            assert call_kwargs["autoescape"] is True

    def test_initialize_enables_async(self):
        """Test that initialize enables async rendering."""
        with patch("app.core.services.template.Environment") as mock_env_class:
            Renderer.initialize(template_dir="/templates")

            call_kwargs = mock_env_class.call_args[1]
            assert call_kwargs["enable_async"] is True

    def test_initialize_with_different_paths(self):
        """Test initialize with various template directory paths."""
        test_paths = [
            "/templates",
            "relative/templates",
            "/var/www/templates",
            "C:\\Windows\\templates",
        ]

        for template_dir in test_paths:
            with patch("app.core.services.template.FileSystemLoader") as mock_loader:
                Renderer.initialize(template_dir=template_dir)
                mock_loader.assert_called_once_with(template_dir)


class TestRendererRenderTemplate:
    """Test suite for template rendering."""

    @pytest.mark.asyncio
    async def test_render_template_basic(self):
        """Test basic template rendering without context."""
        mock_env = MagicMock()
        mock_template = AsyncMock()
        mock_template.render_async = AsyncMock(return_value="<h1>Test</h1>")
        mock_env.get_template.return_value = mock_template

        Renderer._env = mock_env

        result = await Renderer.render_template("test.html")

        assert result == "<h1>Test</h1>"
        mock_env.get_template.assert_called_once_with("test.html")
        mock_template.render_async.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_render_template_with_context(self):
        """Test template rendering with context variables."""
        mock_env = MagicMock()
        mock_template = AsyncMock()
        mock_template.render_async = AsyncMock(return_value="<h1>Hello, John</h1>")
        mock_env.get_template.return_value = mock_template

        Renderer._env = mock_env

        context = {"name": "John", "age": 30}
        result = await Renderer.render_template("greeting.html", context)

        assert result == "<h1>Hello, John</h1>"
        mock_template.render_async.assert_called_once_with(name="John", age=30)

    @pytest.mark.asyncio
    async def test_render_template_with_empty_context(self):
        """Test template rendering with empty context dict."""
        mock_env = MagicMock()
        mock_template = AsyncMock()
        mock_template.render_async = AsyncMock(return_value="<p>Content</p>")
        mock_env.get_template.return_value = mock_template

        Renderer._env = mock_env

        result = await Renderer.render_template("template.html", context={})

        assert result == "<p>Content</p>"
        mock_template.render_async.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_render_template_with_complex_context(self):
        """Test rendering with nested context data."""
        mock_env = MagicMock()
        mock_template = AsyncMock()
        mock_template.render_async = AsyncMock(return_value="<div>Rendered</div>")
        mock_env.get_template.return_value = mock_template

        Renderer._env = mock_env

        complex_context = {
            "user": {"name": "Alice", "email": "alice@example.com"},
            "items": [1, 2, 3],
            "settings": {"theme": "dark", "notifications": True},
        }

        result = await Renderer.render_template("dashboard.html", complex_context)

        assert result == "<div>Rendered</div>"
        mock_template.render_async.assert_called_once()
        call_kwargs = mock_template.render_async.call_args[1]
        assert call_kwargs["user"] == complex_context["user"]
        assert call_kwargs["items"] == complex_context["items"]
        assert call_kwargs["settings"] == complex_context["settings"]

    @pytest.mark.asyncio
    async def test_render_template_multiple_templates(self):
        """Test rendering different templates."""
        mock_env = MagicMock()

        templates = {
            "email.html": "<p>Email content</p>",
            "invoice.html": "<table>Invoice</table>",
            "notification.html": "<span>Alert</span>",
        }

        for template_name, expected_output in templates.items():
            mock_template = AsyncMock()
            mock_template.render_async = AsyncMock(return_value=expected_output)
            mock_env.get_template.return_value = mock_template

            Renderer._env = mock_env

            result = await Renderer.render_template(template_name)
            assert result == expected_output

    @pytest.mark.asyncio
    async def test_render_template_raises_not_found(self):
        """Test that rendering nonexistent template raises TemplateNotFound."""
        mock_env = MagicMock()
        mock_env.get_template.side_effect = TemplateNotFound("missing.html")

        Renderer._env = mock_env

        with pytest.raises(TemplateNotFound):
            await Renderer.render_template("missing.html")

    @pytest.mark.asyncio
    async def test_render_template_default_context_is_empty_dict(self):
        """Test that default context is empty dict when not provided."""
        mock_env = MagicMock()
        mock_template = AsyncMock()
        mock_template.render_async = AsyncMock(return_value="content")
        mock_env.get_template.return_value = mock_template

        Renderer._env = mock_env

        # Call without context parameter
        await Renderer.render_template("test.html")

        # Should be called with no kwargs since context defaults to {}
        mock_template.render_async.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_render_template_preserves_html_entities(self):
        """Test that rendered output preserves HTML entities."""
        mock_env = MagicMock()
        mock_template = AsyncMock()
        rendered_html = "<p>&lt;script&gt;alert('xss')&lt;/script&gt;</p>"
        mock_template.render_async = AsyncMock(return_value=rendered_html)
        mock_env.get_template.return_value = mock_template

        Renderer._env = mock_env

        result = await Renderer.render_template("safe.html")

        # Verify HTML entities are preserved (autoescape in effect)
        assert "&lt;" in result
        assert "&gt;" in result

    @pytest.mark.asyncio
    async def test_render_template_with_special_characters_in_context(self):
        """Test rendering with special characters in context."""
        mock_env = MagicMock()
        mock_template = AsyncMock()
        mock_template.render_async = AsyncMock(return_value="<p>Special: &amp;</p>")
        mock_env.get_template.return_value = mock_template

        Renderer._env = mock_env

        context = {
            "special_chars": "< > & \" '",
            "unicode": "こんにちは",
            "emoji": "🎉",
        }

        result = await Renderer.render_template("special.html", context)

        assert result == "<p>Special: &amp;</p>"
        mock_template.render_async.assert_called_once()


class TestRendererIntegration:
    """Integration tests with real Jinja2 environment."""

    @pytest.mark.asyncio
    async def test_full_initialization_and_render_flow(self):
        """Test complete flow from initialization to rendering."""
        import tempfile
        import os

        # Create a temporary template directory
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a simple template file
            template_path = os.path.join(temp_dir, "test.html")
            with open(template_path, "w") as f:
                f.write("<h1>Hello, {{ name }}!</h1>")

            # Initialize renderer with temp directory
            Renderer.initialize(template_dir=temp_dir)

            # Render the template
            result = await Renderer.render_template("test.html", {"name": "World"})

            assert result == "<h1>Hello, World!</h1>"

    @pytest.mark.asyncio
    async def test_autoescape_prevents_xss(self):
        """Test that autoescape prevents XSS attacks."""
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as temp_dir:
            template_path = os.path.join(temp_dir, "xss_test.html")
            with open(template_path, "w") as f:
                f.write("<p>{{ user_input }}</p>")

            Renderer.initialize(template_dir=temp_dir)

            # Try to inject script
            malicious_input = "<script>alert('XSS')</script>"
            result = await Renderer.render_template(
                "xss_test.html", {"user_input": malicious_input}
            )

            # Should be escaped
            assert "&lt;script&gt;" in result
            assert "<script>" not in result

    @pytest.mark.asyncio
    async def test_render_with_loops_and_conditionals(self):
        """Test rendering template with Jinja2 control structures."""
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as temp_dir:
            template_path = os.path.join(temp_dir, "loop.html")
            with open(template_path, "w") as f:
                f.write("{% for item in items %}<li>{{ item }}</li>{% endfor %}")

            Renderer.initialize(template_dir=temp_dir)

            result = await Renderer.render_template(
                "loop.html", {"items": ["a", "b", "c"]}
            )

            assert result == "<li>a</li><li>b</li><li>c</li>"
