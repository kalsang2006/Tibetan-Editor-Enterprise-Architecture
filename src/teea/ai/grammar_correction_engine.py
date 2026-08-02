"""Grammar Correction Engine using fine-tuned Tibetan-Llama2-7B with QLoRA.

Loads Tibetan-Llama2-7B base model and optional QLoRA adapter (models/llama2_gec_lora)
to provide fluent grammatical error correction for Tibetan sentences.
"""

from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from teea.core.logging import get_logger

logger = get_logger(__name__)


class GrammarCorrectionEngine:
    """Grammar correction engine using fine-tuned Tibetan-Llama2-7B with QLoRA."""

    def __init__(
        self,
        model_path: str = "./models/llama2_gec_lora",
        base_model_path: str = "./models/Tibetan-Llama2-7B",
    ):
        self.model_path = Path(model_path)
        self.base_model_path = Path(base_model_path)
        self._model = None
        self._tokenizer = None
        self._available = False
        self._device = None
        self._is_causal = True

        target_base = self.base_model_path if self.base_model_path.exists() else Path("./models/tibert-grammar-correction-final")

        if target_base.exists() or self.model_path.exists():
            try:
                import os
                import torch
                from transformers import AutoModelForCausalLM, AutoTokenizer
                torch.set_num_threads(os.cpu_count())
                self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
                load_dir = str(self.base_model_path) if self.base_model_path.exists() else str(self.model_path)

                print(f"[*] Loading GEC model from: {load_dir} (Device: {self._device}, CPU Threads: {torch.get_num_threads()})")
                
                # Check model architecture
                if (Path(load_dir) / "config.json").exists():
                    import json
                    with open(Path(load_dir) / "config.json", "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                        if cfg.get("model_type") == "encoder-decoder":
                            self._is_causal = False

                if self._is_causal:
                    self._tokenizer = AutoTokenizer.from_pretrained(load_dir, trust_remote_code=True)
                    if self._tokenizer.pad_token is None:
                        self._tokenizer.pad_token = self._tokenizer.eos_token

                    # Attempt 4-bit load if CUDA available, else 16-bit / float32
                    offload_dir = Path("./models/.offload")
                    offload_dir.mkdir(parents=True, exist_ok=True)
                    try:
                        from transformers import BitsAndBytesConfig
                        bnb_config = BitsAndBytesConfig(
                            load_in_4bit=True,
                            bnb_4bit_quant_type="nf4",
                            bnb_4bit_compute_dtype=torch.float16,
                            bnb_4bit_use_double_quant=True,
                        )
                        self._model = AutoModelForCausalLM.from_pretrained(
                            load_dir,
                            quantization_config=bnb_config if torch.cuda.is_available() else None,
                            device_map="auto" if torch.cuda.is_available() else None,
                            offload_folder=str(offload_dir),
                            trust_remote_code=True,
                        )
                    except Exception as quant_err:
                        logger.info("quantization_load_fallback", error=str(quant_err))
                        self._model = AutoModelForCausalLM.from_pretrained(
                            load_dir,
                            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
                            device_map="auto" if torch.cuda.is_available() else None,
                            offload_folder=str(offload_dir),
                            trust_remote_code=True,
                        )

                    # Check for LoRA Adapter
                    if self.model_path.exists() and (self.model_path / "adapter_config.json").exists():
                        try:
                            from peft import PeftModel
                            print(f"[*] Loading QLoRA adapter from: {self.model_path}")
                            self._model = PeftModel.from_pretrained(self._model, str(self.model_path))
                            logger.info("llama2_lora_adapter_loaded", path=str(self.model_path))
                        except Exception as peft_err:
                            logger.warning("failed_loading_llama2_lora_adapter", error=str(peft_err))
                    else:
                        print(f"[!] Warning: QLoRA adapter not found at {self.model_path}. Falling back to base model.")
                        logger.warning("llama2_lora_adapter_not_found_using_base_model", path=str(self.model_path))

                    self._available = True
                    logger.info("grammar_correction_llama2_loaded", path=load_dir, device=str(self._device))

                else:
                    # Fallback to Encoder-Decoder TiBERT engine if requested
                    from transformers import BertTokenizer, EncoderDecoderModel
                    self._model = EncoderDecoderModel.from_pretrained(load_dir)
                    self._tokenizer = BertTokenizer.from_pretrained(load_dir)
                    self._model.to(self._device)
                    self._available = True
                    logger.info("grammar_correction_encoder_decoder_loaded", path=load_dir)

            except Exception as e:
                logger.warning("failed_loading_grammar_correction_model", error=str(e))
                self._available = False
        else:
            logger.info("grammar_correction_model_not_found", path=str(self.model_path))

    def is_available(self) -> bool:
        """Check if the grammar correction model is loaded and ready."""
        return self._available

    @lru_cache(maxsize=1000)
    def correct(self, sentence: str, max_length: int = 128) -> str:
        """Correct a single Tibetan sentence.

        Args:
            sentence: Tibetan sentence to correct.
            max_length: Maximum token length of the output sequence.

        Returns:
            Corrected Tibetan sentence string.
        """
        if not sentence or not sentence.strip():
            return sentence

        if not self._available or self._model is None or self._tokenizer is None:
            return sentence

        try:
            if self._is_causal:
                prompt = f"ཞུ་དག: {sentence.strip()}\nདག་ཆ:"
                inputs = self._tokenizer(prompt, return_tensors="pt")
                if self._device is not None and str(self._device) != "cpu":
                    inputs = {k: v.to(self._device) for k, v in inputs.items()}

                outputs = self._model.generate(
                    **inputs,
                    max_new_tokens=16,
                    repetition_penalty=1.1,
                    do_sample=False,
                    pad_token_id=self._tokenizer.pad_token_id,
                    eos_token_id=self._tokenizer.eos_token_id,
                )

                decoded = self._tokenizer.decode(outputs[0], skip_special_tokens=True)
                
                # Extract portion after prompt target marker
                if "དག་ཆ:" in decoded:
                    target_part = decoded.split("དག་ཆ:")[-1].strip()
                    # Take first line if output continues across lines
                    first_line = target_part.split("\n")[0].strip()
                    if first_line and first_line != sentence:
                        return first_line

                return sentence

            else:
                inputs = self._tokenizer(
                    sentence,
                    return_tensors="pt",
                    truncation=True,
                    max_length=max_length,
                )
                if self._device is not None and str(self._device) != "cpu":
                    inputs = {k: v.to(self._device) for k, v in inputs.items()}

                outputs = self._model.generate(
                    **inputs,
                    decoder_start_token_id=self._tokenizer.cls_token_id,
                    max_length=max_length,
                    num_beams=4,
                    early_stopping=True,
                    pad_token_id=self._tokenizer.pad_token_id,
                    eos_token_id=self._tokenizer.eos_token_id,
                )

                return self._tokenizer.decode(outputs[0], skip_special_tokens=True)

        except Exception as e:
            logger.warning("grammar_correction_inference_failed", sentence=sentence, error=str(e))
            return sentence

    def correct_batch(self, sentences: List[str], max_length: int = 128) -> List[str]:
        """Correct multiple Tibetan sentences."""
        if not sentences:
            return []
        return [self.correct(s, max_length=max_length) for s in sentences]
