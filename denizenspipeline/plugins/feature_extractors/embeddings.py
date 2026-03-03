"""Embedding feature extractors: word2vec, BERT, FastText."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from denizenspipeline.core.datasequence import DataSequence, make_word_ds
from denizenspipeline.core.types import FeatureSet, StimulusData


class Word2VecExtractor:
    """Word2Vec embeddings. Wraps Features.word2vec()."""

    name = "word2vec"
    n_dims = 300

    def __init__(self):
        self._model_cache = {}

    def extract(self, stimuli: StimulusData, run_names: list[str],
                config: dict) -> FeatureSet:
        embedding_path = config['embedding_path']
        model = self._load_model(embedding_path)

        data = {}
        for run_name in run_names:
            stim_run = stimuli.runs[run_name]
            wordseq = make_word_ds(stim_run.textgrid, stim_run.trfile)
            # Build per-word embedding matrix
            words = wordseq.data
            embeddings = np.zeros((len(words), self.n_dims))
            for i, word in enumerate(words):
                w = word.lower().strip()
                if w in model:
                    embeddings[i] = model[w]

            ds = DataSequence(embeddings, wordseq.split_inds,
                              wordseq.data_times, wordseq.tr_times)
            data[run_name] = ds.chunksums(interp="lanczos", window=3)

        return FeatureSet(name=self.name, data=data, n_dims=self.n_dims)

    def validate_config(self, config: dict) -> list[str]:
        errors = []
        if 'embedding_path' not in config:
            errors.append("word2vec requires 'embedding_path'")
        elif not Path(config['embedding_path']).exists():
            errors.append(
                f"Embedding file not found: {config['embedding_path']}")
        return errors

    def _load_model(self, path: str):
        if path not in self._model_cache:
            from gensim.models import KeyedVectors
            self._model_cache[path] = KeyedVectors.load(path)
        return self._model_cache[path]


class BERTExtractor:
    """BERT contextual embeddings (base or large).

    Automatically adapts to model size:
    - hidden_size (768 for base, 1024 for large)
    - num_hidden_layers (12 for base, 24 for large)
    """

    name = "bert"
    n_dims = None  # determined dynamically

    def extract(self, stimuli: StimulusData, run_names: list[str],
                config: dict) -> FeatureSet:
        from transformers import AutoModel, AutoTokenizer
        import torch

        model_name = config.get("model", "bert-base-uncased")
        layer = config.get("layer", None)

        tokenizer = AutoTokenizer.from_pretrained(model_name, use_fast=True)
        model = AutoModel.from_pretrained(
            model_name,
            output_hidden_states=True
        )
        model.eval()

        # Dynamically read model properties
        hidden_size = model.config.hidden_size
        num_layers = model.config.num_hidden_layers

        self.n_dims = hidden_size

        # If no layer specified, use middle layer (common best practice)
        if layer is None:
            layer = num_layers // 2

        if layer < 0 or layer > num_layers:
            raise ValueError(
                f"Layer must be between 0 and {num_layers}, got {layer}"
            )

        data = {}
        for run_name in run_names:
            stim_run = stimuli.runs[run_name]
            wordseq = make_word_ds(stim_run.textgrid, stim_run.trfile)

            embeddings = self._extract_layer(
                model=model,
                tokenizer=tokenizer,
                words=wordseq.data,
                layer=layer,
                max_len=model.config.max_position_embeddings
            )

            ds = DataSequence(
                embeddings,
                wordseq.split_inds,
                wordseq.data_times,
                wordseq.tr_times
            )

            data[run_name] = ds.chunksums(interp="lanczos", window=3)

        return FeatureSet(name=self.name, data=data, n_dims=self.n_dims)

    def validate_config(self, config: dict) -> list[str]:
        errors = []
        layer = config.get("layer", None)

        if layer is not None and (not isinstance(layer, int) or layer < 0):
            errors.append(f"BERT layer must be >= 0, got {layer}")

        return errors

    def _extract_layer(self, model, tokenizer, words, layer: int,
                       max_len: int = 512):
        """Run BERT and extract specific layer word-level embeddings."""
        import torch

        max_len = min(max_len, 512)
        all_embeddings = []

        for chunk_start in range(0, len(words), max_len - 2):
            chunk_words = words[chunk_start:chunk_start + max_len - 2]
            text = " ".join(str(w) for w in chunk_words)

            inputs = tokenizer(
                text,
                return_tensors="pt",
                return_offsets_mapping=True,
                truncation=True,
                max_length=max_len
            )

            offset_mapping = inputs.pop("offset_mapping")[0]

            with torch.no_grad():
                outputs = model(**inputs)

            hidden = outputs.hidden_states[layer][0].cpu().numpy()

            word_embeddings = []
            token_embeddings = []

            # Skip [CLS] and [SEP]
            for ti in range(1, len(hidden) - 1):
                token_embeddings.append(hidden[ti])

                if (ti + 1 >= len(offset_mapping) - 1 or
                        offset_mapping[ti + 1][0].item() == 0):
                    word_embeddings.append(
                        np.mean(token_embeddings, axis=0)
                    )
                    token_embeddings = []

            if token_embeddings:
                word_embeddings.append(
                    np.mean(token_embeddings, axis=0)
                )

            all_embeddings.extend(word_embeddings)

        result = np.zeros((len(words), self.n_dims), dtype=np.float32)
        n = min(len(all_embeddings), len(words))
        if n > 0:
            result[:n] = np.asarray(all_embeddings[:n], dtype=np.float32)

        return result

class FastTextExtractor:
    """FastText embeddings — supports en, zh, es."""

    name = "fasttext"
    n_dims = 300

    def extract(self, stimuli: StimulusData, run_names: list[str],
                config: dict) -> FeatureSet:
        import fasttext
        model_path = config['model_path']
        ft_model = fasttext.load_model(model_path)

        data = {}
        for run_name in run_names:
            stim_run = stimuli.runs[run_name]
            wordseq = make_word_ds(stim_run.textgrid, stim_run.trfile)
            embeddings = np.array([
                ft_model.get_word_vector(str(w)) for w in wordseq.data
            ])
            ds = DataSequence(embeddings, wordseq.split_inds,
                              wordseq.data_times, wordseq.tr_times)
            data[run_name] = ds.chunksums(interp="lanczos", window=3)

        return FeatureSet(name=self.name, data=data, n_dims=self.n_dims)

    def validate_config(self, config: dict) -> list[str]:
        errors = []
        if 'model_path' not in config:
            errors.append("fasttext requires 'model_path'")
        return errors


class GPT2Extractor:
    """GPT-2 contextual embeddings.

    Produces word-level embeddings by running GPT-2 on the run's text and
    mapping subword tokens back to word-level embeddings by averaging.
    """

    name = "gpt2"
    n_dims = 768  # gpt2 / distilgpt2 hidden size

    def extract(self, stimuli: StimulusData, run_names: list[str],
                config: dict) -> FeatureSet:
        from transformers import AutoModel, AutoTokenizer
        import torch

        model_name = config.get("model", "gpt2")  # or "distilgpt2"
        layer = config.get("layer", 8)

        tokenizer = AutoTokenizer.from_pretrained(model_name, use_fast=True)
        model = AutoModel.from_pretrained(model_name, output_hidden_states=True)
        model.eval()

        # GPT-2 has no pad token; set to eos for safety (esp. batching/truncation).
        if tokenizer.pad_token_id is None:
            tokenizer.pad_token = tokenizer.eos_token

        # Update n_dims in case user chooses another GPT-2 variant (e.g. medium/large)
        self.n_dims = int(getattr(model.config, "n_embd", self.n_dims))

        data = {}
        for run_name in run_names:
            stim_run = stimuli.runs[run_name]
            wordseq = make_word_ds(stim_run.textgrid, stim_run.trfile)

            embeddings = self._extract_layer(
                model=model,
                tokenizer=tokenizer,
                words=wordseq.data,
                layer=layer,
            )

            ds = DataSequence(embeddings, wordseq.split_inds,
                              wordseq.data_times, wordseq.tr_times)
            data[run_name] = ds.chunksums(interp="lanczos", window=3)

        return FeatureSet(name=self.name, data=data, n_dims=self.n_dims)

    def validate_config(self, config: dict) -> list[str]:
        errors = []
        layer = config.get("layer", 8)
        if not isinstance(layer, int) or layer < 0:
            errors.append(f"GPT-2 layer must be >= 0, got {layer}")

        # Optional, but helpful: validate that chosen model is GPT-2 family-ish
        model_name = config.get("model", "gpt2")
        if not isinstance(model_name, str) or not model_name:
            errors.append("gpt2 requires 'model' to be a non-empty string (default 'gpt2')")

        return errors

    def _extract_layer(self, model, tokenizer, words, layer: int) -> np.ndarray:
        """Run GPT-2 and extract a specific layer's hidden states.

        Tokenizes the concatenated text, runs the model, then maps subword tokens
        back to word-level embeddings by averaging token vectors that overlap each
        word span (via offset_mapping).
        """
        import torch

        max_len = 1024  # GPT-2 context window (for base); tokenizer will truncate.
        text = " ".join(str(w) for w in words)

        # Get word character spans in the concatenated text.
        # These are used to align token offset spans back to each word.
        word_spans = []
        pos = 0
        for w in words:
            s = text.find(str(w), pos)
            if s < 0:
                # Fallback: approximate span at current pos
                s = pos
            e = s + len(str(w))
            word_spans.append((s, e))
            pos = e + 1  # skip the space

        inputs = tokenizer(
            text,
            return_tensors="pt",
            return_offsets_mapping=True,
            truncation=True,
            max_length=max_len,
            padding=False,
        )
        offset_mapping = inputs.pop("offset_mapping")[0].tolist()  # [(s,e), ...]
        # Some fast tokenizers may include (0,0) for special cases; GPT-2 typically doesn't have CLS/SEP.

        with torch.no_grad():
            outputs = model(**inputs)

        # hidden_states: tuple(len = n_layers+1), each: (batch, n_tokens, hidden)
        hidden = outputs.hidden_states[layer][0].cpu().numpy()  # (n_tokens, n_dims)

        # Map tokens -> words by span overlap.
        # For each word span, average all token vectors whose offsets overlap the word.
        result = np.zeros((len(words), self.n_dims), dtype=np.float32)

        token_spans = offset_mapping
        token_idx = 0
        n_tokens = len(token_spans)

        for wi, (ws, we) in enumerate(word_spans):
            vecs = []

            # Advance token index until tokens might overlap this word
            while token_idx < n_tokens and token_spans[token_idx][1] <= ws:
                token_idx += 1

            ti = token_idx
            while ti < n_tokens:
                ts, te = token_spans[ti]
                if te <= ws:
                    ti += 1
                    continue
                if ts >= we:
                    break
                # Overlap
                if te > ts and we > ws:
                    vecs.append(hidden[ti])
                ti += 1

            if vecs:
                result[wi] = np.mean(np.stack(vecs, axis=0), axis=0)

        return result
