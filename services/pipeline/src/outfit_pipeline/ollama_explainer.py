from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional
from urllib import error as urlerror
from urllib import request as urlrequest

from .config import OllamaConfig


_CONFIDENCE_VALUES = {"high", "medium", "low"}
_EMPTY_POINT_VALUES = {"0", "none", "n/a", "na", "null"}
_VOLATILE_FACT_KEYS = {"top_image", "bottom_image", "query_image", "candidate_image"}
_DEFAULT_NUM_PREDICT = 160
_EXTRA_PARSE_RETRY = 1


@dataclass
class OllamaExplainResult:
    status: str
    explanation: Optional[Dict[str, Any]] = None
    raw: str = ""
    error: str = ""
    cached: bool = False
    source: str = ""


class OllamaExplainer:
    PROMPT_VERSION = "v2"

    def __init__(self, cfg: OllamaConfig, cache_dir: Path) -> None:
        self.cfg = cfg
        self.cache_dir = cache_dir / "ollama_explanations"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _normalize_facts(self, obj: Any) -> Any:
        if isinstance(obj, dict):
            out: Dict[str, Any] = {}
            for k in sorted(obj.keys()):
                key = str(k)
                if key in _VOLATILE_FACT_KEYS:
                    continue
                out[key] = self._normalize_facts(obj[k])
            return out
        if isinstance(obj, list):
            return [self._normalize_facts(v) for v in obj]
        if isinstance(obj, float):
            return round(float(obj), 4)
        if isinstance(obj, (str, int, bool)) or obj is None:
            return obj
        return str(obj)

    def _cache_key(self, facts: Dict[str, Any]) -> str:
        normalized = self._normalize_facts(facts)
        payload = {
            "prompt_version": self.PROMPT_VERSION,
            "model": self.cfg.model,
            "facts": normalized,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return sha1(raw.encode("utf-8")).hexdigest()

    def _cache_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def _read_cache(self, key: str) -> Optional[Dict[str, Any]]:
        path = self._cache_path(key)
        if not path.exists():
            return None
        try:
            slot = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(slot, dict):
            return None
        exp = slot.get("explanation")
        if not isinstance(exp, dict):
            return None
        clean = self._sanitize_explanation(exp)
        return clean

    def _write_cache(self, key: str, explanation: Dict[str, Any]) -> None:
        path = self._cache_path(key)
        payload = {
            "prompt_version": self.PROMPT_VERSION,
            "model": self.cfg.model,
            "explanation": explanation,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def _system_prompt(self) -> str:
        return (
            "You are a fashion stylist assistant with strong taste and practical advice. "
            "Use ONLY provided numeric/component facts; never invent unseen item details. "
            "Never change the provided score or label. "
            "Tone: confident, specific, human, not robotic. Avoid generic wording like "
            "'good' or 'works' without concrete reason. "
            "Return strict JSON only with exactly keys: "
            "summary, why_it_works, risk_points, style_suggestion, confidence_note, disclaimer. "
            "Rules: summary is 1 sentence; why_it_works is 2-3 bullets; risk_points is 1-2 bullets; "
            "style_suggestion is 1-2 actionable sentences."
        )

    def _system_prompt_fallback_text(self) -> str:
        return (
            "You are a fashion stylist. Use only provided facts. "
            "Write natural, human advice in plain text with exactly these sections on separate lines:\n"
            "SUMMARY: ...\n"
            "WHY: ...\n"
            "RISK: ...\n"
            "SUGGESTION: ...\n"
            "CONFIDENCE: high|medium|low\n"
            "Do not output JSON or markdown."
        )

    def _user_prompt(self, facts: Dict[str, Any]) -> str:
        return (
            "Analyze the following outfit compatibility facts and explain tradeoffs. "
            "If components conflict, explain why. "
            "Return strict JSON only.\n\n"
            f"{json.dumps(facts, ensure_ascii=False)}"
        )

    def _user_prompt_fallback_text(self, facts: Dict[str, Any]) -> str:
        return (
            "Facts:\n"
            f"{json.dumps(facts, ensure_ascii=False)}\n\n"
            "Write concise stylist guidance that sounds like a real person, not a numeric report."
        )

    def _call_ollama(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool,
        max_tokens: int,
    ) -> str:
        host = self.cfg.host.rstrip("/")
        url = f"{host}/api/generate"
        options: Dict[str, Any] = {
            "temperature": float(self.cfg.temperature),
        }
        options["num_predict"] = int(max_tokens) if int(max_tokens) > 0 else _DEFAULT_NUM_PREDICT
        options["num_ctx"] = 1024
        body = {
            "model": self.cfg.model,
            "stream": False,
            "system": system_prompt,
            "prompt": user_prompt,
            "options": options,
            "keep_alive": "30m",
        }
        if json_mode:
            body["format"] = "json"
        data = json.dumps(body).encode("utf-8")
        req = urlrequest.Request(
            url=url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlrequest.urlopen(req, timeout=float(self.cfg.timeout_sec)) as resp:
            raw = resp.read().decode("utf-8")
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise RuntimeError("Unexpected Ollama response format.")
        if parsed.get("error"):
            raise RuntimeError(str(parsed.get("error")))
        return str(parsed.get("response", "")).strip()

    def _call_ollama_json(self, facts: Dict[str, Any]) -> str:
        max_tokens = int(self.cfg.max_tokens) if int(self.cfg.max_tokens) > 0 else _DEFAULT_NUM_PREDICT
        # Slightly higher cap improves chance of complete valid JSON.
        max_tokens = max(200, max_tokens)
        return self._call_ollama(
            system_prompt=self._system_prompt(),
            user_prompt=self._user_prompt(facts),
            json_mode=True,
            max_tokens=max_tokens,
        )

    def _call_ollama_text(self, facts: Dict[str, Any]) -> str:
        return self._call_ollama(
            system_prompt=self._system_prompt_fallback_text(),
            user_prompt=self._user_prompt_fallback_text(facts),
            json_mode=False,
            max_tokens=180,
        )

    def _extract_json_object(self, text: str) -> Optional[Dict[str, Any]]:
        t = str(text or "").strip()
        if not t:
            return None

        # Handle fenced payloads if model emits markdown despite JSON-only instruction.
        if t.startswith("```"):
            lines = t.splitlines()
            if len(lines) >= 3:
                t = "\n".join(lines[1:-1]).strip()

        try:
            obj = json.loads(t)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass

        dec = json.JSONDecoder()
        for i, ch in enumerate(t):
            if ch != "{":
                continue
            try:
                obj, _ = dec.raw_decode(t[i:])
            except Exception:
                continue
            if isinstance(obj, dict):
                return obj
        return None

    def _sanitize_explanation(self, obj: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(obj, dict):
            return None
        summary = str(obj.get("summary", "")).strip()
        style = str(obj.get("style_suggestion", "")).strip()
        _ = str(obj.get("disclaimer", "")).strip()

        why_raw = obj.get("why_it_works", [])
        risk_raw = obj.get("risk_points", [])
        if isinstance(why_raw, str):
            why_raw = [why_raw]
        if isinstance(risk_raw, str):
            risk_raw = [risk_raw]
        if not isinstance(why_raw, list) or not isinstance(risk_raw, list):
            return None

        def _clean_points(values: List[Any], max_items: int) -> List[str]:
            out: List[str] = []
            for v in values:
                s = str(v).strip()
                if not s:
                    continue
                if s.lower() in _EMPTY_POINT_VALUES:
                    continue
                out.append(s)
                if len(out) >= max_items:
                    break
            return out

        why = _clean_points(why_raw, max_items=4)
        risk = _clean_points(risk_raw, max_items=3)
        conf = str(obj.get("confidence_note", "medium")).strip().lower()
        if conf not in _CONFIDENCE_VALUES:
            conf = "medium"
        if not summary or not style:
            return None
        disclaimer = "Explanation only; score and label are unchanged."

        return {
            "summary": summary,
            "why_it_works": why,
            "risk_points": risk,
            "style_suggestion": style,
            "confidence_note": conf,
            "disclaimer": disclaimer,
        }

    def _parse_text_explanation(self, raw: str) -> Optional[Dict[str, Any]]:
        text = str(raw or "").strip()
        if not text:
            return None

        # Accept small format drift, but target sections are fixed.
        section_map: Dict[str, str] = {
            "summary": "",
            "why": "",
            "risk": "",
            "suggestion": "",
            "confidence": "",
        }
        current_key = ""
        for line in text.splitlines():
            row = line.strip()
            if not row:
                continue
            m = re.match(r"^(SUMMARY|WHY|RISK|SUGGESTION|CONFIDENCE)\s*:\s*(.*)$", row, flags=re.IGNORECASE)
            if m:
                key = m.group(1).lower()
                section_map[key] = m.group(2).strip()
                current_key = key
                continue
            if current_key:
                section_map[current_key] = f"{section_map[current_key]} {row}".strip()

        summary = section_map["summary"].strip()
        why_text = section_map["why"].strip()
        risk_text = section_map["risk"].strip()
        suggestion = section_map["suggestion"].strip()
        confidence = section_map["confidence"].strip().lower()

        if not summary or not suggestion:
            return None

        def _split_points(value: str, max_items: int) -> List[str]:
            raw_parts = re.split(r"(?:\s*;\s*|\s*\.\s+|\s*\|\s*)", value)
            out: List[str] = []
            for part in raw_parts:
                p = part.strip(" -\t\r\n.")
                if not p:
                    continue
                out.append(p)
                if len(out) >= max_items:
                    break
            return out

        why = _split_points(why_text, 3)
        risk = _split_points(risk_text, 2)
        if confidence not in _CONFIDENCE_VALUES:
            confidence = "medium"

        shaped = {
            "summary": summary,
            "why_it_works": why,
            "risk_points": risk,
            "style_suggestion": suggestion,
            "confidence_note": confidence,
            "disclaimer": "Explanation only; score and label are unchanged.",
        }
        return self._sanitize_explanation(shaped)

    def explain(self, facts: Dict[str, Any]) -> OllamaExplainResult:
        if not self.cfg.enabled:
            return OllamaExplainResult(status="disabled")

        normalized_facts = self._normalize_facts(facts)
        key = self._cache_key(normalized_facts)
        if self.cfg.cache_explanations:
            cached = self._read_cache(key)
            if cached is not None:
                return OllamaExplainResult(status="ok", explanation=cached, cached=True, source="ollama_cache")

        attempts = max(1, int(self.cfg.retries) + 1)
        last_error = ""
        last_raw = ""
        had_parse_issue = False
        for _ in range(attempts):
            try:
                raw = self._call_ollama_json(normalized_facts)
                last_raw = raw
            except (urlerror.URLError, urlerror.HTTPError, TimeoutError, ConnectionError, OSError) as exc:
                last_error = str(exc)
                continue
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                continue

            obj = self._extract_json_object(raw)
            if not isinstance(obj, dict):
                had_parse_issue = True
                continue
            clean = self._sanitize_explanation(obj)
            if clean is None:
                had_parse_issue = True
                continue
            if self.cfg.cache_explanations:
                self._write_cache(key, clean)
            return OllamaExplainResult(
                status="ok",
                explanation=clean,
                raw=raw,
                cached=False,
                source="ollama_json",
            )

        # One extra strict-json retry specifically for parse quality.
        if had_parse_issue and _EXTRA_PARSE_RETRY > 0:
            for _ in range(_EXTRA_PARSE_RETRY):
                try:
                    raw = self._call_ollama_json(normalized_facts)
                    last_raw = raw
                    obj = self._extract_json_object(raw)
                    if isinstance(obj, dict):
                        clean = self._sanitize_explanation(obj)
                        if clean is not None:
                            if self.cfg.cache_explanations:
                                self._write_cache(key, clean)
                            return OllamaExplainResult(
                                status="ok",
                                explanation=clean,
                                raw=raw,
                                cached=False,
                                source="ollama_json_retry",
                            )
                except (urlerror.URLError, urlerror.HTTPError, TimeoutError, ConnectionError, OSError) as exc:
                    last_error = str(exc)
                except Exception as exc:  # noqa: BLE001
                    last_error = str(exc)

        # Second pass: non-JSON stylist response, then map back to schema.
        if had_parse_issue:
            try:
                freeform_raw = self._call_ollama_text(normalized_facts)
                last_raw = freeform_raw
                clean = self._parse_text_explanation(freeform_raw)
                if clean is not None:
                    if self.cfg.cache_explanations:
                        self._write_cache(key, clean)
                    return OllamaExplainResult(
                        status="ok",
                        explanation=clean,
                        raw=freeform_raw,
                        cached=False,
                        source="ollama_text",
                    )
            except (urlerror.URLError, urlerror.HTTPError, TimeoutError, ConnectionError, OSError) as exc:
                last_error = str(exc)
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)

        if last_error:
            return OllamaExplainResult(status="unavailable", raw=last_raw, error=last_error, source="ollama_error")
        return OllamaExplainResult(status="invalid_json", raw=last_raw)
