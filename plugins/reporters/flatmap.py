"""FlatmapReporter — generates pycortex flatmap visualizations."""

from __future__ import annotations

from pathlib import Path

from denizenspipeline.core.types import ModelResult, ResponseData


class FlatmapReporter:
    """Generates pycortex flatmap visualizations."""

    name = "flatmap"

    def report(self, result: ModelResult, context, config: dict) -> dict[str, str]:
        import cortex

        resp_data = context.get('responses', ResponseData)
        output_dir = Path(config.get('reporting', {}).get('output_dir', './results'))
        output_dir.mkdir(parents=True, exist_ok=True)

        vol = cortex.Vertex(
            result.scores,
            resp_data.surface,
            vmin=0, vmax=0.5, cmap='inferno',
        )
        path = output_dir / 'prediction_accuracy_flatmap.png'
        cortex.quickflat.make_png(str(path), vol)

        return {'flatmap': str(path)}

    def validate_config(self, config: dict) -> list[str]:
        return []
