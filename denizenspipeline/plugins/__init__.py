"""Built-in plugin registration."""


def register_builtins(registry):
    """Register all built-in plugins with the given registry."""

    # Stimulus Loaders
    from denizenspipeline.plugins.stimulus_loaders.textgrid import TextGridStimulusLoader
    from denizenspipeline.plugins.stimulus_loaders.skip import SkipStimulusLoader
    registry._stimulus_loaders['textgrid'] = TextGridStimulusLoader
    registry._stimulus_loaders['skip'] = SkipStimulusLoader

    # Response Loaders
    from denizenspipeline.plugins.response_loaders.cloud import CloudResponseLoader
    from denizenspipeline.plugins.response_loaders.local import LocalResponseLoader
    registry._response_loaders['cloud'] = CloudResponseLoader
    registry._response_loaders['local'] = LocalResponseLoader

    # Feature Sources
    from denizenspipeline.plugins.feature_sources.compute import ComputeSource
    from denizenspipeline.plugins.feature_sources.filesystem import FilesystemSource
    from denizenspipeline.plugins.feature_sources.cloud import CloudSource
    from denizenspipeline.plugins.feature_sources.grouped_hdf import GroupedHDFSource
    registry._feature_sources['compute'] = ComputeSource
    registry._feature_sources['filesystem'] = FilesystemSource
    registry._feature_sources['cloud'] = CloudSource
    registry._feature_sources['grouped_hdf'] = GroupedHDFSource

    # Feature Extractors
    from denizenspipeline.plugins.feature_extractors.basic import (
        NumWordsExtractor, NumLettersExtractor,
        NumPhonemesExtractor, WordLengthStdExtractor,
    )
    from denizenspipeline.plugins.feature_extractors.histograms import (
        English1000Extractor, LetterHistogramExtractor,
        PhonemeHistogramExtractor,
    )
    from denizenspipeline.plugins.feature_extractors.embeddings import (
        Word2VecExtractor, BERTExtractor, FastTextExtractor,
    )
    for cls in [NumWordsExtractor, NumLettersExtractor,
                NumPhonemesExtractor, WordLengthStdExtractor,
                English1000Extractor, LetterHistogramExtractor,
                PhonemeHistogramExtractor,
                Word2VecExtractor, BERTExtractor, FastTextExtractor]:
        registry._feature_extractors[cls.name] = cls

    # Preprocessors
    from denizenspipeline.plugins.preprocessors.default import DefaultPreprocessor
    from denizenspipeline.plugins.preprocessors.pre_prepared import PreparedDataLoader
    registry._preprocessors['default'] = DefaultPreprocessor
    registry._preprocessors['pre_prepared'] = PreparedDataLoader

    # Models
    from denizenspipeline.plugins.models.ridge import BootstrapRidgeModel
    registry._models['bootstrap_ridge'] = BootstrapRidgeModel

    from denizenspipeline.plugins.models.himalaya import (
        HimalayaRidgeModel, BandedRidgeModel, MultipleKernelRidgeModel,
    )
    registry._models['himalaya_ridge'] = HimalayaRidgeModel
    registry._models['banded_ridge'] = BandedRidgeModel
    registry._models['multiple_kernel_ridge'] = MultipleKernelRidgeModel

    # Reporters
    from denizenspipeline.plugins.reporters.metrics import MetricsReporter
    from denizenspipeline.plugins.reporters.flatmap import FlatmapReporter
    from denizenspipeline.plugins.reporters.weights import WeightsReporter
    from denizenspipeline.plugins.reporters.histogram import HistogramReporter
    from denizenspipeline.plugins.reporters.webgl import WebGLReporter
    registry._reporters['metrics'] = MetricsReporter
    registry._reporters['flatmap'] = FlatmapReporter
    registry._reporters['weights'] = WeightsReporter
    registry._reporters['histogram'] = HistogramReporter
    registry._reporters['webgl'] = WebGLReporter
