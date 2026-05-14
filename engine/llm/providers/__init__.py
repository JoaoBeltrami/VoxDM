"""
Providers de LLM — abstração comum para múltiplos backends.

Exporta a interface base e os providers registrados no router.
"""

from engine.llm.providers.base import BaseLLMProvider, LLMRetriable

__all__ = ["BaseLLMProvider", "LLMRetriable"]
