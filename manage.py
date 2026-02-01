import asyncio
import json
import os
from pathlib import Path
import subprocess
from typing import Annotated

# from email_validator import validate_email, EmailNotValidError
from pydantic import validate_email
from rich import print

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine
import typer

from app.shared.config import settings

app = typer.Typer()


async def clear_alembic_task():
    """
    Asynchronously clears the Alembic version history from the database.
    This function connects to the database specified by the `DATABASE_URL` environment variable
    and deletes all rows from the `alembic_version` table, effectively resetting Alembic's migration history.
    It provides colored console output to indicate the operation's status and handles errors gracefully,
    including missing environment variables, missing tables, and SQL execution errors.
    Raises:
        typer.Exit: If the `DATABASE_URL` environment variable is not set or if an error occurs during execution.
    """
    print("[yellow]Clearing Alembic version history[/yellow]")
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("[red]Error: DATABASE_URL environment variable is not set[/red]")
        # This is a hard configuration error – fail fast so it can be fixed.
        raise typer.Exit(1)

    engine = create_async_engine(database_url, echo=False)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(text("DELETE FROM alembic_version"))
            await connection.commit()  # Ensure the deletion is committed
            if result.rowcount > 0:
                print(
                    f"[green]Alembic version history cleared ({result.rowcount} rows)[/green]"
                )
            else:
                print("[cyan]Alembic version history is already empty[/cyan]")
    except SQLAlchemyError as e:
        # Make this operation idempotent: log the problem but do not fail the workflow.
        print(f"[red]Error clearing Alembic version history:[/red] {str(e)}")
        if "alembic_version" in str(e):
            print("[cyan]alembic_version table does not exist; skipping clear[/cyan]")
        else:
            print(
                "[yellow]Skipping Alembic clear; leaving migration history unchanged[/yellow]"
            )
    except Exception as e:
        # Any unexpected error should be visible but not break CI.
        print(f"[red]Unexpected error while clearing Alembic history:[/red] {str(e)}")
        print(
            "[yellow]Skipping Alembic clear; leaving migration history unchanged[/yellow]"
        )
    finally:
        await engine.dispose()  # Clean up the engine


async def create_extensions_task(extensions: list[str]) -> None:
    """Ensure that the given PostgreSQL extensions exist.

    This connects to the database specified by ``DATABASE_URL`` and runs
    ``CREATE EXTENSION IF NOT EXISTS <ext>;`` for each provided extension
    name. The operation is idempotent and safe to call in CI.

    Args:
        extensions: A list of extension names to ensure (e.g. ["citext"]).
    """

    if not extensions:
        print("[cyan]No extensions specified; skipping extension creation[/cyan]")
        return

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("[red]Error: DATABASE_URL environment variable is not set[/red]")
        # Hard config error: fail so CI/config can be fixed.
        raise typer.Exit(1)

    engine = create_async_engine(database_url, echo=False)
    try:
        async with engine.begin() as connection:
            for ext in extensions:
                ext_name = ext.strip()
                if not ext_name:
                    continue
                print(
                    f"[yellow]Ensuring PostgreSQL extension exists:[/yellow] {ext_name}"
                )
                # Use IF NOT EXISTS to make this idempotent across environments.
                await connection.execute(
                    text(f'CREATE EXTENSION IF NOT EXISTS "{ext_name}";')
                )
        print("[green]PostgreSQL extensions ensured successfully[/green]")
    except SQLAlchemyError as e:
        print(f"[red]Error ensuring PostgreSQL extensions:[/red] {str(e)}")
        raise
    except Exception as e:
        print(f"[red]Unexpected error ensuring PostgreSQL extensions:[/red] {str(e)}")
        raise
    finally:
        await engine.dispose()


# async def create_superuser_task(email: str, password: str):
#     async with AsyncSessionLocal() as session:
#         async with session.begin():
#             # Check if user exists already
#             if existing_user := await user_db.get_one_by_conditions(
#                 session,
#                 [user_db.model.email == email],
#             ):
#                 if existing_user.role == UserRole.ADMIN:
#                     print(f"[yellow]Superuser already exists:[/yellow] {email}")
#                     return
#                 else:
#                     # Prompt for user upgrade confirmation
#                     if typer.confirm(
#                         f"[yellow]User exists but is not a superuser. Upgrade to superuser:[/yellow] {existing_user.full_name}"
#                     ):
#                         existing_user.role = UserRole.ADMIN
#                         await session.flush()
#                         await session.refresh(existing_user)
#                         print(
#                             f"[green]User upgraded to superuser:[/green] {existing_user.full_name}"
#                         )
#                         return
#             user = await user_db.create_superuser(
#                 session, email, password, commit_self=False
#             )
#             print(f"[green]Superuser created:[/green] {user.email}")


def email_validator(email: str) -> str:
    _, email = validate_email(email)
    return email


# @app.command()
# def createsuperuser(
#     email: Annotated[
#         str, typer.Option(prompt=True, prompt_required=False, callback=email_validator)
#     ],
#     password: Annotated[
#         str, typer.Option(prompt=True, hide_input=True, confirmation_prompt=True)
#     ],
# ):
#     """
#     Creates a new superuser with the given email and password.

#     Args:
#         email (str): The email address of the superuser.
#         password (str): The plaintext password for the superuser.
#     """
#     asyncio.run(create_superuser_task(email.lower(), password))


@app.command()
def clearalembic():
    """
    Clears Alembic migration history by running the asynchronous clear_alembic_task function.

    This function serves as a synchronous entry point to execute the asynchronous
    clear_alembic_task coroutine, which is responsible for removing or resetting
    Alembic migration data.

    Usage:
        clearalembic()
    """
    asyncio.run(clear_alembic_task())


@app.command()
def createextensions(
    extensions: Annotated[
        list[str] | None,
        typer.Argument(
            help=(
                "PostgreSQL extensions to ensure exist, e.g. "
                "'citext pgcrypto'. If omitted, nothing is done."
            ),
        ),
    ] = None,
):
    """Ensure one or more PostgreSQL extensions exist.

    Examples:
        python manage.py createextensions citext
        python manage.py createextensions citext pgcrypto
    """

    if not extensions:
        print("[cyan]No extensions specified; skipping extension creation[/cyan]")
        return

    asyncio.run(create_extensions_task(list(extensions)))


@app.command()
def makemigrations(comment: Annotated[str, typer.Argument()] = "auto"):
    """
    Creates a new Alembic migration revision with an autogenerated migration script.

    Args:
        comment (str, optional): The message to use for the migration revision. Defaults to "auto".

    Raises:
        subprocess.CalledProcessError: If the Alembic command fails.

    Side Effects:
        Executes the Alembic CLI to generate a new migration file.
        Prints status messages to the console.
    """
    try:
        revision_command = f"alembic revision --autogenerate -m {comment}"
        print(f"Running Alembic migrations: {revision_command}")
        subprocess.run(revision_command, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"[red]Error:[/red] {e}")
        raise
    print("[green]Make migrations complete[/green]")


@app.command()
def startngrok():
    """
    Starts an ngrok tunnel to expose the local FastAPI server to the internet.

    This function runs the ngrok command to create a secure tunnel to the local server
    running on port 8000. It provides console output to indicate the operation's status
    and handles errors gracefully.

    Raises:
        subprocess.CalledProcessError: If the ngrok command fails.
    """
    try:
        ngrok_command = "ngrok http --url=assured-elf-friendly.ngrok-free.app 8000"
        print(f"Starting ngrok tunnel: {ngrok_command}")
        subprocess.run(ngrok_command, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"[red]Error:[/red] {e}")
        raise


@app.command()
def migrate():
    """
    Runs the Alembic database migration to upgrade the schema to the latest version.

    This function executes the "alembic upgrade head" command using a subprocess.
    If the migration fails, it prints an error message; otherwise, it confirms successful migration.
    """
    try:
        upgrade_command = "alembic upgrade head"
        print(f"Running Alembic upgrade: {upgrade_command}")
        subprocess.run(upgrade_command, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"[red]Error:[/red] {e}")
        raise
    print("[green]Migration complete[/green]")


@app.command()
def runserver():
    try:
        server_command = (
            "uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"
            if settings.DEBUG
            else "uvicorn app.main:app --host 0.0.0.0 --port 8000"
        )
        print(f"Running FastAPI server: {server_command}")
        subprocess.run(server_command, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"[red]Error:[/red] {e}")
        raise


@app.command()
def runbroker():
    """
    Run the FastAPI broker
    """
    try:
        broker_command = "docker run -it --rm --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:4-management"
        print(f"Running FastAPI broker: {broker_command}")
        subprocess.run(broker_command, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"[red]Error:[/red] {e}")
        raise


@app.command()
def generateopenapi():
    """
    Generates the OpenAPI schema for the FastAPI application and saves it to a JSON file.

    This function initializes the FastAPI application, retrieves the OpenAPI schema,
    and writes it to the file specified by the OPENAPI_JSON_PATH setting.
    It provides console output to indicate the progress and completion of the operation.
    """
    from app.main import app

    openapi_path = Path("openapi.json")
    with openapi_path.open("w", encoding="utf-8") as f:
        json.dump(app.openapi(), f, ensure_ascii=False, indent=2)
    print(f"[green]OpenAPI schema generated at {openapi_path.name}[/green]")


@app.callback()
def main(ctx: typer.Context):
    print(f"Executing the command: {ctx.invoked_subcommand}")


if __name__ == "__main__":
    app()
