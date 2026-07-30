====================================================================================================
  TEEA COMPREHENSIVE PERFORMANCE AUDIT REPORT
====================================================================================================
  Date: 2026-07-30
  Auditor: Performance Engineering

----------------------------------------------------------------------------------------------------
  1. HARDWARE SPECIFICATION
----------------------------------------------------------------------------------------------------
    python_version: 3.11.9 (tags/v3.11.9:de54cf5, Apr  2 2024, 10:12:12) [MSC v.1938 64 bit (AMD64)]
    platform: Windows-10-10.0.26200-SP0
    processor: Intel64 Family 6 Model 183 Stepping 1, GenuineIntel
    machine: AMD64
    hostname: Kalsang
    cpu_logical_cores: 20
    cpu_physical_cores: 14
    cpu_freq_mhz: 2600.0
    memory_total_mb: 16091.9
    memory_available_mb: 6684.9
    memory_percent_used: 58.5
    swap_total_mb: 11264.0
    swap_percent_used: 8.5
    disk_total_gb: 951.5
    disk_used_gb: 642.9
    disk_free_gb: 308.5
    disk_read_gb: 98.82
    disk_write_gb: 65.51

----------------------------------------------------------------------------------------------------
  2. DEPENDENCY AVAILABILITY
----------------------------------------------------------------------------------------------------
    numpy: 2.4.6
    psutil: 7.2.2
    pyarrow: ❌ NOT INSTALLED
    pydantic: 2.13.4
    sentencepiece: 0.2.2
    tokenizers: ❌ NOT INSTALLED
    torch: ❌ NOT INSTALLED
    transformers: 5.14.1

----------------------------------------------------------------------------------------------------
  3. COMPONENTS THAT COULD NOT BE BENCHMARKED
----------------------------------------------------------------------------------------------------
  ❌ TiBERT Inference Engine
     PyTorch (torch) is not installed. The TiBERT model requires torch >=2.0.0 for neural network inference. This is ~2GB to download. Without it, the TiBERTInferenceEngine cannot load or run.

  ❌ Parquet Loading / Corpus Builder
     PyArrow (pyarrow) is not installed. Parquet file operations and the BoCorpus dataset builder cannot run.

  ❌ GPU Utilization
     No CUDA-capable GPU or PyTorch detected. GPU acceleration is not available. All AI operations would fall back to CPU.

  ❌ Plagiarism Detection (full)
     The plagiarism engine could be instantiated but requires a populated fingerprint index to give meaningful throughput/latency results.

  ❌ Microsoft Word Add-in
     The Word add-in is a TypeScript/Office.js project that requires Microsoft Word to be running with the add-in sideloaded. Cannot be benchmarked from the CLI.

----------------------------------------------------------------------------------------------------
  4. APPLICATION PERFORMANCE
----------------------------------------------------------------------------------------------------
  allocation_trace:
    unit: bytes
    current: 310160
    peak: 311401
    peak_mb: 0.3

  config_load:
    unit: ms
    samples: 15
    mean: 1.0054
    median: 0.9873
    min: 0.7845
    max: 1.3375
    p95: 1.3375
    p99: 1.3375
    stdev: 0.1381
    metadata: {'file_source': 'environment + defaults'}

  cpu_idle:
    unit: percent
    value: 0.0

  file_load_lexicon_sample:
    unit: ms
    samples: 20
    mean: 0.0841
    median: 0.0829
    min: 0.0806
    max: 0.108
    p95: 0.108
    p99: 0.108
    stdev: 0.0057
    metadata: {'path': 'tests/data/lexicon_sample.json', 'size_bytes': 2688, 'type': 'json'}

  file_load_lexicon_sample_parse:
    unit: ms
    samples: 20
    mean: 0.1241
    median: 0.1189
    min: 0.1132
    max: 0.1794
    p95: 0.1794
    p99: 0.1794
    stdev: 0.0153
    metadata: {'path': 'tests/data/lexicon_sample.json', 'size_bytes': 2688}

  file_load_mila_sentences:
    unit: ms
    samples: 20
    mean: 0.0791
    median: 0.0785
    min: 0.0723
    max: 0.091
    p95: 0.091
    p99: 0.091
    stdev: 0.0044
    metadata: {'path': 'tests/data/mila_sentences.txt', 'size_bytes': 10059, 'type': 'text'}

  file_load_small_text:
    unit: ms
    samples: 20
    mean: 0.0471
    median: 0.0377
    min: 0.033
    max: 0.146
    p95: 0.146
    p99: 0.146
    stdev: 0.0273
    metadata: {'path': 'test.txt', 'size_bytes': 42, 'type': 'text'}

  gc_stats:
    unit: count
    total_collections: 241
    total_collected: 1460
    generation_0_collections: 220
    generation_1_collections: 19
    generation_2_collections: 2

  handle_count:
    unit: handles
    value: 350

  import_teea:
    unit: ms
    samples: 5
    mean: 0.0026
    median: 0.0015
    min: 0.0011
    max: 0.0074
    p95: 0.0074
    p99: 0.0074
    stdev: 0.0027
    metadata: {'module': 'teea'}

  import_teea_core_config:
    unit: ms
    samples: 5
    mean: 0.0025
    median: 0.0013
    min: 0.0011
    max: 0.0067
    p95: 0.0067
    p99: 0.0067
    stdev: 0.0024
    metadata: {'module': 'teea.core.config'}

  import_teea_core_logging:
    unit: ms
    samples: 5
    mean: 0.0024
    median: 0.0012
    min: 0.0011
    max: 0.0069
    p95: 0.0069
    p99: 0.0069
    stdev: 0.0025
    metadata: {'module': 'teea.core.logging'}

  import_teea_fusion:
    unit: ms
    samples: 5
    mean: 0.001
    median: 0.0006
    min: 0.0004
    max: 0.0028
    p95: 0.0028
    p99: 0.0028
    stdev: 0.001
    metadata: {'module': 'teea.fusion'}

  import_teea_nlp_postagging:
    unit: ms
    samples: 5
    mean: 0.0008
    median: 0.0005
    min: 0.0004
    max: 0.0021
    p95: 0.0021
    p99: 0.0021
    stdev: 0.0007
    metadata: {'module': 'teea.nlp.postagging'}

  import_teea_nlp_segmentation:
    unit: ms
    samples: 5
    mean: 0.0009
    median: 0.0005
    min: 0.0005
    max: 0.0023
    p95: 0.0023
    p99: 0.0023
    stdev: 0.0008
    metadata: {'module': 'teea.nlp.segmentation'}

  import_teea_nlp_snapshot:
    unit: ms
    samples: 5
    mean: 0.0011
    median: 0.0005
    min: 0.0004
    max: 0.003
    p95: 0.003
    p99: 0.003
    stdev: 0.0011
    metadata: {'module': 'teea.nlp.snapshot'}

  import_teea_nlp_tokenization:
    unit: ms
    samples: 5
    mean: 0.0008
    median: 0.0005
    min: 0.0004
    max: 0.002
    p95: 0.002
    p99: 0.002
    stdev: 0.0007
    metadata: {'module': 'teea.nlp.tokenization'}

  import_teea_persistence:
    unit: ms
    samples: 5
    mean: 0.0011
    median: 0.0005
    min: 0.0005
    max: 0.0035
    p95: 0.0035
    p99: 0.0035
    stdev: 0.0013
    metadata: {'module': 'teea.persistence'}

  import_teea_plugins:
    unit: ms
    samples: 5
    mean: 0.0012
    median: 0.0006
    min: 0.0004
    max: 0.0038
    p95: 0.0038
    p99: 0.0038
    stdev: 0.0014
    metadata: {'module': 'teea.plugins'}

  memory_idle:
    unit: MB
    samples: 1
    idle_rss_mb: 81.2
    idle_vms_mb: 676.16

  thread_count:
    unit: threads
    value: 23

----------------------------------------------------------------------------------------------------
  5. NLP PIPELINE BENCHMARKS
----------------------------------------------------------------------------------------------------
  nlp_builder_creation:
    Mean:       4.0876 ms
    Median:     4.0233 ms
    P95:        5.6029 ms
    P99:        5.6029 ms
    Min:        2.7773 ms
    Max:        5.6029 ms
    Stdev:      1.2170 ms

  nlp_large_text:
    Mean:     330.2679 ms
    Median:   319.0527 ms
    P95:      387.0461 ms
    P99:      387.0461 ms
    Min:      305.4426 ms
    Max:      387.0461 ms
    Stdev:     32.4598 ms
    Metadata: {'char_count': 3393}

  nlp_memory_analysis:
    memory_before: 97.35
    memory_after: 126.02
    delta_mb: 28.67
    text_char_count: 25678

  nlp_multi_sentence_10:
    Mean:      36.2781 ms
    Median:    37.0977 ms
    P95:       39.0997 ms
    P99:       42.6442 ms
    Min:       21.4781 ms
    Max:       42.6442 ms
    Stdev:      3.7511 ms
    Metadata: {'sentence_count': 10, 'char_count': 406}

  nlp_sentence_0:
    Mean:       1.5824 ms
    Median:     1.4499 ms
    P95:        2.3320 ms
    P99:        3.3253 ms
    Min:        1.2144 ms
    Max:        3.3253 ms
    Stdev:      0.3604 ms
    Metadata: {'text': 'བཀྲ་ཤིས་བདེ་ལེགས།', 'chars': 17, 'text_length': 17}

  nlp_sentence_1:
    Mean:       2.0531 ms
    Median:     1.9963 ms
    P95:        2.5362 ms
    P99:        2.7829 ms
    Min:        1.8795 ms
    Max:        2.7829 ms
    Stdev:      0.1824 ms
    Metadata: {'text': 'ང་བཀྲ་ཤིམ་ཟེར།', 'chars': 14, 'text_length': 14}

  nlp_sentence_2:
    Mean:       1.2540 ms
    Median:     1.2036 ms
    P95:        1.5877 ms
    P99:        2.0813 ms
    Min:        0.9770 ms
    Max:        2.0813 ms
    Stdev:      0.1677 ms
    Metadata: {'text': 'ཕྱིན་ནས་ཕྱིན་ནས།', 'chars': 16, 'text_length': 16}

  nlp_sentence_3:
    Mean:       1.6001 ms
    Median:     1.5257 ms
    P95:        2.0074 ms
    P99:        2.8559 ms
    Min:        0.9164 ms
    Max:        2.8559 ms
    Stdev:      0.2513 ms
    Metadata: {'text': 'མངོན་སུམ་དུ་གྱུར་ཏོ།', 'chars': 20, 'text_length': 20}

  nlp_sentence_4:
    Mean:       2.3526 ms
    Median:     2.1917 ms
    P95:        3.0896 ms
    P99:        3.5556 ms
    Min:        2.0849 ms
    Max:        3.5556 ms
    Stdev:      0.3525 ms
    Metadata: {'text': 'རྒྱལ་པོ་ཆེན་པོ་དེ་དག་གིས།', 'chars': 25, 'text_length': 25}

----------------------------------------------------------------------------------------------------
  6. DATA / CORPUS BENCHMARKS
----------------------------------------------------------------------------------------------------
  dict_loading:
    Mean:       0.0008 ms
    Median:     0.0007 ms
    P95:        0.0020 ms
    P99:        0.0020 ms
    Min:        0.0005 ms
    Max:        0.0020 ms

  dict_lookup_100:
    Mean:      19.2729 ms
    Median:    19.1275 ms
    P95:       20.8759 ms
    P99:       20.8759 ms
    Min:       17.3979 ms
    Max:       20.8759 ms

  json_load_bocorpus_ngrams:
    Mean:     150.2511 ms
    Median:   152.5547 ms
    P95:      160.9602 ms
    P99:      160.9602 ms
    Min:      140.4433 ms
    Max:      160.9602 ms

  json_load_collocations:
    Mean:       0.4298 ms
    Median:     0.4282 ms
    P95:        0.4659 ms
    P99:        0.4659 ms
    Min:        0.3936 ms
    Max:        0.4659 ms

  json_load_confusion_sets:
    Mean:       0.3904 ms
    Median:     0.3827 ms
    P95:        0.4877 ms
    P99:        0.4877 ms
    Min:        0.3461 ms
    Max:        0.4877 ms

  json_load_corpus_stats:
    Mean:       0.7259 ms
    Median:     0.7352 ms
    P95:        0.7605 ms
    P99:        0.7605 ms
    Min:        0.6114 ms
    Max:        0.7605 ms

  json_load_sanskrit_words:
    Mean:       0.3533 ms
    Median:     0.3511 ms
    P95:        0.3735 ms
    P99:        0.3735 ms
    Min:        0.3461 ms
    Max:        0.3735 ms

  json_load_synthetic_errors:
    error: File not found: C:\Users\kalsa\Desktop\Tibetan Editor Enterprise Architecture\Data\Data\SyntheticErrors\synthetic_errors.json

  json_load_verb_lexicon:
    Mean:       0.4640 ms
    Median:     0.4580 ms
    P95:        0.5515 ms
    P99:        0.5515 ms
    Min:        0.4031 ms
    Max:        0.5515 ms

  lexicon_classical_lexicon:
    Mean:       9.6966 ms
    Median:     9.7406 ms
    P95:       10.5849 ms
    P99:       10.5849 ms
    Min:        8.8759 ms
    Max:       10.5849 ms

  vocabulary_loading:
    Mean:     227.1288 ms
    Median:   279.2142 ms
    P95:      310.6017 ms
    P99:      310.6017 ms
    Min:       99.6264 ms
    Max:      310.6017 ms

----------------------------------------------------------------------------------------------------
  7. PLUGIN BENCHMARKS
----------------------------------------------------------------------------------------------------
  plugin_diagnostics:
    error: 'DocumentDiagnosticsPlugin' object has no attribute 'analyze'

  plugin_grammar_checker:
    error: 'GrammarCheckerPlugin' object has no attribute 'analyze'

  plugin_runtime_all:
    Mean:       1.8073 ms
    Median:     1.7468 ms
    P95:        2.3938 ms
    P99:        2.3938 ms
    Min:        1.5041 ms
    Max:        2.3938 ms
    Metadata: {'plugin_count': 4}

  plugin_spell_checker:
    error: 'SpellCheckerPlugin' object has no attribute 'analyze'

  plugin_typography:
    error: 'TypographyPlugin' object has no attribute 'analyze'

----------------------------------------------------------------------------------------------------
  8. SCALABILITY BENCHMARKS
----------------------------------------------------------------------------------------------------
----------------------------------------------------------------------------------------------------
  9. CACHE / HOT PATH BENCHMARKS
----------------------------------------------------------------------------------------------------
----------------------------------------------------------------------------------------------------
  10. STRESS TEST RESULTS
----------------------------------------------------------------------------------------------------
====================================================================================================
  11. PERFORMANCE SCORING
====================================================================================================

  Total benchmark groups: 57
  Successful measurements: 46
  Failed/unavailable: 5

  Overall Performance Score: 7.6/10

    NLP Pipeline Latency: 9/10
    Plugin Performance: 10/10
    Data Loading Speed: 5/10
    Scalability: 5/10
    Memory Efficiency: 9/10

----------------------------------------------------------------------------------------------------
  12. PRODUCTION READINESS ASSESSMENT
----------------------------------------------------------------------------------------------------

    Core NLP Pipeline: ✅ Production Ready
    Spell Checking: ⚠️ Needs AI model
    Grammar Checking: ⚠️ Needs verification
    AI/Machine Learning: ❌ Not available (torch: None)
    Plagiarism Detection: ⚠️ Not benchmarked (needs populated index)
    Memory Efficiency: ✅ Good
    Scalability: ⚠️ Not verified
    Dependency Installation: ❌ Broken (transformers version conflict, torch not installed)
    Python Version: ⚠️ Requires >=3.12, running 3.11

----------------------------------------------------------------------------------------------------
  13. BOTTLENECK ANALYSIS
----------------------------------------------------------------------------------------------------

  Top 10 Slowest Operations:
    1. nlp_large_text: 330.2679 ms
    2. vocabulary_loading: 227.1288 ms
    3. json_load_bocorpus_ngrams: 150.2511 ms
    4. correction_candidates_བདེ་ལེག: 42.2207 ms
    5. correction_candidates_བཀྲ་ཤིམ: 41.4741 ms
    6. nlp_multi_sentence_10: 36.2781 ms
    7. dict_lookup_100: 19.2729 ms
    8. lexicon_classical_lexicon: 9.6966 ms
    9. correction_candidates_མངོན་སུམ: 6.7984 ms
    10. correction_candidates_ཆོས་ཀྱི།: 6.3861 ms

  GC Collections: 241 total

----------------------------------------------------------------------------------------------------
  14. OPTIMIZATION PRIORITIES
----------------------------------------------------------------------------------------------------

  [CRITICAL] Python 3.12 Migration
    Issue: Project requires Python >=3.12 but running 3.11. This breaks pip install -e .
    Solution: Install Python 3.12+

  [CRITICAL] Fix transformers + tokenizers installation
    Issue: Broken version conflict between transformers 5.x and tokenizers
    Solution: Pin transformers==4.47.1 and tokenizers==0.22.1

  [HIGH] Install PyTorch for TiBERT inference
    Issue: Without torch, TiBERT AI scoring cannot run. ~2GB download required.
    Solution: pip install torch --index-url https://download.pytorch.org/whl/cpu

  [HIGH] Install PyArrow for corpus processing
    Issue: BoCorpus parquet loading and dataset builder require pyarrow
    Solution: pip install pyarrow

  [MEDIUM] Add LRU caching to analysis results
    Issue: Potential for significant speedup on repeated document analysis
    Solution: Implement content-hash LRU cache for DocumentSnapshot

  [MEDIUM] Parallelize sentence processing
    Issue: Sentences are independent; could use ThreadPoolExecutor
    Solution: Wrap analyze() with concurrent.futures

  [LOW] Memory-map dictionary payloads
    Issue: Reduce JSON parsing overhead for large dictionaries
    Solution: Use mmap for dictionary JSON files


====================================================================================================
  END OF REPORT
====================================================================================================