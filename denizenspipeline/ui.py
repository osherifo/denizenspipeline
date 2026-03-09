"""Rich-based terminal UI for pipeline output."""

from __future__ import annotations

import contextlib
import time

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn


console = Console()


@contextlib.contextmanager
def model_live():
    """Context manager that frames live model output between separator lines.

    Suppresses sklearn FutureWarnings while letting solver progress
    render live to the terminal.
    """
    import warnings
    console.print("       [bright_blue]───── model fitting ─────[/]", highlight=False)
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=FutureWarning)
        yield
    console.print("       [bright_blue]────────────────────────[/]", highlight=False)

# Color scheme
STAGE_COLORS = {
    'stimuli': 'bright_cyan',
    'responses': 'bright_magenta',
    'features': 'bright_yellow',
    'preprocess': 'bright_green',
    'model': 'bright_blue',
    'analyze': 'bright_red',
    'report': 'bright_white',
}


def header(experiment: str, subject: str, config: dict | None = None):
    """Print a styled pipeline header panel."""
    lines = [
        f"[bold]Experiment:[/bold] {experiment}",
        f"[bold]Subject:[/bold]    {subject}",
    ]
    if config:
        features = config.get('features', [])
        if features:
            names = ", ".join(f['name'] for f in features)
            lines.append(f"[bold]Features:[/bold]   {names}")
        model = config.get('model', {}).get('type', 'bootstrap_ridge')
        lines.append(f"[bold]Model:[/bold]      {model}")

    content = "\n".join(lines)
    console.print(Panel(
        content,
        title="[bold bright_cyan]DENIZENS PIPELINE[/]",
        border_style="bright_cyan",
        padding=(0, 2),
    ))


def stage_start(name: str) -> float:
    """Record stage start time."""
    return time.time()


def stage_done(name: str, t0: float, detail: str = ""):
    """Print stage completed line."""
    elapsed = time.time() - t0
    color = STAGE_COLORS.get(name, 'white')
    detail_str = f"  [dim]{detail}[/]" if detail else ""
    console.print(
        f"  [bold green]ok[/]  [{color}]{name:<12}[/]{detail_str}"
        f"  [dim]{elapsed:.1f}s[/]",
        highlight=False,
    )


def stage_fail(name: str, t0: float, error: str = ""):
    """Print stage failure line."""
    elapsed = time.time() - t0
    color = STAGE_COLORS.get(name, 'white')
    err_str = f"  [red]{error}[/]" if error else ""
    console.print(
        f"  [bold red]!![/]  [{color}]{name:<12}[/]{err_str}"
        f"  [dim]{elapsed:.1f}s[/]",
        highlight=False,
    )


def stage_warn(name: str, t0: float, detail: str = ""):
    """Print stage partial-success line (some reporters ok, some failed)."""
    elapsed = time.time() - t0
    color = STAGE_COLORS.get(name, 'white')
    detail_str = f"  [yellow]{detail}[/]" if detail else ""
    console.print(
        f"  [bold yellow]!![/]  [{color}]{name:<12}[/]{detail_str}"
        f"  [dim]{elapsed:.1f}s[/]",
        highlight=False,
    )


def log_hint(log_path: str):
    """Print a hint pointing to the log file."""
    console.print(f"\n  [dim]Details:[/] [bold]{log_path}[/]\n")


def data_warning(msg: str):
    """Print a colored data quality warning on the console."""
    console.print(f"       [bold yellow]⚠[/]  [yellow]{msg}[/]", highlight=False)


def trim_table(target: str, trim_start: int, trim_end: int,
               run_shapes: list[tuple[str, int, int]]):
    """Print a compact trim summary table.

    *run_shapes*: list of (run_name, before_trs, after_trs)
    """
    color = "bright_green"
    console.print(
        f"       [bold {color}]trim {target}[/]  "
        f"[dim]start=[/]{trim_start}  [dim]end=[/]{trim_end}",
        highlight=False,
    )
    for run, before, after in run_shapes:
        console.print(
            f"         [dim]{run:<30}[/]  {before} [dim]->[/] {after}",
            highlight=False,
        )


def feature_info(name: str, source: str, n_runs: int = 0, n_dims: int = 0):
    """Print feature loading detail."""
    parts = [f"[dim]source=[/]{source}"]
    if n_runs:
        parts.append(f"[dim]runs=[/]{n_runs}")
    if n_dims:
        parts.append(f"[dim]dims=[/]{n_dims}")
    detail = "  ".join(parts)
    console.print(f"       [bright_yellow]{name}[/]  {detail}", highlight=False)


def results_panel(mean_score: float, max_score: float, n_voxels: int,
                  extra: dict | None = None):
    """Print results summary in a styled panel."""
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("key", style="bold")
    table.add_column("value", style="bright_green")
    table.add_row("Mean corr", f"{mean_score:.4f}")
    table.add_row("Max corr", f"{max_score:.4f}")
    table.add_row("N voxels", str(n_voxels))
    if extra:
        for k, v in extra.items():
            table.add_row(k, str(v))

    console.print(Panel(
        table,
        title="[bold bright_green]Results[/]",
        border_style="bright_green",
        padding=(0, 1),
    ))


def artifacts_panel(artifacts: dict):
    """Print saved artifacts."""
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("reporter", style="bold cyan")
    table.add_column("file", style="dim")
    for reporter, files in artifacts.items():
        for name, path in files.items():
            table.add_row(f"[{reporter}]", str(path))

    console.print(Panel(
        table,
        title="[bold]Artifacts[/]",
        border_style="dim",
        padding=(0, 1),
    ))


def error_panel(message: str, stage: str | None = None):
    """Print error in a red panel."""
    title = f"[bold red]Error in {stage}[/]" if stage else "[bold red]Error[/]"
    console.print(Panel(
        f"[red]{message}[/]",
        title=title,
        border_style="red",
        padding=(0, 2),
    ))


def config_error(errors: list[str]):
    """Print config validation errors."""
    lines = "\n".join(f"[red]  - {e}[/]" for e in errors)
    console.print(Panel(
        lines,
        title="[bold red]Config Errors[/]",
        border_style="red",
        padding=(0, 1),
    ))


def success(message: str):
    """Print a success message."""
    console.print(f"\n[bold green]{message}[/]")


def dry_run_panel(config: dict, stages: list[str] | None = None):
    """Print dry-run summary."""
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("key", style="bold")
    table.add_column("value")

    table.add_row("Experiment", config.get('experiment', '?'))
    table.add_row("Subject", config.get('subject', '?'))

    features = config.get('features', [])
    feat_str = ", ".join(
        f"{f['name']} [dim]({f.get('source', 'compute')})[/]" for f in features
    )
    table.add_row("Features", feat_str or "(none)")
    table.add_row("Model", config.get('model', {}).get('type', 'bootstrap_ridge'))
    table.add_row("Reporters", str(config.get('reporting', {}).get('formats', [])))
    table.add_row("Stages", ", ".join(stages) if stages else "all")

    console.print(Panel(
        table,
        title="[bold bright_cyan]Dry Run[/]",
        border_style="bright_cyan",
        padding=(0, 1),
    ))


def validate_line(ok: bool, message: str):
    """Print a validation check line."""
    if ok:
        console.print(f"  [bold green]ok[/]  {message}", highlight=False)
    else:
        console.print(f"  [bold red]!![/]  {message}", highlight=False)


def plugins_table(plugins: dict, title: str = "Available Plugins"):
    """Print plugin listing as a styled table."""
    labels = {
        'stimulus_loaders': 'Stimulus Loaders',
        'response_loaders': 'Response Loaders',
        'response_readers': 'Response Readers',
        'feature_extractors': 'Feature Extractors',
        'feature_sources': 'Feature Sources',
        'preprocessors': 'Preprocessors',
        'preprocessing_steps': 'Preprocessing Steps',
        'analyzers': 'Analyzers',
        'models': 'Models',
        'reporters': 'Reporters',
    }
    table = Table(title=f"[bold]{title}[/]", border_style="bright_cyan")
    table.add_column("Category", style="bold cyan")
    table.add_column("Plugins")

    for key, names in plugins.items():
        label = labels.get(key, key)
        plugin_str = ", ".join(names) if names else "[dim](none)[/]"
        table.add_row(label, plugin_str)

    console.print(table)


def stages_table(stages: list[str]):
    """Print pipeline stages as a styled table."""
    descriptions = {
        'stimuli': 'Load stimulus timing data (TextGrids, TRFiles)',
        'responses': 'Load fMRI response data',
        'features': 'Extract or load features from stimuli',
        'preprocess': 'Trim, normalize, concatenate, delay',
        'model': 'Fit voxelwise encoding model',
        'analyze': 'Postprocessing analysis (variance partition, weights, etc.)',
        'report': 'Generate output artifacts (flatmaps, metrics, etc.)',
    }
    table = Table(title="[bold]Pipeline Stages[/]", border_style="bright_cyan")
    table.add_column("#", style="dim", justify="right")
    table.add_column("Stage", style="bold cyan")
    table.add_column("Description")

    for i, stage in enumerate(stages, 1):
        color = STAGE_COLORS.get(stage, 'white')
        table.add_row(str(i), f"[{color}]{stage}[/]", descriptions.get(stage, ''))

    console.print()
    console.print(table)


def bootstrap_progress(n_boots: int):
    """Create a rich Progress context manager for bootstrap iterations."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[bright_blue]{task.description}"),
        BarColumn(bar_width=30, style="bright_blue", complete_style="bold bright_blue"),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
    )
