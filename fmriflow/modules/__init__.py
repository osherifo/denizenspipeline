"""Built-in module registration.

Every module class is decorated with a registration decorator from
``_decorators``, which collects it into the shared module-level dicts at
import time.  ``register_builtins()`` simply imports each module file
so that the decorators fire.  The :class:`ModuleRegistry` points at the
same dicts, so no copying is needed.
"""


def register_builtins(registry):
    """Import all built-in module files so their decorators fire."""

    import fmriflow.modules.stimulus_loaders.textgrid  # noqa: F401
    import fmriflow.modules.stimulus_loaders.skip  # noqa: F401
    import fmriflow.modules.stimulus_loaders.audio  # noqa: F401
    import fmriflow.modules.stimulus_loaders.video  # noqa: F401

    import fmriflow.modules.response_loaders.bids  # noqa: F401
    import fmriflow.modules.response_loaders.cloud  # noqa: F401
    import fmriflow.modules.response_loaders.local  # noqa: F401
    import fmriflow.modules.response_loaders.readers  # noqa: F401
    import fmriflow.modules.response_loaders.multiphase_hdf  # noqa: F401
    try:
        import fmriflow.modules.response_loaders.study_hdf  # noqa: F401
    except ImportError:
        pass  # optional lab-specific loader, not distributed
    import fmriflow.modules.response_loaders.preproc  # noqa: F401

    import fmriflow.modules.feature_extractors.basic  # noqa: F401
    import fmriflow.modules.feature_extractors.histograms  # noqa: F401
    import fmriflow.modules.feature_extractors.embeddings  # noqa: F401
    import fmriflow.modules.feature_extractors.audio  # noqa: F401
    import fmriflow.modules.feature_extractors.visual  # noqa: F401

    import fmriflow.modules.feature_sources.compute  # noqa: F401
    import fmriflow.modules.feature_sources.filesystem  # noqa: F401
    import fmriflow.modules.feature_sources.cloud  # noqa: F401
    import fmriflow.modules.feature_sources.grouped_hdf  # noqa: F401

    import fmriflow.modules.preparers.default  # noqa: F401
    import fmriflow.modules.preparers.pre_prepared  # noqa: F401
    import fmriflow.modules.preparers.pipeline  # noqa: F401

    # Preparation steps (for pipeline preparer)
    import fmriflow.modules.preparation_steps.split  # noqa: F401
    import fmriflow.modules.preparation_steps.trim  # noqa: F401
    import fmriflow.modules.preparation_steps.zscore  # noqa: F401
    import fmriflow.modules.preparation_steps.concatenate  # noqa: F401
    import fmriflow.modules.preparation_steps.delay  # noqa: F401
    import fmriflow.modules.preparation_steps.mean_center  # noqa: F401

    # Analyzers
    import fmriflow.modules.analyzers.weight_analysis  # noqa: F401
    import fmriflow.modules.analyzers.variance_partition  # noqa: F401

    import fmriflow.modules.models.ridge  # noqa: F401
    import fmriflow.modules.models.himalaya  # noqa: F401

    import fmriflow.modules.reporters.metrics  # noqa: F401
    import fmriflow.modules.reporters.flatmap  # noqa: F401
    import fmriflow.modules.reporters.flatmap_mapped  # noqa: F401
    import fmriflow.modules.reporters.weights  # noqa: F401
    import fmriflow.modules.reporters.histogram  # noqa: F401
    import fmriflow.modules.reporters.webgl  # noqa: F401
