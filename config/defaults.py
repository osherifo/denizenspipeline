"""Default configuration values shipped with the package."""

DEFAULT_CONFIG = {
    "stimulus": {
        "loader": "textgrid",
        "language": "en",
        "modality": "reading",
        "sessions": ["generic"],
    },

    "response": {
        "loader": "cloud",
        "mask_type": "thick",
        "multiseries": "mean",
    },

    "preprocessing": {
        "type": "default",
        "trim_start": 5,
        "trim_end": 5,
        "delays": [1, 2, 3, 4],
        "zscore": True,
    },

    "model": {
        "type": "bootstrap_ridge",
        "params": {
            "alphas": "logspace(1,3,20)",
            "n_boots": 50,
            "single_alpha": False,
            "chunk_len": 40,
            "n_chunks": 20,
        },
    },

    "reporting": {
        "formats": ["metrics"],
        "output_dir": "./results",
    },
}
