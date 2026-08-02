# TEEA Tibetan NLP Pipeline Benchmark Report

**Generated at:** 2026-08-02 09:14:55

## Environment Metadata

| Property | Value |
| --- | --- |
| os | Windows 10 (10.0.26200) |
| python_version | 3.11.9 |
| cpu_model | Intel64 Family 6 Model 183 Stepping 1, GenuineIntel |
| physical_cores | 14 |
| logical_cores | 20 |
| total_ram_gb | 15.71 |
| available_ram_gb | 5.03 |
| pid | 20684 |
| python_executable | C:\Users\kalsa\AppData\Local\Programs\Python\Python311\python.exe |

## LanguageServerSnapshotBuilder Latency

| Target | Sentences | Mean (ms) | Median (ms) | StdDev | 95% CI (ms) |
| --- | --- | --- | --- | --- | --- |
| single_sentence | 4 | 0.97 | 0.97 | 0.03 | [0.95, 0.99] |
| paragraph | 9 | 7.26 | 6.99 | 1.14 | [6.47, 8.05] |
| page | 45 | 56.47 | 52.53 | 16.47 | [45.06, 67.88] |
| chapter | 180 | 184.02 | 149.97 | 67.54 | [137.22, 230.82] |
| 100KB_doc | 810 | 1175.87 | 990.88 | 431.83 | [876.62, 1475.11] |

## Incremental Parsing Efficiency

| Edit Scenario | Full Analysis (ms) | Reanalyze (ms) | Speedup Ratio | Cache Hit Rate |
| --- | --- | --- | --- | --- |
| single_character | 68.74 | 4.28 | **16.06x** | 98.9% |
| single_syllable | 58.39 | 5.84 | **9.99x** | 98.9% |
| single_word | 85.67 | 8.67 | **9.88x** | 98.9% |
| one_sentence | 92.86 | 4.79 | **19.39x** | 97.8% |
| paragraph | 325.30 | 7.04 | **46.21x** | 100.0% |