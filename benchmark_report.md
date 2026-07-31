# TEEA Tibetan NLP Pipeline Benchmark Report

**Generated at:** 2026-07-31 14:06:48

## Environment Metadata

| Property | Value |
| --- | --- |
| os | Windows 10 (10.0.26200) |
| python_version | 3.11.9 |
| cpu_model | Intel64 Family 6 Model 183 Stepping 1, GenuineIntel |
| physical_cores | 14 |
| logical_cores | 20 |
| total_ram_gb | 15.71 |
| available_ram_gb | 2.14 |
| pid | 37160 |
| python_executable | C:\Users\kalsa\AppData\Local\Programs\Python\Python311\python.exe |

## LanguageServerSnapshotBuilder Latency

| Target | Sentences | Mean (ms) | Median (ms) | StdDev | 95% CI (ms) |
| --- | --- | --- | --- | --- | --- |
| single_sentence | 4 | 2.06 | 2.09 | 0.18 | [1.85, 2.26] |
| paragraph | 9 | 11.46 | 10.51 | 2.14 | [9.04, 13.88] |
| page | 45 | 36.61 | 29.36 | 13.97 | [20.81, 52.42] |
| chapter | 180 | 164.25 | 155.95 | 39.77 | [119.24, 209.26] |
| 100KB_doc | 810 | 1591.58 | 1111.94 | 931.62 | [537.36, 2645.80] |

## Incremental Parsing Efficiency

| Edit Scenario | Full Analysis (ms) | Reanalyze (ms) | Speedup Ratio | Cache Hit Rate |
| --- | --- | --- | --- | --- |
| single_character | 360.39 | 29.57 | **12.19x** | 98.9% |
| single_syllable | 335.60 | 25.18 | **13.33x** | 98.9% |
| single_word | 467.36 | 22.84 | **20.46x** | 98.9% |
| one_sentence | 304.92 | 33.69 | **9.05x** | 97.8% |
| paragraph | 359.56 | 22.26 | **16.15x** | 100.0% |