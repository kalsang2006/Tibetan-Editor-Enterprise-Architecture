"""Unit tests for synthetic Tibetan error generator."""

from __future__ import annotations

from teea.corpus.synthetic import (
    SyntheticErrorDataset,
    SyntheticErrorGenerator,
    SyntheticErrorRecord,
)


def test_synthetic_error_corrupt_sentence() -> None:
    generator = SyntheticErrorGenerator(seed=123)
    sentence = "བཀྲ་ཤིས་བདེ་ལེགས་ཁམས་བཟང་། ང་ཚོས་སྐད་ཡིག་སློབ་སྦྱོང་བྱེད་གི་ཡོད།"
    record = generator.corrupt_sentence(sentence, record_id="test-001")

    assert record is not None
    assert record.id == "test-001"
    assert record.original_text != ""
    assert record.corrupted_text != ""
    assert record.error_type in [
        "TSHEG_DROP",
        "SYLLABLE_SWAP",
        "CHARACTER_CONFUSION",
        "VOWEL_MUTATION",
        "WORD_DUPLICATION",
        "CASE_PARTICLE_SUBSTITUTION",
        "PARTICLE_OMISSION",
    ]


def test_synthetic_error_dataset_generation() -> None:
    generator = SyntheticErrorGenerator(seed=42)
    sentences = [
        "བཀྲ་ཤིས་བདེ་ལེགས་ཁམས་བཟང་།",
        "ང་ཚོས་སྐད་ཡིག་སློབ་སྦྱོང་བྱེད་གི་ཡོད།",
        "དེ་རིང་ཉིན་མོ་དེ་ཧ་ཅང་སྤྲོ་པོ་ཡིན།",
    ]
    dataset = generator.generate_dataset(sentences, max_count=5)

    assert isinstance(dataset, SyntheticErrorDataset)
    assert dataset.total_records > 0
    assert len(dataset.records) == dataset.total_records
    for r in dataset.records:
        assert isinstance(r, SyntheticErrorRecord)
        assert r.original_text != r.corrupted_text
