"""Unit tests for app.services.package_text_tokenizer.TextTokenizer.

Uses a fake spaCy backend (see tests/conftest.py::fake_spacy_backend) to
keep these deterministic and independent of a downloaded language model.
The matcher-match path (compound-phrase collapsing) isn't exercised by the
generic fake matcher, so it gets a dedicated fake matcher here that
reports one match, to cover that branch specifically.
"""

import app.services.package_text_tokenizer as tokenizer_module
from app.services.package_text_tokenizer import TextTokenizer


class TestTokenize:
    def test_strips_stopwords_and_lowercases(self, fake_spacy_backend):
        tokenizer = TextTokenizer()
        tokens = tokenizer.tokenize("The Revenue was Strong")
        assert "revenue" in tokens
        assert "strong" in tokens
        assert "the" not in tokens
        assert "was" not in tokens

    def test_non_strict_mode_keeps_non_alpha_tokens(self, fake_spacy_backend):
        tokenizer = TextTokenizer()
        strict_tokens = tokenizer.tokenize("Revenue: $4.2M", strict=True)
        loose_tokens = tokenizer.tokenize("Revenue: $4.2M", strict=False)
        # Non-strict keeps punctuation/symbol tokens that strict mode drops
        # (both still drop stopwords, of which there are none here).
        assert len(loose_tokens) >= len(strict_tokens)

    def test_caches_nlp_pipeline_per_instance(self, fake_spacy_backend):
        tokenizer = TextTokenizer()
        tokenizer.tokenize("first call")
        nlp_first, _ = tokenizer._get_nlp()
        tokenizer.tokenize("second call")
        nlp_second, _ = tokenizer._get_nlp()
        assert nlp_first is nlp_second

    def test_matcher_collapses_matched_span_into_single_label(self, monkeypatch, fake_spacy_backend):
        """When the compound matcher fires, tokenize() should emit the
        matcher's label instead of the individual tokens it consumed."""

        class _OneMatchMatcher:
            def __init__(self, vocab, *a, **kw):
                self._vocab = vocab
                self._vocab.strings[999] = "INVESTIGATIONAL_DRUG"

            def add(self, name, patterns):
                pass

            def __call__(self, doc):
                # Match the first two tokens as a single compound span.
                if len(doc) >= 2:
                    return [(999, 0, 2)]
                return []

        monkeypatch.setattr(tokenizer_module, "Matcher", _OneMatchMatcher)
        tokenizer = TextTokenizer()

        tokens = tokenizer.tokenize("investigational drug showed promise")

        assert "investigational_drug" in tokens
        # The two consumed tokens shouldn't also appear individually.
        assert "investigational" not in tokens


class TestTokenizeStructured:
    def test_keeps_alpha_lemmas(self, fake_spacy_backend):
        tokenizer = TextTokenizer()
        tokens = tokenizer.tokenize_structured("Revenue Growth")
        assert "revenue" in tokens
        assert "growth" in tokens

    def test_keeps_pure_numeric_tokens(self, fake_spacy_backend):
        tokenizer = TextTokenizer()
        tokens = tokenizer.tokenize_structured("Year 2024 total 4200000")
        assert "2024" in tokens
        assert "4200000" in tokens

    def test_normalizes_currency_like_tokens_to_digits(self, fake_spacy_backend):
        tokenizer = TextTokenizer()
        tokens = tokenizer.tokenize_structured("Total was $4.2")
        assert "4.2" in tokens

    def test_drops_punctuation_and_whitespace_only_tokens(self, fake_spacy_backend):
        tokenizer = TextTokenizer()
        tokens = tokenizer.tokenize_structured("Revenue, growth!")
        assert "," not in tokens
        assert "!" not in tokens

    def test_drops_purely_punctuational_symbol_with_no_digits(self, fake_spacy_backend):
        tokenizer = TextTokenizer()
        # "--" has no digits, isn't alpha: falls through both branches and
        # is dropped entirely (covers the "no digits -> skip" path).
        tokens = tokenizer.tokenize_structured("value -- missing")
        assert "--" not in tokens
