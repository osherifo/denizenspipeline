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
    import fmriflow.modules.stimulus_loaders.nsd  # noqa: F401
    import fmriflow.modules.stimulus_loaders.algonauts2023  # noqa: F401

    import fmriflow.modules.response_loaders.bids  # noqa: F401
    import fmriflow.modules.response_loaders.bids_mult  # noqa: F401
    import fmriflow.modules.response_loaders.cloud  # noqa: F401
    import fmriflow.modules.response_loaders.local  # noqa: F401
    import fmriflow.modules.response_loaders.nsd  # noqa: F401
    import fmriflow.modules.response_loaders.algonauts2023  # noqa: F401
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
    import fmriflow.modules.feature_sources.npz_concat  # noqa: F401

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
    import fmriflow.modules.analyzers.project_to_subspace  # noqa: F401
    import fmriflow.modules.analyzers.project_to_fsaverage  # noqa: F401
    import fmriflow.modules.analyzers.block_permutation_significance  # noqa: F401
    import fmriflow.modules.analyzers.algonauts_to_fsaverage  # noqa: F401

    import fmriflow.modules.models.ridge  # noqa: F401
    import fmriflow.modules.models.himalaya  # noqa: F401
    import fmriflow.modules.models.kernelized_banded_ridge  # noqa: F401

    import fmriflow.modules.reporters.metrics  # noqa: F401
    import fmriflow.modules.reporters.flatmap  # noqa: F401
    import fmriflow.modules.reporters.flatmap_mapped  # noqa: F401
    import fmriflow.modules.reporters.weights  # noqa: F401
    import fmriflow.modules.reporters.histogram  # noqa: F401
    import fmriflow.modules.reporters.webgl  # noqa: F401
    import fmriflow.modules.reporters.fsaverage_flatmap  # noqa: F401
    import fmriflow.modules.reporters.semantic_rgb_flatmap  # noqa: F401
    import fmriflow.modules.reporters.arrays_dump  # noqa: F401
    import fmriflow.modules.reporters.r_flatmap  # noqa: F401
    import fmriflow.modules.reporters.r2_flatmap  # noqa: F401
    import fmriflow.modules.reporters.native_flatmap  # noqa: F401
    import fmriflow.modules.reporters.nsd_fsaverage_flatmap  # noqa: F401
    import fmriflow.modules.reporters.algonauts_fsaverage_flatmap  # noqa: F401

    # Group-scope analyzers
    import fmriflow.modules.group_analyzers.voxelwise_mean  # noqa: F401
    import fmriflow.modules.group_analyzers.significance_count  # noqa: F401
    import fmriflow.modules.group_analyzers.scalar_summary  # noqa: F401
    import fmriflow.modules.group_analyzers.stacked_weights_pca  # noqa: F401
    import fmriflow.modules.group_analyzers.external_pca_basis  # noqa: F401

    # Group-scope reporters
    import fmriflow.modules.group_reporters.group_summary_html  # noqa: F401
    import fmriflow.modules.group_reporters.group_npy_dump  # noqa: F401
    import fmriflow.modules.group_reporters.group_fsaverage_flatmap  # noqa: F401

    # Study-scope analyzers (generic). Replication-specific study analyzers
    # (cross-modal / semantic-PC / amodal) ship as user addon modules under
    # $FMRIFLOW_HOME/addons/modules/, not as built-ins.
    import fmriflow.modules.study_analyzers.group_delta  # noqa: F401
    import fmriflow.modules.study_analyzers.cohen_d_across_groups  # noqa: F401

    # Study-scope reporters (generic). Replication-specific reporters live in
    # user addon modules (see above).
    import fmriflow.modules.study_reporters.study_summary_html  # noqa: F401
    import fmriflow.modules.study_reporters.study_delta_flatmap  # noqa: F401

    # QA reporters (per-stage diagnostic viz)
    import fmriflow.modules.qa_reporters.model_qa  # noqa: F401
    import fmriflow.modules.qa_reporters.prepare_qa  # noqa: F401
    import fmriflow.modules.qa_reporters.responses_qa  # noqa: F401
    import fmriflow.modules.qa_reporters.features_qa  # noqa: F401
