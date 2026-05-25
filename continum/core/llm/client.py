from __future__ import annotations

import json
import logging
import warnings
from typing import Any, Dict, Optional

logger = logging.getLogger("continum.core.llm.client")

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

AGENT_CONFIG: Dict[str, Any] = {
    "model_id":          "Qwen/Qwen2.5-1.5B-Instruct",
    # Maximum generation tokens — user requested maximum utilisation
    "max_new_tokens":    2048,
    "temperature":       0.3,
    "do_sample":         True,
    "repetition_penalty":1.1,
}

# Grounding system prompt — ensures the model ONLY uses provided data
GROUNDING_SYSTEM = (
    "You are a senior data scientist presenting findings to VPs and heads of department. "
    "Your responses MUST be grounded exclusively in the data and numbers provided in the prompt. "
    "Do NOT invent, extrapolate, or assume any numbers not explicitly stated. "
    "If data is insufficient to answer, say so clearly. "
    "Write clear, concise, executive-level insights with specific numbers. "
    "Flag risks and opportunities. Be direct — no filler phrases. "
    "Write in plain business language. Do not use emojis, icons, or decorative symbols."
)


# ─────────────────────────────────────────────────────────────────────────────
# ROPE SCALING FIX (from notebook — prevents transformers version conflicts)
# ─────────────────────────────────────────────────────────────────────────────

def _sanitise_rope_scaling(config):
    rs = getattr(config, "rope_scaling", None)
    if not rs or not isinstance(rs, dict):
        return config
    if "type" in rs and "rope_type" not in rs:
        rs["rope_type"] = rs["type"]
    elif "rope_type" in rs and "type" not in rs:
        rs["type"] = rs["rope_type"]
    config.rope_scaling = rs
    return config


# ─────────────────────────────────────────────────────────────────────────────
# TRANSFORMERS CLIENT
# ─────────────────────────────────────────────────────────────────────────────

class TransformersClient:

    def __init__(self, config: Optional[Dict] = None):
        cfg = config or AGENT_CONFIG
        self.model_id        = cfg["model_id"]
        self.max_new_tokens  = cfg.get("max_new_tokens", 2048)
        self.gen_kwargs = {
            # max_new_tokens passed separately at call time to avoid conflict with
            # model's GenerationConfig max_length setting
            "temperature":        cfg.get("temperature", 0.3),
            "do_sample":          cfg.get("do_sample", True),
            "repetition_penalty": cfg.get("repetition_penalty", 1.1),
            "pad_token_id":       None,   # set after tokenizer loads
        }
        self._pipe   = None   # lazy load
        self._device = None
        self._load_lock = __import__("threading").Lock()   # prevent concurrent loading
        logger.info("TransformersClient configured: %s (max_new_tokens=%d)",
                    self.model_id, self.max_new_tokens)

    # ── Lazy loader ────────────────────────────────────────────────────────────

    def _load(self) -> None:
        if self._pipe is not None:
            return   # fast path — no lock needed

        with self._load_lock:
            # Double-checked locking: another thread may have loaded between the
            # check above and acquiring the lock
            if self._pipe is not None:
                return

        try:
            import torch
            self._device = "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            self._device = "cpu"

        try:
            import torch
        except ImportError:
            torch = None

        dtype = None
        try:
            import torch as _t
            dtype = _t.float16 if self._device != "cpu" else _t.float32
        except ImportError:
            pass

        print(f"  Loading {self.model_id} (device={self._device})...")
        logger.info("Loading %s on %s", self.model_id, self._device)

        from transformers import (AutoConfig, AutoModelForCausalLM,
                                   AutoTokenizer, pipeline)

        # Try to pre-load config and sanitise rope_scaling
        model_config = None
        try:
            model_config = AutoConfig.from_pretrained(
                self.model_id, trust_remote_code=False)
            model_config = _sanitise_rope_scaling(model_config)
        except Exception as e:
            logger.debug("Could not pre-load config: %s", e)

        load_attempts = [
            dict(label="native (eager attention, sanitised config)",
                 attn_implementation="eager", config=model_config, force_cpu=False),
            dict(label="native (default attention)",
                 attn_implementation=None,   config=model_config, force_cpu=False),
            dict(label="CPU float32 fallback",
                 attn_implementation="eager", config=model_config, force_cpu=True),
        ]

        last_err = None
        for attempt in load_attempts:
            try:
                tok = AutoTokenizer.from_pretrained(
                    self.model_id, trust_remote_code=False)

                model_kwargs: Dict[str, Any] = {
                    "pretrained_model_name_or_path": self.model_id,
                    "trust_remote_code": False,
                }
                if dtype is not None:
                    model_kwargs["torch_dtype"] = (
                        getattr(__import__("torch"), "float32")
                        if attempt.get("force_cpu") else dtype
                    )
                if attempt.get("config") is not None:
                    model_kwargs["config"] = attempt["config"]
                if attempt.get("attn_implementation"):
                    model_kwargs["attn_implementation"] = attempt["attn_implementation"]
                model_kwargs["device_map"] = "cpu" if attempt.get("force_cpu") else "auto"

                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    mdl = AutoModelForCausalLM.from_pretrained(**model_kwargs)

                if tok.pad_token_id is None:
                    tok.pad_token_id = tok.eos_token_id

                device_for_pipe = -1 if attempt.get("force_cpu") else (
                    0 if self._device == "cuda" else -1)

                self._pipe = pipeline(
                    "text-generation",
                    model=mdl,
                    tokenizer=tok,
                    device=device_for_pipe,
                )
                print(f"  ✅ {self.model_id} loaded: {attempt['label']}")
                logger.info("Loaded: %s", attempt["label"])
                return
            except Exception as e:
                last_err = e
                logger.debug("Load attempt failed [%s]: %s", attempt["label"], e)
                print(f"  Attempt failed [{attempt['label']}]: {type(e).__name__}: {str(e)[:100]}")

        raise RuntimeError(
            f"Failed to load {self.model_id}. Last error: {last_err}"
        )

    # ── Core chat method ───────────────────────────────────────────────────────

    def ask(self, prompt: str, system: str = "") -> str:
        self._load()

        messages = []
        messages.append({
            "role": "system",
            "content": system or GROUNDING_SYSTEM,
        })
        messages.append({"role": "user", "content": prompt})

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                # Pass max_new_tokens explicitly (not via gen_kwargs) to avoid
                # conflict with GenerationConfig's max_length setting
                _kw = {k: v for k, v in self.gen_kwargs.items()
                       if k != "pad_token_id" and v is not None}
                outputs = self._pipe(
                    messages,
                    max_new_tokens=self.max_new_tokens,
                    return_full_text=False,
                    pad_token_id=self._pipe.tokenizer.pad_token_id,
                    **_kw,
                )
            generated = outputs[0]["generated_text"]

            # Handle both str and list formats
            if isinstance(generated, list):
                for msg in reversed(generated):
                    if isinstance(msg, dict) and msg.get("role") == "assistant":
                        return msg["content"].strip()
                last = generated[-1]
                return (last.get("content", str(last))
                        if isinstance(last, dict) else str(last)).strip()
            return str(generated).strip()

        except Exception as e:
            logger.error("TransformersClient.ask() error: %s", e)
            return f"[LLM error: {e}]"

    # ── Narrative helper (from notebook) ──────────────────────────────────────

    def narrate(self, data: Any, context: str) -> str:
        data_str = json.dumps(data, indent=2, default=str)
        # 32K context window — include up to 6000 chars of data (generous)
        if len(data_str) > 6000:
            data_str = data_str[:6000] + "\n... [truncated]"
        prompt = f"{context}\n\nData:\n{data_str}"
        return self.ask(prompt)

    # ── Grounded Ask Continum helper ──────────────────────────────────────────

    def ask_grounded(
        self,
        question: str,
        session_context: str,
        reasoning_chain: Optional[str] = None,
        historical_context: str = "",
    ) -> str:
        context_parts = [
            "=== SESSION CONTEXT ===",
            session_context,
        ]
        if reasoning_chain:
            context_parts += ["", "=== EVIDENCE CHAIN ===", reasoning_chain]
        if historical_context:
            context_parts += ["", "=== HISTORICAL PATTERNS ===", historical_context]

        context_block = "\n".join(context_parts)

        # Maximise context — include all available data up to ~8000 chars
        if len(context_block) > 8000:
            context_block = context_block[:8000] + "\n... [context truncated]"

        prompt = (
            f"{context_block}\n\n"
            f"=== QUESTION ===\n{question}\n\n"
            f"Answer ONLY using the data above. "
            f"If the data doesn't contain enough to answer, say so explicitly. "
            f"Be specific with numbers. Be direct."
        )

        system = (
            "You are a senior experimentation analyst. "
            "You answer questions about A/B experiments based exclusively on the "
            "session data provided. Do not invent numbers or make assumptions "
            "beyond what the data shows. "
            "If results are inconclusive, say so. "
            "Use plain business language."
        )

        return self.ask(prompt, system=system)

    # ── Memory management ──────────────────────────────────────────────────────

    def unload(self) -> None:
        if self._pipe is not None:
            del self._pipe
            self._pipe = None
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass
            logger.info("%s unloaded from memory", self.model_id)
            print(f"  {self.model_id} unloaded from memory")

    @property
    def is_loaded(self) -> bool:
        return self._pipe is not None

    def status(self) -> Dict:
        return {
            "model_id":       self.model_id,
            "is_loaded":      self.is_loaded,
            "device":         self._device or "not loaded yet",
            "max_new_tokens": self.max_new_tokens,
        }


__all__ = ["TransformersClient", "AGENT_CONFIG", "GROUNDING_SYSTEM"]
