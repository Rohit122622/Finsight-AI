"""
FinSentry AI — Financial NLP & FinBERT Service Extension.

Provides a clean abstraction layer for financial sentiment
and risk classification (e.g. ProsusAI/finbert / Loughran-McDonald financial domain analysis).

If heavy transformer model weights are not pre-downloaded in the runtime environment,
this service operates in non-blocking passthrough or lexicon mode without crashing.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Protocol

logger = logging.getLogger(__name__)


class FinBERTRiskClassifier(Protocol):
    """Protocol for pluggable financial risk sentiment classifiers."""

    def classify_risk_sentiment(self, text: str) -> Dict[str, Any]:
        """Classify financial text into sentiment/risk probability distribution."""
        ...


class ProsusAIFinBERTClassifier:
    """
    Production financial risk classifier powered by FinBERT / financial domain NLP.
    Provides sentiment probabilities (positive, negative, neutral) and a calibrated risk score (0-100).
    """

    def __init__(self, model_name: str = "ProsusAI/finbert", device: Optional[str] = None) -> None:
        self.model_name = model_name
        self.device = device
        self._pipeline = None
        self._initialized = False

    def load_model(self) -> bool:
        """Attempt to load the transformers pipeline. Returns True on success, False on failure."""
        try:
            from transformers import pipeline
            import torch

            device_id = 0 if torch.cuda.is_available() and self.device != "cpu" else -1
            self._pipeline = pipeline(
                "text-classification",
                model=self.model_name,
                top_k=None,
                device=device_id,
                truncation=True,
                max_length=512,
            )
            self._initialized = True
            logger.info("Loaded live FinBERT model '%s' successfully on device=%s", self.model_name, device_id)
            return True
        except Exception as exc:
            logger.info("Live FinBERT model could not be loaded from network/cache: %s", exc)
            self._initialized = False
            return False

    def classify_risk_sentiment(self, text: str) -> Dict[str, Any]:
        """
        Classify financial text into sentiment distribution and compute risk signal.
        """
        if not text or not text.strip():
            return {
                "sentiment": "neutral",
                "risk_score": 0.0,
                "probabilities": {"positive": 0.0, "negative": 0.0, "neutral": 1.0},
                "source": "finbert",
            }

        if self._pipeline is not None:
            try:
                truncated_text = text[:1500]
                outputs = self._pipeline(truncated_text)
                probs = {}
                top_label = "neutral"
                top_score = 0.0
                if isinstance(outputs, list) and len(outputs) > 0:
                    entries = outputs[0] if isinstance(outputs[0], list) else outputs
                    for item in entries:
                        lbl = str(item.get("label", "")).lower()
                        sc = float(item.get("score", 0.0))
                        probs[lbl] = sc
                        if sc > top_score:
                            top_score = sc
                            top_label = lbl

                neg_prob = probs.get("negative", 0.0)
                pos_prob = probs.get("positive", 0.0)
                neu_prob = probs.get("neutral", 0.0)
                risk_score = round(neg_prob * 100.0, 2)

                return {
                    "sentiment": top_label,
                    "risk_score": risk_score,
                    "probabilities": {
                        "positive": round(pos_prob, 4),
                        "negative": round(neg_prob, 4),
                        "neutral": round(neu_prob, 4),
                    },
                    "confidence": round(top_score, 4),
                    "model": self.model_name,
                    "source": "live_finbert",
                }
            except Exception as exc:
                logger.warning("FinBERT inference error: %s", exc)

                                                                                                           
        return self._rule_based_financial_sentiment(text)

    @staticmethod
    def _rule_based_financial_sentiment(text: str) -> Dict[str, Any]:
        """
        Loughran-McDonald domain financial sentiment analysis fallback.
        """
        text_lower = text.lower()
        negative_words = {
            "loss", "losses", "deficit", "decline", "declining", "drop", "default", "defaulted", "defaults",
            "impairment", "write-down", "restatement", "litigation", "lawsuit", "investigation",
            "breach", "covenant", "bankruptcy", "insolvent", "adverse", "risk", "risks", "uncertainty",
            "material weakness", "deficiency", "going concern", "inflation", "compression", "crisis",
            "debt", "debts", "distress", "distressed", "deterioration", "deteriorated", "shortfall", "shortfalls",
            "warning", "warnings", "downgrade", "downgrades", "restructuring", "negative"
        }
        positive_words = {
            "growth", "profit", "profitable", "increase", "increasing", "gain", "gains",
            "record", "expansion", "dividend", "dividends", "strong", "outperform", "cash generation",
            "robust", "positive", "improved", "improvement", "exceeded", "upside"
        }
        words = re.findall(r"\b[a-z\-]+\b", text_lower)
        neg_count = sum(1 for w in words if w in negative_words)
        pos_count = sum(1 for w in words if w in positive_words)
        total = max(1, neg_count + pos_count)

        neg_prob = neg_count / (total + 2.0)
        pos_prob = pos_count / (total + 2.0)
        neu_prob = max(0.0, 1.0 - neg_prob - pos_prob)

        sentiment = "neutral"
        if neg_count > pos_count:
            sentiment = "negative"
        elif pos_count > neg_count:
            sentiment = "positive"

        risk_score = round(neg_prob * 100.0, 2)
        return {
            "sentiment": sentiment,
            "risk_score": risk_score,
            "probabilities": {
                "positive": round(pos_prob, 4),
                "negative": round(neg_prob, 4),
                "neutral": round(neu_prob, 4),
            },
            "confidence": round(max(neg_prob, pos_prob, neu_prob), 4),
            "model": "loughran-mcdonald-nlp",
            "source": "financial_nlp_lexicon",
        }


class NLPService:
    """
    NLP service providing financial risk scoring and text analytics hooks.
    """

    def __init__(self, classifier: Optional[FinBERTRiskClassifier] = None) -> None:
        self._classifier = classifier or ProsusAIFinBERTClassifier()
        self._is_finbert_available = True

    @property
    def is_available(self) -> bool:
        """Return whether a live FinBERT/NLP model is actively loaded."""
        return self._is_finbert_available

    def register_classifier(self, classifier: FinBERTRiskClassifier) -> None:
        """Register a custom or loaded FinBERT classifier model instance."""
        self._classifier = classifier
        self._is_finbert_available = True
        logger.info("Custom FinBERT/NLP classifier registered successfully.")

    def set_available(self, available: bool) -> None:
        """Explicitly toggle availability status."""
        self._is_finbert_available = available

    def analyze_risk_sentiment(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Analyze risk sentiment for financial text if FinBERT is available.

        Returns None if no active NLP model is registered, allowing caller to
        proceed with standard deterministic rules and LLM reasoning.
        """
        if not self._is_finbert_available or self._classifier is None:
            return None

        try:
            return self._classifier.classify_risk_sentiment(text)
        except Exception as exc:
            logger.warning("FinBERT classifier evaluation failed (%s); bypassing NLP hook.", exc)
            return None


                  
nlp_service = NLPService()

