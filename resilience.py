"""
resilience.py — Circuit Breaker + Retry con backoff exponencial
===============================================================
Diseñado para entornos industriales donde el servicio externo (SmartRack API)
puede caer sin aviso. Evita fallos en cascada y da tiempo al servicio de recuperarse.

USO:
    from resilience import CircuitBreaker, retry_with_backoff

    cb = CircuitBreaker(name="SmartRack", failure_threshold=5, recovery_timeout=60)

    @retry_with_backoff(max_attempts=3, base_delay=2.0)
    def my_call():
        with cb:
            return requests.get(...)
"""

from __future__ import annotations

import time
import random
import threading
import functools
from enum import Enum
from typing import Callable, Any

from logger_setup import setup_logger

logger = setup_logger("Resilience")


# ---------------------------------------------------------------------------
# Estados del Circuit Breaker
# ---------------------------------------------------------------------------
class CBState(str, Enum):
    CLOSED    = "CLOSED"     # Normal — peticiones pasan
    OPEN      = "OPEN"       # Fallo — peticiones rechazadas inmediatamente
    HALF_OPEN = "HALF_OPEN"  # Prueba — se permite UNA petición para evaluar


class CircuitBreakerOpenError(Exception):
    """Lanzada cuando el circuito está ABIERTO y se rechaza la petición."""
    def __init__(self, name: str, retry_after: float):
        self.name        = name
        self.retry_after = retry_after
        super().__init__(
            f"Circuit breaker '{name}' ABIERTO. "
            f"Reintento disponible en {retry_after:.1f}s"
        )


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------
class CircuitBreaker:
    """
    Thread-safe Circuit Breaker con tres estados: CLOSED → OPEN → HALF_OPEN → CLOSED.

    Params:
        name               Identificador para logs
        failure_threshold  Fallos consecutivos para abrir el circuito (default 5)
        recovery_timeout   Segundos en OPEN antes de pasar a HALF_OPEN (default 60)
        success_threshold  Éxitos consecutivos en HALF_OPEN para cerrar (default 2)
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int  = 5,
        recovery_timeout:  float = 60.0,
        success_threshold: int  = 2,
    ):
        self.name              = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout  = recovery_timeout
        self.success_threshold = success_threshold

        self._state            = CBState.CLOSED
        self._failure_count    = 0
        self._success_count    = 0
        self._opened_at: float = 0.0
        self._lock             = threading.Lock()

    # ------------------------------------------------------------------
    # Propiedades públicas (lectura segura)
    # ------------------------------------------------------------------
    @property
    def state(self) -> CBState:
        with self._lock:
            return self._state

    @property
    def failure_count(self) -> int:
        with self._lock:
            return self._failure_count

    # ------------------------------------------------------------------
    # Context manager — uso con `with cb:`
    # ------------------------------------------------------------------
    def __enter__(self) -> "CircuitBreaker":
        with self._lock:
            if self._state == CBState.OPEN:
                elapsed      = time.monotonic() - self._opened_at
                retry_after  = max(0.0, self.recovery_timeout - elapsed)
                if elapsed < self.recovery_timeout:
                    raise CircuitBreakerOpenError(self.name, retry_after)
                # Tiempo cumplido → probar con HALF_OPEN
                self._transition(CBState.HALF_OPEN)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if exc_type is None:
            self._on_success()
        elif not issubclass(exc_type, CircuitBreakerOpenError):
            self._on_failure()
        return False  # No suprimir excepciones

    # ------------------------------------------------------------------
    # Transiciones internas
    # ------------------------------------------------------------------
    def _on_success(self) -> None:
        with self._lock:
            if self._state == CBState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self._transition(CBState.CLOSED)
            elif self._state == CBState.CLOSED:
                self._failure_count = 0  # Resetear contador en éxito

    def _on_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            if self._state == CBState.HALF_OPEN:
                # Fallo en prueba → volver a OPEN
                self._transition(CBState.OPEN)
            elif (self._state == CBState.CLOSED
                  and self._failure_count >= self.failure_threshold):
                self._transition(CBState.OPEN)

    def _transition(self, new_state: CBState) -> None:
        """Efectúa la transición y loggea el cambio (ya dentro del lock)."""
        old_state = self._state
        self._state = new_state

        if new_state == CBState.OPEN:
            self._opened_at     = time.monotonic()
            self._success_count = 0
            logger.warning(
                f"CIRCUIT BREAKER [{self.name}] {old_state} → OPEN "
                f"({self._failure_count} fallos). "
                f"Reintento en {self.recovery_timeout}s"
            )
        elif new_state == CBState.HALF_OPEN:
            self._success_count = 0
            logger.info(
                f"CIRCUIT BREAKER [{self.name}] OPEN → HALF_OPEN "
                f"— probando recuperación..."
            )
        elif new_state == CBState.CLOSED:
            self._failure_count = 0
            self._success_count = 0
            logger.info(
                f"CIRCUIT BREAKER [{self.name}] HALF_OPEN → CLOSED "
                f"— servicio recuperado ✓"
            )

    # ------------------------------------------------------------------
    # Estado para monitoreo
    # ------------------------------------------------------------------
    def status(self) -> dict:
        with self._lock:
            info: dict[str, Any] = {
                "name":           self.name,
                "state":          self._state.value,
                "failure_count":  self._failure_count,
            }
            if self._state == CBState.OPEN:
                elapsed = time.monotonic() - self._opened_at
                info["retry_in_seconds"] = max(0.0, round(self.recovery_timeout - elapsed, 1))
            return info


# ---------------------------------------------------------------------------
# Decorador: retry con backoff exponencial + jitter
# ---------------------------------------------------------------------------
def retry_with_backoff(
    max_attempts: int   = 3,
    base_delay:   float = 1.0,
    max_delay:    float = 30.0,
    backoff:      float = 2.0,
    jitter:       float = 0.3,
    reraise_on:   tuple = (CircuitBreakerOpenError,),
) -> Callable:
    """
    Decorador que reintenta la función con backoff exponencial y jitter aleatorio.

    Params:
        max_attempts  Intentos totales (1 = sin reintentos)
        base_delay    Espera base en segundos entre intentos
        max_delay     Techo de espera (nunca superar este valor)
        backoff       Factor multiplicador (2.0 = duplicar por intento)
        jitter        Fracción aleatoria del delay para evitar thundering herd
        reraise_on    Excepciones que se re-lanzan SIN reintentar
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc: Exception | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except reraise_on as e:
                    # Circuito abierto u error no reintentable → propagar de inmediato
                    raise
                except Exception as e:
                    last_exc = e
                    if attempt == max_attempts:
                        break
                    delay = min(base_delay * (backoff ** (attempt - 1)), max_delay)
                    delay += random.uniform(0, jitter * delay)  # jitter
                    logger.warning(
                        f"[{func.__name__}] Intento {attempt}/{max_attempts} fallido: {e}. "
                        f"Reintentando en {delay:.2f}s..."
                    )
                    time.sleep(delay)
            logger.error(
                f"[{func.__name__}] Todos los {max_attempts} intentos agotados. "
                f"Último error: {last_exc}"
            )
            raise last_exc
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Instancias globales — una por servicio externo
# ---------------------------------------------------------------------------
# SmartRack API (login + polling + extracción)
smartrack_cb = CircuitBreaker(
    name="SmartRack-API",
    failure_threshold=5,    # 5 fallos consecutivos abren el circuito
    recovery_timeout=60.0,  # 60s en OPEN antes de probar recuperación
    success_threshold=2,    # 2 éxitos en HALF_OPEN para cerrar
)
