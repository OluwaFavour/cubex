from jinja2 import Environment, FileSystemLoader


class Renderer:
    _env: Environment | None = None

    @classmethod
    def initialize(cls, template_dir: str) -> None:
        """
        Initializes the template environment for rendering templates.

        This method sets up a Jinja2 environment with the specified template directory,
        enabling asynchronous template rendering and automatic escaping for security.

        Args:
            template_dir (str): The directory containing the template files.
        """
        cls._env = Environment(
            loader=FileSystemLoader(template_dir), autoescape=True, enable_async=True
        )

    @classmethod
    async def render_template(cls, template_name: str, context: dict = {}) -> str:
        """
        Renders an asynchronous template with the given context.

        Args:
            template_name (str): The name of the template to be rendered.
            context (dict): A dictionary containing the context data to be passed to the template.

        Returns:
            str: The rendered template as a string.

        Raises:
            TemplateNotFound: If the specified template cannot be found.
            TemplateError: If an error occurs during template rendering.
            RuntimeError: If the renderer has not been initialized.
        """
        if cls._env is None:
            raise RuntimeError("Renderer not initialized. Call initialize() first.")
        template = cls._env.get_template(template_name)
        return await template.render_async(**context)
