from __future__ import annotations
import json
import math
import os
from typing import Dict

try:
    from src.config import AI_MODEL_PATH as _AI_PATH
except Exception:
    _AI_PATH = os.path.join("data", "ai_model.json")

class SimpleMetaScorer:
    """
    Scorer ligero (IA) que combina features normalizadas en un score [-1,1] con pesos ajustables.
    Persiste pesos en JSON para refinarlos en el tiempo (stub para aprendizaje online futuro).
    """
    def __init__(self):
        self.model_path = _AI_PATH
        self.weights = {
            "mom": 1.2,           # momentum EMA9-EMA21 normalizado
            "rsi_centered": 0.8,  # RSI centrado (rsi-50)/50
            "vwap_dev": 0.7,      # desvío a VWAP (en ATRs)
            "atr_regime": -0.4,   # penaliza volatilidad excesiva
            "micro_trend": 0.9,   # pendiente corta de precio
        }
        self.bias = 0.0
        self._load()

    def _load(self):
        try:
            os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
            if os.path.exists(self.model_path):
                with open(self.model_path, "r") as f:
                    data = json.load(f)
                self.weights.update(data.get("weights", {}))
                self.bias = float(data.get("bias", 0.0))
        except Exception:
            pass

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
            with open(self.model_path, "w") as f:
                json.dump({"weights": self.weights, "bias": self.bias}, f)
        except Exception:
            pass

    @staticmethod
    def _tanh(x: float) -> float:
        return math.tanh(x)

    def score(self, feats: Dict[str, float]) -> float:
        z = self.bias
        for k, w in self.weights.items():
            z += w * float(feats.get(k, 0.0))
        return self._tanh(z)

    def update(self, feats: Dict[str, float], outcome: float, lr: float = 0.001):
        # Stub para futuras mejoras online.
        return

scorer = SimpleMetaScorer()