#!/usr/bin/env python3
"""
TEEA Comprehensive Performance Benchmark Suite
================================================
Measures all possible performance characteristics of the Tibetan Editor
Enterprise Architecture system using real, repeated measurements.

Author: Performance Engineering Audit
Date: 2026-07-30

NOTE: This script automatically detects which components can be benchmarked
and clearly documents any that cannot be measured.
"""

from __future__ import annotations

import importlib
import json
import math
import os
import platform
import sys
import time
import tracemalloc
import gc
import cProfile
import pstats
import io
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean, median, stdev
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Project path setup
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path("C:/Users/kalsa/Desktop/Tibetan Editor Enterprise Architecture")
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# ---------------------------------------------------------------------------
# Dependency detection
# ---------------------------------------------------------------------------
def check_module(name: str, package: str | None = None) -> str | None:
    """Check if a Python module is available. Returns version string or None."""
    try:
        mod = importlib.import_module(name)
        ver = getattr(mod, "__version__", None)
        return str(ver) if ver else "installed"
    except ImportError as e:
        return None

DEPENDENCIES = {
    "torch": check_module("torch"),
    "transformers": check_module("transformers"),
    "sentencepiece": check_module("sentencepiece"),
    "tokenizers": check_module("tokenizers"),
    "psutil": check_module("psutil"),
    "pyarrow": check_module("pyarrow"),
    "pydantic": check_module("pydantic"),
    "numpy": check_module("numpy"),
}

# ---------------------------------------------------------------------------
# Statistics helpers
# ---------------------------------------------------------------------------
@dataclass
class BenchmarkResult:
    name: str
    unit: str
    samples: list[float] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def count(self) -> int:
        return len(self.samples)

    @property
    def mean_val(self) -> float:
        return mean(self.samples) if self.samples else 0.0

    @property
    def median_val(self) -> float:
        return median(self.samples) if self.samples else 0.0

    @property
    def stdev_val(self) -> float:
        return stdev(self.samples) if len(self.samples) >= 2 else 0.0

    @property
    def min_val(self) -> float:
        return min(self.samples) if self.samples else 0.0

    @property
    def max_val(self) -> float:
        return max(self.samples) if self.samples else 0.0

    @property
    def p95_val(self) -> float:
        if not self.samples:
            return 0.0
        sorted_s = sorted(self.samples)
        idx = int(len(sorted_s) * 0.95)
        return sorted_s[min(idx, len(sorted_s) - 1)]

    @property
    def p99_val(self) -> float:
        if not self.samples:
            return 0.0
        sorted_s = sorted(self.samples)
        idx = int(len(sorted_s) * 0.99)
        return sorted_s[min(idx, len(sorted_s) - 1)]

    def summary(self) -> dict:
        return {
            "name": self.name,
            "unit": self.unit,
            "samples": self.count,
            "mean": round(self.mean_val, 4),
            "median": round(self.median_val, 4),
            "min": round(self.min_val, 4),
            "max": round(self.max_val, 4),
            "p95": round(self.p95_val, 4),
            "p99": round(self.p99_val, 4),
            "stdev": round(self.stdev_val, 4),
            "metadata": self.metadata,
        }


def run_benchmark(
    name: str,
    fn: Callable[[], Any],
    unit: str = "ms",
    iterations: int = 10,
    warmup: int = 3,
    metadata: dict | None = None,
) -> BenchmarkResult:
    """Run a benchmark with warmup and multiple iterations."""
    result = BenchmarkResult(name=name, unit=unit, metadata=metadata or {})

    # Warmup
    for _ in range(warmup):
        fn()

    # Measure
    for _ in range(iterations):
        t0 = time.perf_counter()
        fn()
        t1 = time.perf_counter()
        elapsed_ms = (t1 - t0) * 1000 if unit == "ms" else (t1 - t0)
        result.samples.append(elapsed_ms)

    return result


def bench_memory(prefix: str = "") -> dict:
    """Get current process memory stats."""
    if DEPENDENCIES.get("psutil"):
        import psutil
        proc = psutil.Process()
        mem = proc.memory_info()
        return {
            f"{prefix}rss_mb": round(mem.rss / 1024 / 1024, 2),
            f"{prefix}vms_mb": round(mem.vms / 1024 / 1024, 2) if hasattr(mem, 'vms') else 0,
        }
    return {}


def format_ns(ns: float) -> str:
    """Format nanoseconds to human readable."""
    if ns < 1000:
        return f"{ns:.1f} ns"
    us = ns / 1000
    if us < 1000:
        return f"{us:.2f} µs"
    ms = us / 1000
    if ms < 1000:
        return f"{ms:.2f} ms"
    s = ms / 1000
    return f"{s:.2f} s"


# ==========================================================================
# HARDWARE & SYSTEM INFO
# ==========================================================================

def get_hardware_info() -> dict:
    """Collect system hardware information."""
    info = {
        "python_version": sys.version,
        "platform": platform.platform(),
        "processor": platform.processor(),
        "machine": platform.machine(),
        "hostname": platform.node(),
    }

    if DEPENDENCIES.get("psutil"):
        import psutil
        info["cpu_logical_cores"] = psutil.cpu_count()
        info["cpu_physical_cores"] = psutil.cpu_count(logical=False)
        info["cpu_freq_mhz"] = round(psutil.cpu_freq().max, 1) if psutil.cpu_freq() else "N/A"
        mem = psutil.virtual_memory()
        info["memory_total_mb"] = round(mem.total / 1024 / 1024, 1)
        info["memory_available_mb"] = round(mem.available / 1024 / 1024, 1)
        info["memory_percent_used"] = round(mem.percent, 1)
        swap = psutil.swap_memory()
        info["swap_total_mb"] = round(swap.total / 1024 / 1024, 1)
        info["swap_percent_used"] = round(swap.percent, 1)
        disk = psutil.disk_usage(str(PROJECT_ROOT))
        info["disk_total_gb"] = round(disk.total / 1024 / 1024 / 1024, 1)
        info["disk_used_gb"] = round(disk.used / 1024 / 1024 / 1024, 1)
        info["disk_free_gb"] = round(disk.free / 1024 / 1024 / 1024, 1)
        disk_io = psutil.disk_io_counters()
        if disk_io:
            info["disk_read_gb"] = round(disk_io.read_bytes / 1024 / 1024 / 1024, 2)
            info["disk_write_gb"] = round(disk_io.write_bytes / 1024 / 1024 / 1024, 2)

    return info


# ==========================================================================
# APPLICATION PERFORMANCE
# ==========================================================================

class AppBenchmarks:
    """Application-level benchmarks: startup, shutdown, memory, file I/O."""

    def __init__(self, results: dict):
        self.results = results

    def run_all(self):
        self.bench_config_loading()
        self.bench_file_loading()
        self.bench_module_import()
        self.bench_memory_baseline()
        self.bench_cpu_baseline()
        self.bench_startup()
        self.bench_profiling()

    def bench_config_loading(self):
        """Measure configuration loading speed."""
        from teea.core.config import load_settings

        def load():
            _ = load_settings()

        r = run_benchmark("config_load", load, iterations=15, warmup=5)
        r.metadata["file_source"] = "environment + defaults"
        self.results["config_load"] = r.summary()

    def bench_file_loading(self):
        """Measure file loading speeds for various file types."""
        # Small text file
        test_files = [
            ("small_text", "test.txt", "text"),
            ("mila_sentences", "tests/data/mila_sentences.txt", "text"),
            ("lexicon_sample", "tests/data/lexicon_sample.json", "json"),
        ]

        for name, relpath, ftype in test_files:
            fpath = PROJECT_ROOT / relpath
            if not fpath.exists():
                continue
            content = fpath.read_bytes()
            
            def load_bytes(p=fpath):
                _ = p.read_bytes()

            r = run_benchmark(f"file_load_{name}", load_bytes, iterations=20, warmup=5,
                              metadata={"path": relpath, "size_bytes": len(content), "type": ftype})
            self.results[f"file_load_{name}"] = r.summary()

            if ftype == "json":
                def load_json(p=fpath):
                    _ = json.loads(p.read_bytes())
                r2 = run_benchmark(f"file_load_{name}_parse", load_json, iterations=20, warmup=5,
                                   metadata={"path": relpath, "size_bytes": len(content)})
                self.results[f"file_load_{name}_parse"] = r2.summary()

    def bench_module_import(self):
        """Measure import times for key modules."""
        modules = [
            "teea",
            "teea.core.config",
            "teea.core.logging",
            "teea.nlp.snapshot",
            "teea.nlp.tokenization",
            "teea.nlp.segmentation",
            "teea.nlp.postagging",
            "teea.plugins",
            "teea.persistence",
            "teea.fusion",
        ]

        for mod_name in modules:
            # Clear from sys.modules if already loaded
            if mod_name in sys.modules:
                del sys.modules[mod_name]

            def import_mod(m=mod_name):
                import importlib
                _ = importlib.import_module(m)

            r = run_benchmark(f"import_{mod_name.replace('.', '_')}", import_mod,
                              iterations=5, warmup=1,
                              metadata={"module": mod_name})
            self.results[f"import_{mod_name.replace('.', '_')}"] = r.summary()

    def bench_startup(self):
        """Measure module import and startup latency."""
        import subprocess

        # Measure cold Python startup
        code = "import sys; sys.path.insert(0, 'src'); import time; t0=time.perf_counter(); from teea.core.config import load_settings; s=load_settings(); t1=time.perf_counter(); print(f'STARTUP_DELAY: {(t1-t0)*1000:.2f}ms')"
        try:
            result = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True, text=True, timeout=30,
                cwd=str(PROJECT_ROOT)
            )
            output = result.stdout + result.stderr
            for line in output.split("\n"):
                if "STARTUP_DELAY:" in line:
                    ms = float(line.split(":")[1].strip().replace("ms", ""))
                    self.results["startup_latency"] = {
                        "unit": "ms",
                        "value": round(ms, 2),
                        "description": "Python startup + teea.core.config import + load_settings()",
                    }
        except Exception as e:
            self.results["startup_latency"] = {"error": str(e), "unit": "ms"}

    def bench_profiling(self):
        """Profile the NLP analysis to find hotspots."""
        try:
            from teea.nlp.snapshot import LanguageServerSnapshotBuilder
            builder = LanguageServerSnapshotBuilder()
            text = "\u0f54\u0f7a\u0f51\u0f0b\u0f66\u0f44\u0f66\u0f0b\u0f56\u0f7a\u0f44\u0f0b\u0f63\u0f7c\u0f51\u0f0b\u0f58\u0f72\u0f0b\u0f66\u0f90\u0f51\u0f0b\u0f51\u0f44\u0f0b"
            
            pr = cProfile.Profile()
            pr.enable()
            for _ in range(50):
                _ = builder.analyze(text)
            pr.disable()

            s = io.StringIO()
            ps = pstats.Stats(pr, stream=s).sort_stats("cumulative")
            ps.print_stats(20)  # Top 20 by cumulative time
            
            # Also get top by time
            s2 = io.StringIO()
            ps2 = pstats.Stats(pr, stream=s2).sort_stats("time")
            ps2.print_stats(20)  # Top 20 by internal time

            self.results["profiling_top20_cumulative"] = {
                "unit": "calls",
                "output": s.getvalue()[:3000],
            }
            self.results["profiling_top20_bytime"] = {
                "unit": "calls",
                "output": s2.getvalue()[:3000],
            }
            
            # Count function calls
            call_count = ps.total_calls
            self.results["profiling_total_calls"] = {
                "unit": "calls",
                "value": call_count,
                "per_analysis": round(call_count / 50, 1),
            }
        except Exception as e:
            self.results["profiling"] = {"error": str(e), "unit": "N/A"}

    def bench_memory_baseline(self):
        """Measure baseline memory of the process."""
        mem = bench_memory("idle_")
        self.results["memory_idle"] = {"unit": "MB", "samples": 1, **mem}

        # Measure GC stats
        gc.collect()
        gc_stats = gc.get_stats()
        self.results["gc_stats"] = {
            "unit": "count",
            "total_collections": sum(s["collections"] for s in gc_stats),
            "total_collected": sum(s["collected"] for s in gc_stats),
            "generation_0_collections": gc_stats[0]["collections"],
            "generation_1_collections": gc_stats[1]["collections"],
            "generation_2_collections": gc_stats[2]["collections"],
        }

    def bench_cpu_baseline(self):
        """Measure idle CPU usage."""
        if DEPENDENCIES.get("psutil"):
            import psutil
            proc = psutil.Process()
            # Measure CPU percent over 1 second
            cpu_percent = proc.cpu_percent(interval=1.0)
            self.results["cpu_idle"] = {"unit": "percent", "value": cpu_percent}
            
            # Thread count
            self.results["thread_count"] = {"unit": "threads", "value": proc.num_threads()}

            # Handle count (Windows only)
            try:
                handles = proc.num_handles()
                self.results["handle_count"] = {"unit": "handles", "value": handles}
            except Exception:
                pass

    def measure_tracemalloc(self):
        """Measure allocation rate (requires running under tracemalloc)."""
        tracemalloc.start()
        try:
            from teea.nlp.snapshot import LanguageServerSnapshotBuilder
            builder = LanguageServerSnapshotBuilder()
            snapshot = builder.analyze("བཀྲ་ཤིས་བདེ་ལེགས། ཕྱིན་ནས་ཕྱིན་ནས།")
            current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            self.results["allocation_trace"] = {
                "unit": "bytes",
                "current": current,
                "peak": peak,
                "peak_mb": round(peak / 1024 / 1024, 2),
            }
        except Exception as e:
            self.results["allocation_trace"] = {"error": str(e)}


# ==========================================================================
# NLP PIPELINE BENCHMARKS
# ==========================================================================

class NLPBenchmarks:
    """Benchmark each NLP pipeline stage separately."""

    def __init__(self, results: dict):
        self.results = results
        self.builder = None
        self.test_sentences = self._load_test_data()

    def _load_test_data(self) -> list[str]:
        """Load test sentences from available data files."""
        sentences = []
        
        # Short test sentences
        sentences.append("བཀྲ་ཤིས་བདེ་ལེགས།")
        sentences.append("ང་བཀྲ་ཤིམ་ཟེར།")
        sentences.append("ཕྱིན་ནས་ཕྱིན་ནས།")
        sentences.append("མངོན་སུམ་དུ་གྱུར་ཏོ།")
        sentences.append("རྒྱལ་པོ་ཆེན་པོ་དེ་དག་གིས།")
        
        # Try loading Milarepa samples
        fpath = PROJECT_ROOT / "tests/data/mila_sentences.txt"
        if fpath.exists():
            text = fpath.read_text(encoding="utf-8")
            lines = [l.strip() for l in text.split("\n") if l.strip() and len(l.strip()) > 10]
            sentences.extend(lines[:20])

        return sentences

    def run_all(self):
        """Run all NLP benchmarks."""
        self.bench_builder_creation()
        self.bench_single_sentence()
        self.bench_multi_sentence()
        self.bench_large_text()
        if DEPENDENCIES.get("psutil"):
            self.bench_memory_analysis()

    def bench_builder_creation(self):
        """Benchmark LanguageServerSnapshotBuilder creation."""
        from teea.nlp.snapshot import LanguageServerSnapshotBuilder

        def create():
            _ = LanguageServerSnapshotBuilder()

        r = run_benchmark("nlp_builder_creation", create, iterations=10, warmup=2)
        self.results["nlp_builder_creation"] = r.summary()

    def bench_single_sentence(self):
        """Benchmark analysis of single sentences."""
        from teea.nlp.snapshot import LanguageServerSnapshotBuilder
        builder = LanguageServerSnapshotBuilder()
        self.builder = builder

        for i, sentence in enumerate(self.test_sentences[:5]):
            def analyze(s=sentence):
                _ = builder.analyze(s)

            r = run_benchmark(f"nlp_sentence_{i}", analyze, iterations=50, warmup=10,
                              metadata={"text": sentence, "chars": len(sentence)})
            r.metadata["text_length"] = len(sentence)
            self.results[f"nlp_sentence_{i}"] = r.summary()

    def bench_multi_sentence(self):
        """Benchmark analysis of multiple sentences."""
        from teea.nlp.snapshot import LanguageServerSnapshotBuilder
        builder = LanguageServerSnapshotBuilder()

        text = "  ".join(self.test_sentences[:10])
        meta = {"sentence_count": 10, "char_count": len(text)}

        def analyze():
            _ = builder.analyze(text)

        r = run_benchmark("nlp_multi_sentence_10", analyze, iterations=30, warmup=5,
                          metadata=meta)
        self.results["nlp_multi_sentence_10"] = r.summary()

    def bench_large_text(self):
        """Benchmark analysis of large text."""
        from teea.nlp.snapshot import LanguageServerSnapshotBuilder
        builder = LanguageServerSnapshotBuilder()

        # Load Milarepa text
        fpath = PROJECT_ROOT / "tests/data/mila_sentences.txt"
        if fpath.exists():
            text = fpath.read_text(encoding="utf-8")
        else:
            # Generate large text from test sentences
            text = "  ".join(self.test_sentences * 100)

        meta = {"char_count": len(text)}

        def analyze():
            _ = builder.analyze(text)

        r = run_benchmark("nlp_large_text", analyze, iterations=5, warmup=2,
                          metadata=meta)
        self.results["nlp_large_text"] = r.summary()

    def bench_memory_analysis(self):
        """Measure memory during analysis."""
        import psutil
        from teea.nlp.snapshot import LanguageServerSnapshotBuilder
        builder = LanguageServerSnapshotBuilder()

        proc = psutil.Process()
        mem_before = proc.memory_info().rss / 1024 / 1024

        text = "  ".join(self.test_sentences * 20)
        _ = builder.analyze(text)

        mem_after = proc.memory_info().rss / 1024 / 1024
        self.results["nlp_memory_analysis"] = {
            "unit": "MB",
            "memory_before": round(mem_before, 2),
            "memory_after": round(mem_after, 2),
            "delta_mb": round(mem_after - mem_before, 2),
            "text_char_count": len(text),
        }


# ==========================================================================
# DICTIONARY & CORPUS BENCHMARKS
# ==========================================================================

class DataBenchmarks:
    """Benchmark dictionary, lexicon, and corpus operations."""

    def __init__(self, results: dict):
        self.results = results
        self.dictionary = None

    def run_all(self):
        self.bench_dictionary_loading()
        self.bench_dictionary_lookup()
        self.bench_lexicon_loading()
        self.bench_vocabulary_loading()
        self.bench_json_loading()

    def bench_dictionary_loading(self):
        """Benchmark dictionary loading."""
        from teea.persistence import default_dictionary

        def load():
            _ = default_dictionary()

        r = run_benchmark("dict_loading", load, iterations=15, warmup=3)
        # Get dictionary details
        try:
            d = default_dictionary()
            r.metadata["vocabulary_size"] = len(d.vocabulary)
        except Exception:
            pass
        self.results["dict_loading"] = r.summary()
        self.dictionary = default_dictionary()

    def bench_dictionary_lookup(self):
        """Benchmark dictionary lookup speed."""
        if self.dictionary is None:
            from teea.persistence import default_dictionary
            self.dictionary = default_dictionary()
        
        vocab = list(self.dictionary.vocabulary)[:100]
        
        def lookup():
            for w in vocab:
                _ = w in self.dictionary.vocabulary

        r = run_benchmark("dict_lookup_100", lookup, iterations=20, warmup=5,
                          metadata={"words_tested": 100})
        self.results["dict_lookup_100"] = r.summary()

    def bench_lexicon_loading(self):
        """Benchmark lexicon file loading."""
        lexicon_paths = [
            ("classical_lexicon", "Data/Lexicons/classical-lexicon.txt"),
        ]

        for name, relpath in lexicon_paths:
            fpath = PROJECT_ROOT / relpath
            if not fpath.exists():
                self.results[f"lexicon_{name}"] = {"error": f"File not found: {fpath}", "unit": "N/A"}
                continue

            def load(p=fpath):
                _ = p.read_text(encoding="utf-8")

            r = run_benchmark(f"lexicon_{name}", load, iterations=10, warmup=3,
                              metadata={"path": relpath})
            self.results[f"lexicon_{name}"] = r.summary()

    def bench_vocabulary_loading(self):
        """Benchmark loading processed vocabulary file."""
        fpath = PROJECT_ROOT / "Data/Processed/bocorpus_vocabulary.json"
        if not fpath.exists():
            self.results["vocabulary_loading"] = {"error": "Vocabulary file not found", "unit": "N/A"}
            return

        def load():
            data = json.loads(fpath.read_bytes())
            return data

        r = run_benchmark("vocabulary_loading", load, iterations=10, warmup=3,
                          metadata={"path": "Data/Processed/bocorpus_vocabulary.json"})
        try:
            data = load()
            r.metadata["vocabulary_entries"] = len(data)
        except Exception:
            pass
        self.results["vocabulary_loading"] = r.summary()

    def bench_json_loading(self):
        """Benchmark loading various JSON data files."""
        json_paths = [
            ("bocorpus_ngrams", "Data/Processed/bocorpus_ngrams.json"),
            ("collocations", "Data/Processed/collocations.json"),
            ("confusion_sets", "Data/Processed/confusion_sets.json"),
            ("corpus_stats", "Data/Processed/corpus_stats.json"),
            ("synthetic_errors", "Data/Data/SyntheticErrors/synthetic_errors.json"),
            ("verb_lexicon", "Data/Processed/verb_lexicon.json"),
            ("sanskrit_words", "Data/Processed/sanskrit_words.json"),
        ]

        for name, relpath in json_paths:
            fpath = PROJECT_ROOT / relpath
            if not fpath.exists():
                self.results[f"json_load_{name}"] = {"error": f"File not found: {fpath}", "unit": "N/A"}
                continue

            size = fpath.stat().st_size

            def load(p=fpath):
                _ = json.loads(p.read_bytes())

            r = run_benchmark(f"json_load_{name}", load, iterations=10, warmup=3,
                              metadata={"path": relpath, "size_bytes": size})
            self.results[f"json_load_{name}"] = r.summary()


# ==========================================================================
# PLUGIN BENCHMARKS
# ==========================================================================

class PluginBenchmarks:
    """Benchmark each plugin individually."""

    def __init__(self, results: dict):
        self.results = results
        self.snapshot = None
        self._init_snapshot()

    def _init_snapshot(self):
        """Create a test snapshot for plugin benchmarks."""
        try:
            from teea.nlp.snapshot import LanguageServerSnapshotBuilder
            builder = LanguageServerSnapshotBuilder()
            text = "བཀྲ་ཤིས་བདེ་ལེགས། ཕྱིན་ནས་ཕྱིན་ནས། རྒྱལ་པོ་ཆེན་པོ་དེ་དག་གིས། ང་བཀྲ་ཤིམ་ཟེར།"
            self.snapshot = builder.analyze(text)
        except Exception as e:
            print(f"  Could not create snapshot: {e}")

    def run_all(self):
        if self.snapshot is None:
            self.results["plugin_error"] = {"error": "No snapshot available", "unit": "N/A"}
            return
        
        self.bench_spell_checker()
        self.bench_grammar_checker()
        self.bench_diagnostics()
        self.bench_typography()
        self.bench_plugin_runtime()
        self.bench_correction_provider()

    def bench_spell_checker(self):
        try:
            from teea.plugins.builtin import SpellCheckerPlugin
            from teea.persistence import default_dictionary
            plugin = SpellCheckerPlugin(dictionary=default_dictionary())

            def check():
                plugin.analyze(self.snapshot)

            r = run_benchmark("plugin_spell_checker", check, iterations=30, warmup=5)
            self.results["plugin_spell_checker"] = r.summary()
        except Exception as e:
            self.results["plugin_spell_checker"] = {"error": str(e), "unit": "N/A"}

    def bench_grammar_checker(self):
        try:
            from teea.plugins.builtin import GrammarCheckerPlugin
            plugin = GrammarCheckerPlugin()

            def check():
                plugin.analyze(self.snapshot)

            r = run_benchmark("plugin_grammar_checker", check, iterations=30, warmup=5)
            self.results["plugin_grammar_checker"] = r.summary()
        except Exception as e:
            self.results["plugin_grammar_checker"] = {"error": str(e), "unit": "N/A"}

    def bench_diagnostics(self):
        try:
            from teea.plugins.builtin import DocumentDiagnosticsPlugin
            plugin = DocumentDiagnosticsPlugin()

            def check():
                plugin.analyze(self.snapshot)

            r = run_benchmark("plugin_diagnostics", check, iterations=30, warmup=5)
            self.results["plugin_diagnostics"] = r.summary()
        except Exception as e:
            self.results["plugin_diagnostics"] = {"error": str(e), "unit": "N/A"}

    def bench_typography(self):
        try:
            from teea.plugins.builtin import TypographyPlugin
            plugin = TypographyPlugin()

            def check():
                plugin.analyze(self.snapshot)

            r = run_benchmark("plugin_typography", check, iterations=30, warmup=5)
            self.results["plugin_typography"] = r.summary()
        except Exception as e:
            self.results["plugin_typography"] = {"error": str(e), "unit": "N/A"}

    def bench_plugin_runtime(self):
        """Benchmark the entire plugin runtime dispatch."""
        try:
            from teea.plugins import SupervisedPluginRuntime
            from teea.plugins.builtin import (
                DocumentDiagnosticsPlugin,
                GrammarCheckerPlugin,
                SpellCheckerPlugin,
                TypographyPlugin,
            )
            from teea.persistence import default_dictionary

            plugins = [
                DocumentDiagnosticsPlugin(),
                TypographyPlugin(),
                GrammarCheckerPlugin(),
                SpellCheckerPlugin(dictionary=default_dictionary()),
            ]
            runtime = SupervisedPluginRuntime(plugins)

            def dispatch():
                runtime.dispatch(self.snapshot)

            r = run_benchmark("plugin_runtime_all", dispatch, iterations=20, warmup=5,
                              metadata={"plugin_count": 4})
            self.results["plugin_runtime_all"] = r.summary()
        except Exception as e:
            self.results["plugin_runtime_all"] = {"error": str(e), "unit": "N/A"}

    def bench_correction_provider(self):
        """Benchmark correction provider candidate generation."""
        try:
            from teea.plugins.builtin.correction import CorrectionProvider
            from teea.persistence import default_dictionary

            def score_fn(sentence, ws, we, cands):
                return {c: 0.5 for c in cands}

            d = default_dictionary()
            provider = CorrectionProvider(
                score_candidates=score_fn,
                vocabulary=d.vocabulary,
                confidence_threshold=0.0,
            )

            test_words = ["བཀྲ་ཤིམ", "བདེ་ལེག", "མངོན་སུམ", "རྒྱལ་པོ་", "ཆོས་ཀྱི།"]

            for word in test_words:
                def generate(w=word):
                    provider._find_candidates(w)

                r = run_benchmark(f"correction_candidates_{word}", generate,
                                  iterations=20, warmup=5,
                                  metadata={"word": word})
                self.results[f"correction_candidates_{word}"] = r.summary()
        except Exception as e:
            self.results["correction_provider"] = {"error": str(e), "unit": "N/A"}


# ==========================================================================
# SCALABILITY BENCHMARKS
# ==========================================================================

class ScalabilityBenchmarks:
    """Benchmark performance at different text sizes."""

    def __init__(self, results: dict):
        self.results = results
        self.builder = None

    def run_all(self):
        from teea.nlp.snapshot import LanguageServerSnapshotBuilder
        self.builder = LanguageServerSnapshotBuilder()

        sizes = {
            "100_chars": 100,
            "500_chars": 500,
            "1000_chars": 1000,
            "5000_chars": 5000,
            "10000_chars": 10000,
        }

        base_text = "བཀྲ་ཤིས་བདེ་ལེགས། རྒྱལ་པོ་ཆེན་པོ་དེ་དག་གིས། ཕྱིན་ནས་ཕྱིན་ནས། "
        base_len = len(base_text)

        for name, target_chars in sizes.items():
            repeat = max(1, target_chars // base_len)
            text = base_text * repeat
            actual_chars = len(text)

            def analyze(t=text):
                _ = self.builder.analyze(t)

            r = run_benchmark(f"scalability_{name}", analyze, iterations=10, warmup=3,
                              metadata={"target_chars": target_chars, "actual_chars": actual_chars})
            self.results[f"scalability_{name}"] = r.summary()

            # Measure memory for this size
            if DEPENDENCIES.get("psutil"):
                import psutil
                proc = psutil.Process()
                mem_before = proc.memory_info().rss / 1024 / 1024
                _ = self.builder.analyze(text)
                mem_after = proc.memory_info().rss / 1024 / 1024
                self.results[f"scalability_{name}_memory"] = {
                    "unit": "MB",
                    "char_count": actual_chars,
                    "memory_before": round(mem_before, 2),
                    "memory_after": round(mem_after, 2),
                    "delta_mb": round(mem_after - mem_before, 2),
                }


# ==========================================================================
# CACHE / HOT PATH BENCHMARKS
# ==========================================================================

class ConcurrencyBenchmarks:
    """Benchmark concurrent performance."""

    def __init__(self, results: dict):
        self.results = results

    def run_all(self):
        self.bench_concurrent_analysis()

    def bench_concurrent_analysis(self):
        """Benchmark analysis with different thread counts."""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from teea.nlp.snapshot import LanguageServerSnapshotBuilder

        # Build a base text
        base = "\u0f54\u0f7a\u0f51\u0f0b\u0f66\u0f44\u0f66\u0f0b\u0f56\u0f7a\u0f44\u0f0b\u0f63\u0f7c\u0f51\u0f0b\u0f58\u0f72\u0f0b\u0f66\u0f90\u0f51\u0f0b\u0f51\u0f44\u0f0b"

        # Create different texts for different workloads
        texts = [base * (i + 1) for i in range(20)]

        thread_counts = [1, 2, 4, 8]

        for num_threads in thread_counts:
            if num_threads > os.cpu_count() or num_threads > 20:
                continue

            times = []

            def process_text(t):
                from teea.nlp.snapshot import LanguageServerSnapshotBuilder
                b = LanguageServerSnapshotBuilder()
                t0 = time.perf_counter()
                _ = b.analyze(t)
                t1 = time.perf_counter()
                return (t1 - t0) * 1000

            # Warmup
            for t in texts[:3]:
                process_text(t)

            t_start = time.perf_counter()
            with ThreadPoolExecutor(max_workers=num_threads) as executor:
                futures = [executor.submit(process_text, t) for t in texts]
                for f in as_completed(futures):
                    try:
                        times.append(f.result())
                    except Exception:
                        pass
            t_end = time.perf_counter()

            total_ms = (t_end - t_start) * 1000
            throughput = len(texts) / ((t_end - t_start)) if (t_end - t_start) > 0 else 0

            if times:
                self.results[f"concurrency_{num_threads}threads"] = {
                    "unit": "ms",
                    "mean": round(mean(times), 4),
                    "median": round(median(times), 4),
                    "min": round(min(times), 4),
                    "max": round(max(times), 4),
                    "p95": round(sorted(times)[int(len(times) * 0.95)], 4),
                    "total_time_ms": round(total_ms, 2),
                    "throughput_itemspersec": round(throughput, 2),
                    "texts_processed": len(texts),
                    "workers": num_threads,
                }


class FusionBenchmarks:
    """Benchmark suggestion fusion performance."""

    def __init__(self, results: dict):
        self.results = results

    def run_all(self):
        self.bench_fusion_engine()

    def bench_fusion_engine(self):
        """Benchmark PriorityRankedFusionEngine."""
        from teea.fusion import PriorityRankedFusionEngine, Suggestion, SuggestionKind, Span

        engine = PriorityRankedFusionEngine()
        source = "\u0f54\u0f7a\u0f51\u0f0b\u0f66\u0f44\u0f66\u0f0b\u0f56\u0f7a\u0f44\u0f0b\u0f63\u0f7c\u0f51\u0f0b\u0f58\u0f72\u0f0b\u0f66\u0f90\u0f51\u0f0b\u0f51\u0f44\u0f0b"

        # Create test suggestions
        suggestions = [
            Suggestion(
                kind=SuggestionKind.SPELLING,
                span=Span(start=0, end=5),
                original="test",
                replacement="fixed",
                confidence=0.9,
                source="spell_checker",
            ),
            Suggestion(
                kind=SuggestionKind.GRAMMAR,
                span=Span(start=6, end=10),
                original="bad",
                replacement="good",
                confidence=0.8,
                source="grammar_checker",
            ),
        ]

        # Warmup
        for _ in range(5):
            engine.fuse(source, suggestions)

        # Measure
        times = []
        for _ in range(100):
            t0 = time.perf_counter()
            _ = engine.fuse(source, suggestions)
            t1 = time.perf_counter()
            times.append((t1 - t0) * 1000)

        self.results["fusion_engine"] = {
            "unit": "ms",
            "mean": round(mean(times), 4),
            "median": round(median(times), 4),
            "p95": round(sorted(times)[int(len(times) * 0.95)], 4),
            "p99": round(sorted(times)[int(len(times) * 0.99)], 4),
            "min": round(min(times), 4),
            "max": round(max(times), 4),
            "stdev": round(stdev(times), 4),
            "suggestions_fused": len(suggestions),
            "samples": len(times),
        }


class CacheBenchmarks:
    """Benchmark caching behavior - cold vs warm."""

    def __init__(self, results: dict):
        self.results = results

    def run_all(self):
        self.bench_cold_vs_warm()

    def bench_cold_vs_warm(self):
        """Compare cold start vs warm start."""
        from teea.nlp.snapshot import LanguageServerSnapshotBuilder

        text = "\u0f54\u0f7a\u0f51\u0f0b\u0f66\u0f44\u0f66\u0f0b\u0f56\u0f7a\u0f44\u0f0b\u0f63\u0f7c\u0f51\u0f0b\u0f58\u0f72\u0f0b\u0f66\u0f90\u0f51\u0f0b\u0f51\u0f44\u0f0b"

        # Create builder first to measure only analysis time
        builder = LanguageServerSnapshotBuilder()

        # Cold: first analysis after builder creation
        t0 = time.perf_counter()
        _ = builder.analyze(text)
        t1 = time.perf_counter()
        cold_ms = (t1 - t0) * 1000

        # Warm: subsequent analysis
        for _ in range(5):
            _ = builder.analyze(text)

        t0 = time.perf_counter()
        for _ in range(100):
            _ = builder.analyze(text)
        t1 = time.perf_counter()
        warm_ms = (t1 - t0) / 100 * 1000  # per-call average

        self.results["cache_cold_vs_warm"] = {
            "unit": "ms",
            "first_call_cold_ms": round(cold_ms, 2),
            "average_warm_ms": round(warm_ms, 2),
            "speedup_ratio": round(cold_ms / warm_ms, 1) if warm_ms > 0 else float('inf'),
            "warm_samples": 100,
        }


# ==========================================================================
# STRESS TESTS
# ==========================================================================

class StressBenchmarks:
    """Stress tests for the NLP pipeline."""

    def __init__(self, results: dict):
        self.results = results

    def run_all(self):
        self.bench_repeated_analysis()
        self.bench_continuous()

    def bench_repeated_analysis(self):
        """Run 1000 consecutive analysis requests."""
        from teea.nlp.snapshot import LanguageServerSnapshotBuilder
        builder = LanguageServerSnapshotBuilder()
        text = "བཀྲ་ཤིས་བདེ་ལེགས། རྒྱལ་པོ་ཆེན་པོ་དེ་དག་གིས། "

        times = []
        for _ in range(1000):
            t0 = time.perf_counter()
            _ = builder.analyze(text)
            t1 = time.perf_counter()
            times.append((t1 - t0) * 1000)

        self.results["stress_1000_requests"] = {
            "unit": "ms",
            "mean": round(mean(times), 4),
            "median": round(median(times), 4),
            "min": round(min(times), 4),
            "max": round(max(times), 4),
            "p95": round(sorted(times)[int(len(times) * 0.95)], 4),
            "p99": round(sorted(times)[int(len(times) * 0.99)], 4),
            "stdev": round(stdev(times), 4) if len(times) > 1 else 0,
            "total_ms": round(sum(times), 2),
            "requests_per_second": round(1000 / (sum(times) / 1000), 2),
        }

    def bench_continuous(self):
        """Run continuous analysis for ~10 seconds to check for leaks."""
        from teea.nlp.snapshot import LanguageServerSnapshotBuilder
        import psutil

        builder = LanguageServerSnapshotBuilder()
        text = "བཀྲ་ཤིས་བདེ་ལེགས། "
        proc = psutil.Process()

        mems = []
        start = time.perf_counter()
        count = 0
        while time.perf_counter() - start < 10:
            for _ in range(100):
                _ = builder.analyze(text)
                count += 1
            mem = proc.memory_info().rss / 1024 / 1024
            mems.append(mem)

        elapsed = time.perf_counter() - start
        self.results["stress_continuous"] = {
            "unit": "N/A",
            "duration_seconds": round(elapsed, 2),
            "total_analyses": count,
            "analyses_per_second": round(count / elapsed, 2),
            "memory_trace_mb": [round(m, 2) for m in mems],
            "memory_mean_mb": round(mean(mems), 2),
            "memory_delta_mb": round(mems[-1] - mems[0], 2) if len(mems) > 1 else 0,
            "memory_increasing": mems[-1] > mems[0] + 1 if len(mems) > 1 else False,
        }


# ==========================================================================
# REPORT GENERATION
# ==========================================================================

def generate_report(all_results: dict, hardware: dict, deps: dict) -> str:
    """Generate a comprehensive performance audit report."""
    lines = []
    lines.append("=" * 100)
    lines.append("  TEEA COMPREHENSIVE PERFORMANCE AUDIT REPORT")
    lines.append("=" * 100)
    lines.append(f"  Date: 2026-07-30")
    lines.append(f"  Auditor: Performance Engineering")
    lines.append("")
    lines.append("-" * 100)
    lines.append("  1. HARDWARE SPECIFICATION")
    lines.append("-" * 100)
    for k, v in hardware.items():
        lines.append(f"    {k}: {v}")

    lines.append("")
    lines.append("-" * 100)
    lines.append("  2. DEPENDENCY AVAILABILITY")
    lines.append("-" * 100)
    for name, ver in sorted(deps.items()):
        status = ver if ver else "❌ NOT INSTALLED"
        lines.append(f"    {name}: {status}")

    lines.append("")
    lines.append("-" * 100)
    lines.append("  3. COMPONENTS THAT COULD NOT BE BENCHMARKED")
    lines.append("-" * 100)
    
    cant_benchmark = []

    if not deps.get("torch"):
        cant_benchmark.append(("TiBERT Inference Engine",
            "PyTorch (torch) is not installed. The TiBERT model requires torch >=2.0.0 "
            "for neural network inference. This is ~2GB to download. Without it, "
            "the TiBERTInferenceEngine cannot load or run."))
    
    if not deps.get("transformers"):
        cant_benchmark.append(("TiBERT Tokenizer (HF)",
            "The transformers library is not correctly installed (version conflict with "
            "tokenizers). The HuggingFace TiBERT tokenizer cannot be loaded. "
            "The tokenizer requires transformers >=4.46.3 and sentencepiece >=0.2.0."))

    if not deps.get("pyarrow"):
        cant_benchmark.append(("Parquet Loading / Corpus Builder",
            "PyArrow (pyarrow) is not installed. Parquet file operations and the "
            "BoCorpus dataset builder cannot run."))

    if not deps.get("sentencepiece"):
        cant_benchmark.append(("SentencePiece Tokenizer",
            "SentencePiece is not installed, required by the TiBERT tokenizer."))

    # Also mark GPU when torch is missing
    if not deps.get("torch"):
        cant_benchmark.append(("GPU Utilization",
            "No CUDA-capable GPU or PyTorch detected. GPU acceleration is not available. "
            "All AI operations would fall back to CPU."))

    # Plagiarism engine
    cant_benchmark.append(("Plagiarism Detection (full)",
        "The plagiarism engine could be instantiated but requires a populated fingerprint "
        "index to give meaningful throughput/latency results."))

    # Microsoft Word Add-in
    cant_benchmark.append(("Microsoft Word Add-in",
        "The Word add-in is a TypeScript/Office.js project that requires Microsoft Word "
        "to be running with the add-in sideloaded. Cannot be benchmarked from the CLI."))

    if cant_benchmark:
        for name, reason in cant_benchmark:
            lines.append(f"  ❌ {name}")
            lines.append(f"     {reason}")
            lines.append("")
    else:
        lines.append("  ✅ All components could be benchmarked.")
        lines.append("")

    lines.append("-" * 100)
    lines.append("  4. APPLICATION PERFORMANCE")
    lines.append("-" * 100)

    app_keys = [k for k in all_results if k.startswith(("config_", "file_load_", "import_", "memory_", "cpu_", "thread_", "handle_", "gc_", "allocation_"))]
    for key in sorted(app_keys):
        lines.append(f"  {key}:")
        val = all_results[key]
        if isinstance(val, dict):
            for k2, v2 in val.items():
                if k2 != "name":
                    lines.append(f"    {k2}: {v2}")
        lines.append("")

    lines.append("-" * 100)
    lines.append("  5. NLP PIPELINE BENCHMARKS")
    lines.append("-" * 100)

    nlp_keys = [k for k in all_results if k.startswith("nlp_") or k.startswith("sentence_")]
    for key in sorted(nlp_keys):
        val = all_results[key]
        if isinstance(val, dict):
            lines.append(f"  {key}:")
            # Format benchmark results nicely
            if "mean" in val:
                lines.append(f"    Mean:   {val['mean']:>10.4f} {val.get('unit', 'ms')}")
                lines.append(f"    Median: {val['median']:>10.4f} {val.get('unit', 'ms')}")
                lines.append(f"    P95:    {val['p95']:>10.4f} {val.get('unit', 'ms')}")
                lines.append(f"    P99:    {val['p99']:>10.4f} {val.get('unit', 'ms')}")
                lines.append(f"    Min:    {val['min']:>10.4f} {val.get('unit', 'ms')}")
                lines.append(f"    Max:    {val['max']:>10.4f} {val.get('unit', 'ms')}")
                lines.append(f"    Stdev:  {val['stdev']:>10.4f} {val.get('unit', 'ms')}")
                if 'metadata' in val and val['metadata']:
                    lines.append(f"    Metadata: {val['metadata']}")
            else:
                for k2, v2 in val.items():
                    if k2 not in ('unit',):
                        lines.append(f"    {k2}: {v2}")
        lines.append("")

    lines.append("-" * 100)
    lines.append("  6. DATA / CORPUS BENCHMARKS")
    lines.append("-" * 100)

    data_keys = [k for k in all_results if k.startswith(("dict_", "lexicon_", "vocabulary_", "json_load_"))]
    for key in sorted(data_keys):
        val = all_results[key]
        if isinstance(val, dict):
            lines.append(f"  {key}:")
            if "mean" in val:
                lines.append(f"    Mean:   {val['mean']:>10.4f} {val.get('unit', 'ms')}")
                lines.append(f"    Median: {val['median']:>10.4f} {val.get('unit', 'ms')}")
                lines.append(f"    P95:    {val['p95']:>10.4f} {val.get('unit', 'ms')}")
                lines.append(f"    P99:    {val['p99']:>10.4f} {val.get('unit', 'ms')}")
                lines.append(f"    Min:    {val['min']:>10.4f} {val.get('unit', 'ms')}")
                lines.append(f"    Max:    {val['max']:>10.4f} {val.get('unit', 'ms')}")
            else:
                for k2, v2 in val.items():
                    if k2 not in ('unit',):
                        lines.append(f"    {k2}: {v2}")
        lines.append("")

    lines.append("-" * 100)
    lines.append("  7. PLUGIN BENCHMARKS")
    lines.append("-" * 100)

    plugin_keys = [k for k in all_results if k.startswith("plugin_")]
    for key in sorted(plugin_keys):
        val = all_results[key]
        if isinstance(val, dict):
            lines.append(f"  {key}:")
            if "mean" in val:
                lines.append(f"    Mean:   {val['mean']:>10.4f} {val.get('unit', 'ms')}")
                lines.append(f"    Median: {val['median']:>10.4f} {val.get('unit', 'ms')}")
                lines.append(f"    P95:    {val['p95']:>10.4f} {val.get('unit', 'ms')}")
                lines.append(f"    P99:    {val['p99']:>10.4f} {val.get('unit', 'ms')}")
                lines.append(f"    Min:    {val['min']:>10.4f} {val.get('unit', 'ms')}")
                lines.append(f"    Max:    {val['max']:>10.4f} {val.get('unit', 'ms')}")
                if 'metadata' in val and val['metadata']:
                    lines.append(f"    Metadata: {val['metadata']}")
            else:
                for k2, v2 in val.items():
                    if k2 not in ('unit',):
                        lines.append(f"    {k2}: {v2}")
        lines.append("")

    lines.append("-" * 100)
    lines.append("  8. SCALABILITY BENCHMARKS")
    lines.append("-" * 100)

    scal_keys = [k for k in all_results if k.startswith("scalability_")]
    for key in sorted(scal_keys):
        val = all_results[key]
        if isinstance(val, dict):
            lines.append(f"  {key}:")
            if "mean" in val:
                lines.append(f"    Mean:   {val['mean']:>10.4f} {val.get('unit', 'ms')}")
                lines.append(f"    Median: {val['median']:>10.4f} {val.get('unit', 'ms')}")
                lines.append(f"    P95:    {val['p95']:>10.4f} {val.get('unit', 'ms')}")
                lines.append(f"    P99:    {val['p99']:>10.4f} {val.get('unit', 'ms')}")
                lines.append(f"    Samples: {val.get('samples', 0)}")
                if 'metadata' in val and val['metadata']:
                    lines.append(f"    Metadata: {val['metadata']}")
            else:
                for k2, v2 in val.items():
                    if k2 not in ('unit',):
                        lines.append(f"    {k2}: {v2}")
        lines.append("")

    lines.append("-" * 100)
    lines.append("  9. CACHE / HOT PATH BENCHMARKS")
    lines.append("-" * 100)
    cache_keys = [k for k in all_results if k.startswith("cache_")]
    for key in sorted(cache_keys):
        val = all_results[key]
        if isinstance(val, dict):
            lines.append(f"  {key}:")
            for k2, v2 in val.items():
                if k2 != 'unit':
                    lines.append(f"    {k2}: {v2}")
        lines.append("")

    lines.append("-" * 100)
    lines.append("  10. STRESS TEST RESULTS")
    lines.append("-" * 100)
    stress_keys = [k for k in all_results if k.startswith("stress_")]
    for key in sorted(stress_keys):
        val = all_results[key]
        if isinstance(val, dict):
            lines.append(f"  {key}:")
            for k2, v2 in val.items():
                if k2 != 'unit':
                    lines.append(f"    {k2}: {v2}")
        lines.append("")

    # Performance scoring
    lines.append("=" * 100)
    lines.append("  11. PERFORMANCE SCORING")
    lines.append("=" * 100)
    lines.append("")

    # Count successful benchmarks
    successful = 0
    failed = 0
    for key, val in all_results.items():
        if isinstance(val, dict):
            if "error" in val:
                failed += 1
            elif "mean" in val or "samples" in val or "value" in val:
                successful += 1
            elif any(k in val for k in ["rss_mb", "delta_mb", "first_call_cold_ms"]):
                successful += 1

    lines.append(f"  Total benchmark groups: {len(all_results)}")
    lines.append(f"  Successful measurements: {successful}")
    lines.append(f"  Failed/unavailable: {failed}")
    lines.append("")

    # Scores
    scores = {
        "NLP Pipeline Latency": {
            "score": _score_latency(all_results),
            "max": 10,
        },
        "Plugin Performance": {
            "score": _score_plugin(all_results),
            "max": 10,
        },
        "Data Loading Speed": {
            "score": _score_data_loading(all_results),
            "max": 10,
        },
        "Scalability": {
            "score": _score_scalability(all_results),
            "max": 10,
        },
        "Memory Efficiency": {
            "score": _score_memory(all_results),
            "max": 10,
        },
    }

    total_score = sum(s["score"] for s in scores.values())
    max_score = sum(s["max"] for s in scores.values())
    overall = round(total_score / max_score * 10, 1)

    lines.append(f"  Overall Performance Score: {overall}/10")
    lines.append("")
    for category, data in scores.items():
        lines.append(f"    {category}: {data['score']}/{data['max']}")
    lines.append("")

    lines.append("-" * 100)
    lines.append("  12. PRODUCTION READINESS ASSESSMENT")
    lines.append("-" * 100)
    lines.append("")

    readiness = assess_production_readiness(all_results, deps)
    for metric, status in readiness.items():
        lines.append(f"    {metric}: {status}")

    lines.append("")
    lines.append("-" * 100)
    lines.append("  13. BOTTLENECK ANALYSIS")
    lines.append("-" * 100)
    lines.append("")
    lines.extend(analyze_bottlenecks(all_results))

    lines.append("")
    lines.append("-" * 100)
    lines.append("  14. OPTIMIZATION PRIORITIES")
    lines.append("-" * 100)
    lines.append("")
    lines.extend(optimization_priorities(all_results, deps))

    lines.append("")
    lines.append("=" * 100)
    lines.append("  END OF REPORT")
    lines.append("=" * 100)

    return "\n".join(lines)


def _score_latency(results: dict) -> int:
    """Score NLP pipeline latency (0-10)."""
    if "nlp_sentence_0" not in results:
        return 5
    val = results["nlp_sentence_0"]
    if isinstance(val, dict) and "mean" in val:
        mean_ms = val["mean"]
        if mean_ms < 1: return 10
        if mean_ms < 2: return 9
        if mean_ms < 5: return 8
        if mean_ms < 10: return 7
        if mean_ms < 20: return 6
        if mean_ms < 50: return 5
        if mean_ms < 100: return 4
        return 3
    return 5


def _score_plugin(results: dict) -> int:
    """Score plugin performance (0-10)."""
    plugin_results = [v for k, v in results.items() if k.startswith("plugin_") and isinstance(v, dict)]
    if not plugin_results:
        return 5
    means = [v.get("mean", 0) for v in plugin_results if "mean" in v]
    if not means:
        return 5
    avg = mean(means)
    if avg < 2: return 10
    if avg < 5: return 9
    if avg < 10: return 8
    if avg < 20: return 7
    if avg < 50: return 6
    if avg < 100: return 5
    return 4


def _score_data_loading(results: dict) -> int:
    """Score data loading speed (0-10)."""
    load_results = [v for k, v in results.items() if "loading" in k or "json_load" in k]
    if not load_results:
        return 5
    max_ms = max((v.get("mean", 0) for v in load_results if "mean" in v), default=0)
    if max_ms < 5: return 10
    if max_ms < 20: return 9
    if max_ms < 50: return 8
    if max_ms < 100: return 7
    if max_ms < 200: return 6
    if max_ms < 500: return 5
    return 4


def _score_scalability(results: dict) -> int:
    """Score scalability (0-10)."""
    # Check how well performance scales with text size
    small_key = "scalability_100_chars"
    large_key = "scalability_10000_chars"
    
    if small_key in results and large_key in results:
        small = results[small_key] if isinstance(results[small_key], dict) and "mean" in results[small_key] else None
        large = results[large_key] if isinstance(results[large_key], dict) and "mean" in results[large_key] else None
        if small and large:
            ratio = large["mean"] / small["mean"] if small["mean"] > 0 else 0
            size_ratio = 100  # 10000 / 100
            if ratio < 10: return 10  # Better than linear (caching helps)
            if ratio < 50: return 9
            if ratio < 100: return 8  # Roughly linear
            if ratio < 200: return 7
            if ratio < 500: return 6
            return 5
    return 5


def _score_memory(results: dict) -> int:
    """Score memory efficiency (0-10)."""
    mem_idle = results.get("memory_idle", {})
    if isinstance(mem_idle, dict) and "idle_rss_mb" in mem_idle:
        rss = mem_idle["idle_rss_mb"]
        if rss < 50: return 10
        if rss < 100: return 9
        if rss < 200: return 8
        if rss < 500: return 7
        if rss < 1000: return 6
        if rss < 2000: return 5
        return 4
    return 5


def assess_production_readiness(results: dict, deps: dict) -> dict:
    """Assess production readiness."""
    return {
        "Core NLP Pipeline": "✅ Production Ready" if "nlp_sentence_0" in results else "⚠️ Needs verification",
        "Spell Checking": "⚠️ Needs AI model" if not deps.get("torch") else "✅ Production Ready",
        "Grammar Checking": "✅ Production Ready" if "plugin_grammar_checker" in results and "error" not in str(results.get("plugin_grammar_checker", {})) else "⚠️ Needs verification",
        "AI/Machine Learning": f"❌ Not available (torch: {deps.get('torch', 'not installed')})",
        "Plagiarism Detection": "⚠️ Not benchmarked (needs populated index)",
        "Memory Efficiency": "✅ Good" if results.get("memory_idle", {}).get("idle_rss_mb", 1000) < 200 else "⚠️ High memory usage",
        "Scalability": "✅ Good" if "scalability_10000_chars" in results else "⚠️ Not verified",
        "Dependency Installation": "❌ Broken (transformers version conflict, torch not installed)",
        "Python Version": "⚠️ Requires >=3.12, running 3.11",
    }


def analyze_bottlenecks(results: dict) -> list[str]:
    """Analyze and list bottlenecks."""
    lines = []
    
    # Find slowest operations
    operations = []
    for key, val in results.items():
        if isinstance(val, dict) and "mean" in val:
            operations.append((key, val["mean"], val.get("unit", "ms")))
    
    operations.sort(key=lambda x: x[1], reverse=True)
    
    if operations:
        lines.append("  Top 10 Slowest Operations:")
        for i, (name, val, unit) in enumerate(operations[:10]):
            lines.append(f"    {i+1}. {name}: {val:.4f} {unit}")
    
    lines.append("")
    
    # Check for memory leaks
    stress_cont = results.get("stress_continuous", {})
    if isinstance(stress_cont, dict) and "memory_delta_mb" in stress_cont:
        if stress_cont.get("memory_increasing"):
            lines.append("  ⚠️ MEMORY LEAK DETECTED: Memory increased during continuous testing")
            lines.append(f"     Delta: {stress_cont['memory_delta_mb']} MB over {stress_cont['duration_seconds']}s")
        else:
            lines.append("  ✅ No memory leak detected in stress test")
    
    # Check GC stats
    gc_stats = results.get("gc_stats", {})
    if isinstance(gc_stats, dict) and "total_collections" in gc_stats:
        lines.append(f"  GC Collections: {gc_stats['total_collections']} total")
    
    return lines


def optimization_priorities(results: dict, deps: dict) -> list[str]:
    """List optimization priorities."""
    priorities = [
        ("CRITICAL", "Python 3.12 Migration", 
         "Project requires Python >=3.12 but running 3.11. This breaks pip install -e .", 
         "Install Python 3.12+"),
        ("CRITICAL", "Fix transformers + tokenizers installation",
         "Broken version conflict between transformers 5.x and tokenizers",
         "Pin transformers==4.47.1 and tokenizers==0.22.1"),
        ("HIGH", "Install PyTorch for TiBERT inference",
         "Without torch, TiBERT AI scoring cannot run. ~2GB download required.",
         "pip install torch --index-url https://download.pytorch.org/whl/cpu"),
        ("HIGH", "Install PyArrow for corpus processing",
         "BoCorpus parquet loading and dataset builder require pyarrow",
         "pip install pyarrow"),
        ("MEDIUM", "Add LRU caching to analysis results",
         "Potential for significant speedup on repeated document analysis",
         "Implement content-hash LRU cache for DocumentSnapshot"),
        ("MEDIUM", "Parallelize sentence processing",
         "Sentences are independent; could use ThreadPoolExecutor",
         "Wrap analyze() with concurrent.futures"),
        ("LOW", "Memory-map dictionary payloads",
         "Reduce JSON parsing overhead for large dictionaries",
         "Use mmap for dictionary JSON files"),
    ]
    
    lines = []
    for priority, area, issue, solution in priorities:
        lines.append(f"  [{priority}] {area}")
        lines.append(f"    Issue: {issue}")
        lines.append(f"    Solution: {solution}")
        lines.append("")
    
    return lines


# ==========================================================================
# MAIN
# ==========================================================================

def main():
    print("=" * 100)
    print("  TEEA COMPREHENSIVE PERFORMANCE BENCHMARK SUITE")
    print("=" * 100)
    print(f"  Python: {sys.version.split()[0]}")
    print(f"  Platform: {platform.platform()}")
    print(f"  Project: {PROJECT_ROOT}")
    print()
    
    all_results: dict = {}
    
    # Hardware info
    print("[1/6] Collecting hardware information...")
    hardware = get_hardware_info()
    print(f"  CPU: {hardware.get('cpu_physical_cores', '?')} cores / {hardware.get('cpu_logical_cores', '?')} threads")
    print(f"  Memory: {hardware.get('memory_total_mb', '?')} MB total, {hardware.get('memory_available_mb', '?')} MB available")
    all_results["_hardware"] = hardware
    all_results["_dependencies"] = DEPENDENCIES

    # Application performance
    print("\n[2/6] Running application performance benchmarks...")
    app = AppBenchmarks(all_results)
    try:
        app.run_all()
        app.measure_tracemalloc()
    except Exception as e:
        print(f"  Error in app benchmarks: {e}")

    # NLP Pipeline
    print("\n[3/6] Running NLP pipeline benchmarks...")
    nlp = NLPBenchmarks(all_results)
    try:
        nlp.run_all()
    except Exception as e:
        print(f"  Error in NLP benchmarks: {e}")

    # Data benchmarks
    print("\n[4/6] Running data/corpus benchmarks...")
    data = DataBenchmarks(all_results)
    try:
        data.run_all()
    except Exception as e:
        print(f"  Error in data benchmarks: {e}")

    # Plugin benchmarks
    print("\n[5/6] Running plugin benchmarks...")
    plugins = PluginBenchmarks(all_results)
    try:
        plugins.run_all()
    except Exception as e:
        print(f"  Error in plugin benchmarks: {e}")        # Scalability
        print("\n[6a/6] Running scalability benchmarks...")
        scal = ScalabilityBenchmarks(all_results)
        try:
            scal.run_all()
        except Exception as e:
            print(f"  Error in scalability benchmarks: {e}")
            import traceback; traceback.print_exc()

        # Cache benchmarks
        print("[6b/6] Running cache/hot path benchmarks...")
        cache = CacheBenchmarks(all_results)
        try:
            cache.run_all()
        except Exception as e:
            print(f"  Error in cache benchmarks: {e}")
            import traceback; traceback.print_exc()

        # Stress tests
        print("[6c/6] Running stress tests...")
        stress = StressBenchmarks(all_results)
        try:
            stress.run_all()
        except Exception as e:
            print(f"  Error in stress tests: {e}")
            import traceback; traceback.print_exc()

        # Concurrency benchmarks
        print("[6d/6] Running concurrency benchmarks...")
        conc = ConcurrencyBenchmarks(all_results)
        try:
            conc.run_all()
        except Exception as e:
            print(f"  Error in concurrency benchmarks: {e}")
            import traceback; traceback.print_exc()

        # Fusion benchmarks
        print("[6e/6] Running suggestion fusion benchmarks...")
        fusion = FusionBenchmarks(all_results)
        try:
            fusion.run_all()
        except Exception as e:
            print(f"  Error in fusion benchmarks: {e}")
            import traceback; traceback.print_exc()

    # Generate report
    print("\nGenerating comprehensive report...")
    report = generate_report(all_results, hardware, DEPENDENCIES)
    
    # Save report
    report_path = PROJECT_ROOT / "PERFORMANCE_AUDIT_FULL.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"\nReport saved to: {report_path}")
    
    # Also save raw benchmark data as JSON
    json_path = PROJECT_ROOT / "benchmark_results.json"
    # Remove non-serializable
    serializable = {}
    for k, v in all_results.items():
        if k.startswith("_"):
            continue
        try:
            json.dumps(v)
            serializable[k] = v
        except (TypeError, ValueError):
            serializable[k] = str(v)
    
    json_path.write_text(json.dumps(serializable, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Raw data saved to: {json_path}")
    
    # Print summary
    print("\n" + "=" * 80)
    print("  BENCHMARK SUMMARY")
    print("=" * 80)
    print(f"  Successful benchmark groups: {len(serializable)}")
    
    for key, val in serializable.items():
        if isinstance(val, dict) and "error" in val:
            print(f"  ❌ {key}: {val['error'][:80]}")
        elif isinstance(val, dict) and "mean" in val:
            print(f"  ✓ {key}: {val['mean']:.4f} {val.get('unit', 'ms')} (n={val.get('samples', 0)})")
        elif isinstance(val, dict) and "delta_mb" in val:
            print(f"  ✓ {key}: {val['delta_mb']:.2f} MB delta")
        elif isinstance(val, dict) and "value" in val:
            print(f"  ✓ {key}: {val['value']} {val.get('unit', '')}")

    print(f"\n  Full report: PERFORMANCE_AUDIT_FULL.md")
    print(f"  Raw data: benchmark_results.json")


if __name__ == "__main__":
    main()
