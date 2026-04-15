"""
test_resilience.py — Unit tests para CircuitBreaker y retry_with_backoff.
No hace llamadas HTTP reales — todo es lógica pura de estados.
"""
import time
import pytest
from unittest.mock import MagicMock, patch

from resilience import (
    CircuitBreaker, CircuitBreakerOpenError, CBState,
    retry_with_backoff,
)


# ===========================================================================
# CircuitBreaker — transiciones de estado
# ===========================================================================
class TestCircuitBreakerStates:

    def _cb(self, threshold=3, recovery=0.05, success_threshold=2):
        """CB con parámetros pequeños para tests rápidos."""
        return CircuitBreaker(
            name="test",
            failure_threshold=threshold,
            recovery_timeout=recovery,
            success_threshold=success_threshold,
        )

    # --- Estado inicial ---
    def test_initial_state_is_closed(self):
        cb = self._cb()
        assert cb.state == CBState.CLOSED

    # --- CLOSED → OPEN ---
    def test_opens_after_failure_threshold(self):
        cb = self._cb(threshold=3)
        for _ in range(3):
            with pytest.raises(RuntimeError):
                with cb:
                    raise RuntimeError("fallo")
        assert cb.state == CBState.OPEN

    def test_does_not_open_before_threshold(self):
        cb = self._cb(threshold=3)
        for _ in range(2):
            with pytest.raises(RuntimeError):
                with cb:
                    raise RuntimeError("fallo")
        assert cb.state == CBState.CLOSED

    # --- OPEN rechaza peticiones inmediatamente ---
    def test_open_raises_circuit_breaker_error(self):
        cb = self._cb(threshold=1)
        with pytest.raises(RuntimeError):
            with cb:
                raise RuntimeError("fallo")
        assert cb.state == CBState.OPEN

        with pytest.raises(CircuitBreakerOpenError):
            with cb:
                pass  # No debe llegar aquí

    def test_open_error_includes_retry_after(self):
        cb = self._cb(threshold=1, recovery=60.0)
        with pytest.raises(RuntimeError):
            with cb:
                raise RuntimeError("x")
        with pytest.raises(CircuitBreakerOpenError) as exc_info:
            with cb:
                pass
        assert exc_info.value.retry_after > 0

    # --- OPEN → HALF_OPEN (después del timeout) ---
    def test_transitions_to_half_open_after_timeout(self):
        cb = self._cb(threshold=1, recovery=0.05)
        with pytest.raises(RuntimeError):
            with cb:
                raise RuntimeError("x")
        assert cb.state == CBState.OPEN

        time.sleep(0.1)   # Esperar recovery_timeout

        # La siguiente llamada debe pasar (HALF_OPEN) y si tiene éxito...
        with cb:
            pass
        # Con success_threshold=2, todavía no cierra tras 1 éxito
        assert cb.state in (CBState.HALF_OPEN, CBState.CLOSED)

    # --- HALF_OPEN → CLOSED (éxitos suficientes) ---
    def test_closes_after_success_threshold_in_half_open(self):
        cb = self._cb(threshold=1, recovery=0.05, success_threshold=2)
        with pytest.raises(RuntimeError):
            with cb:
                raise RuntimeError("x")
        time.sleep(0.1)
        with cb:
            pass
        assert cb.state == CBState.HALF_OPEN
        with cb:
            pass
        assert cb.state == CBState.CLOSED

    # --- HALF_OPEN → OPEN (fallo en prueba) ---
    def test_reopens_on_failure_in_half_open(self):
        cb = self._cb(threshold=1, recovery=0.05, success_threshold=2)
        with pytest.raises(RuntimeError):
            with cb:
                raise RuntimeError("x")
        time.sleep(0.1)
        with pytest.raises(RuntimeError):
            with cb:
                raise RuntimeError("fallo en half-open")
        assert cb.state == CBState.OPEN

    # --- Éxito en CLOSED resetea contador ---
    def test_success_resets_failure_count(self):
        cb = self._cb(threshold=3)
        # 2 fallos
        for _ in range(2):
            with pytest.raises(RuntimeError):
                with cb:
                    raise RuntimeError("x")
        assert cb.failure_count == 2

        # 1 éxito → reset
        with cb:
            pass
        assert cb.failure_count == 0
        assert cb.state == CBState.CLOSED

    # --- status() devuelve info correcta ---
    def test_status_closed(self):
        cb = self._cb()
        s = cb.status()
        assert s["state"] == "CLOSED"
        assert "retry_in_seconds" not in s

    def test_status_open_includes_retry(self):
        cb = self._cb(threshold=1, recovery=60.0)
        with pytest.raises(RuntimeError):
            with cb:
                raise RuntimeError("x")
        s = cb.status()
        assert s["state"] == "OPEN"
        assert s["retry_in_seconds"] > 0


# ===========================================================================
# retry_with_backoff
# ===========================================================================
class TestRetryWithBackoff:

    def test_returns_on_first_success(self):
        calls = []

        @retry_with_backoff(max_attempts=3, base_delay=0.01)
        def fn():
            calls.append(1)
            return "ok"

        result = fn()
        assert result == "ok"
        assert len(calls) == 1

    def test_retries_on_failure_then_succeeds(self):
        attempt_counter = {"n": 0}

        @retry_with_backoff(max_attempts=3, base_delay=0.01)
        def fn():
            attempt_counter["n"] += 1
            if attempt_counter["n"] < 3:
                raise ConnectionError("timeout")
            return "recovered"

        result = fn()
        assert result == "recovered"
        assert attempt_counter["n"] == 3

    def test_raises_after_max_attempts(self):
        @retry_with_backoff(max_attempts=3, base_delay=0.01)
        def fn():
            raise ConnectionError("siempre falla")

        with pytest.raises(ConnectionError):
            fn()

    def test_does_not_retry_on_circuit_breaker_open(self):
        calls = []

        @retry_with_backoff(max_attempts=5, base_delay=0.01)
        def fn():
            calls.append(1)
            raise CircuitBreakerOpenError("test", 60.0)

        with pytest.raises(CircuitBreakerOpenError):
            fn()

        assert len(calls) == 1, "No debe reintentar si el CB está abierto"

    def test_respects_max_attempts(self):
        calls = []

        @retry_with_backoff(max_attempts=4, base_delay=0.01)
        def fn():
            calls.append(1)
            raise ValueError("x")

        with pytest.raises(ValueError):
            fn()

        assert len(calls) == 4
