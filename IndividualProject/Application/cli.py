from pathlib import Path
import pandas as pd

from Application import ERRORS, __app_name__, __version__



    """Input handling logic for selecting simulation
    match sim_select_1:
        case "Exit":
            typer.secho(
                f'Exiting application.',
                fg=typer.colors.GREEN
            )
            raise typer.Exit(1)
        case "1-10: historical":
            sim_select_2: str = typer.Option(
                "Exit",
                "1", "2", "3", "4", "5", "6", "7", "8", "9", "10",
                prompt="Choose scenario.",
            )
        case "1-16: simulated":
            sim_select_2: str = typer.Option(
                "Exit",
                "11", "12", "13", "14", "15", "16",
                prompt="Choose scenario.",
            )
        case _:
            typer.secho(
                f'Something went catastrophically wrong, exiting application.',
                fg=typer.colors.RED
            )
            raise typer.Exit(1)

    # Initialise config file
    ''' app_init_error = config.init_app(db_path)
    if app_init_error:
        typer.secho(
            f'Creating config file failed with "{ERRORS[app_init_error]}"',
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)

    # Import database data into frames




    db_init_error = database.init_database(Path(db_path))
    if db_init_error:
        typer.secho(
            f'Creating database failed with "{ERRORS[db_init_error]}"',
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)
    else:
        typer.secho(f"The to-do database is {db_path}", fg=typer.colors.GREEN)'''

# Version callback to cleanly exit application
def _version_callback(value: bool):
    if value:
        typer.echo(f"{__app_name__} v{__version__}")
        raise typer.Exit()

# Main function
def main(
        version: Optional[bool] = typer.Option(
            None,
            "--version",
            help="Show application version and exit.",
            callback=_version_callback,
            is_eager=True,
        )
)"""