"""Built-in plugin registration.

Every plugin class is decorated with a registration decorator from
``_decorators``, which collects it into the shared module-level dicts at
import time.  ``register_builtins()`` simply imports each plugin module
so that the decorators fire.  The :class:`PluginRegistry` points at the
same dicts, so no copying is needed.
"""


def register_builtins(registry):
    """Import all built-in plugin modules so their decorators fire."""

    import denizenspipeline.plugins.stimulus_loaders.textgrid  # noqa: F401
    import denizenspipeline.plugins.stimulus_loaders.skip  # noqa: F401
    import denizenspipeline.plugins.stimulus_loaders.audio  # noqa: F401
    import denizenspipeline.plugins.stimulus_loaders.video  # noqa: F401

    import denizenspipeline.plugins.response_loaders.bids  # noqa: F401
    import denizenspipeline.plugins.response_loaders.cloud  # noqa: F401
    import denizenspipeline.plugins.response_loaders.local  # noqa: F401
    import denizenspipeline.plugins.response_loaders.readers  # noqa: F401
    import denizenspipeline.plugins.response_loaders.multiphase_hdf  # noqa: F401
    import denizenspipeline.plugins.response_loaders.study_hdf  # noqa: F401

    import denizenspipeline.plugins.feature_extractors.basic  # noqa: F401
    import denizenspipeline.plugins.feature_extractors.histograms  # noqa: F401
    import denizenspipeline.plugins.feature_extractors.embeddings  # noqa: F401
    import denizenspipeline.plugins.feature_extractors.audio  # noqa: F401
    import denizenspipeline.plugins.feature_extractors.visual  # noqa: F401

    import denizenspipeline.plugins.feature_sources.compute  # noqa: F401
    import denizenspipeline.plugins.feature_sources.filesystem  # noqa: F401
    import denizenspipeline.plugins.feature_sources.cloud  # noqa: F401
    import denizenspipeline.plugins.feature_sources.grouped_hdf  # noqa: F401

    import denizenspipeline.plugins.preprocessors.default  # noqa: F401
    import denizenspipeline.plugins.preprocessors.pre_prepared  # noqa: F401
    import denizenspipeline.plugins.preprocessors.pipeline  # noqa: F401

    # Preprocessing steps (for pipeline preprocessor)
    import denizenspipeline.plugins.preprocessing_steps.split  # noqa: F401
    import denizenspipeline.plugins.preprocessing_steps.trim  # noqa: F401
    import denizenspipeline.plugins.preprocessing_steps.zscore  # noqa: F401
    import denizenspipeline.plugins.preprocessing_steps.concatenate  # noqa: F401
    import denizenspipeline.plugins.preprocessing_steps.delay  # noqa: F401
    import denizenspipeline.plugins.preprocessing_steps.mean_center  # noqa: F401

    # Analyzers
    import denizenspipeline.plugins.analyzers.weight_analysis  # noqa: F401
    import denizenspipeline.plugins.analyzers.variance_partition  # noqa: F401

    import denizenspipeline.plugins.models.ridge  # noqa: F401
    import denizenspipeline.plugins.models.himalaya  # noqa: F401

    import denizenspipeline.plugins.reporters.metrics  # noqa: F401
    import denizenspipeline.plugins.reporters.flatmap  # noqa: F401
    import denizenspipeline.plugins.reporters.flatmap_mapped  # noqa: F401
    import denizenspipeline.plugins.reporters.weights  # noqa: F401
    import denizenspipeline.plugins.reporters.histogram  # noqa: F401
    import denizenspipeline.plugins.reporters.webgl  # noqa: F401
