"""
hsb/metrics.py
Recolector de métricas operacionales del HSB.
Expone contadores por estado, latencia media, duplicados y tasa de fallos.
"""

import time
from typing import Dict, Any, List
from collections import deque


class MetricsCollector:
    def __init__(self):
        self.total_recibidos = 0
        self.total_entregados = 0
        self.total_rechazados = 0
        self.total_duplicados = 0
        self.total_reintentos = 0
        self.total_muertos = 0
        self.latencias: deque = deque(maxlen=500)  # Últimas 500 mediciones en ms
        self.timestamps_mensajes: deque = deque(maxlen=1000)

    def registrar_recibido(self):
        self.total_recibidos += 1
        self.timestamps_mensajes.append(time.time())

    def registrar_entregado(self, latencia_ms: float):
        self.total_entregados += 1
        self.latencias.append(latencia_ms)

    def registrar_rechazado(self):
        self.total_rechazados += 1

    def registrar_duplicado(self):
        self.total_duplicados += 1

    def registrar_reintento(self):
        self.total_reintentos += 1

    def registrar_muerto(self):
        self.total_muertos += 1

    def obtener_metricas(self) -> Dict[str, Any]:
        ahora = time.time()
        # Mensajes en el último minuto (60 segundos)
        mensajes_ultimo_minuto = sum(1 for ts in self.timestamps_mensajes if ahora - ts <= 60.0)

        latencia_media = (sum(self.latencias) / len(self.latencias)) if self.latencias else 0.0

        total_procesados = self.total_entregados + self.total_rechazados + self.total_muertos
        pct_fallidos = (
            ((self.total_rechazados + self.total_muertos) / total_procesados * 100.0)
            if total_procesados > 0 else 0.0
        )

        return {
            "total_recibidos": self.total_recibidos,
            "total_entregados": self.total_entregados,
            "total_rechazados": self.total_rechazados,
            "total_duplicados_detectados": self.total_duplicados,
            "total_reintentos_ejecutados": self.total_reintentos,
            "total_mensajes_muertos": self.total_muertos,
            "mensajes_ultimo_minuto": mensajes_ultimo_minuto,
            "latencia_media_ms": round(latencia_media, 2),
            "porcentaje_fallidos": round(pct_fallidos, 2),
            "estado_general": "SALUDABLE" if self.total_muertos == 0 else "CON_MENSAJES_MUERTOS"
        }


metrics = MetricsCollector()

