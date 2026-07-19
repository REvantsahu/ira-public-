"""IRA Clap Detector — audio clap detection for voice activation."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable

import numpy as np


@dataclass
class ClapEvent:
    timestamp: float
    energy: float
    confidence: float


class ClapDetector:
    """Detects claps via microphone audio energy analysis."""

    def __init__(self, on_clap: Callable[[ClapEvent], None] | None = None):
        self.on_clap = on_clap
        self._running = False
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

        # Config
        self.sample_rate = 16000
        self.chunk_size = 1024
        self.energy_threshold = 0.08  # Minimum energy to consider
        self.clap_cooldown = 1.5  # Seconds between claps
        self.window_size = 5  # Number of chunks to analyze
        self.spike_ratio = 3.0  # Energy spike ratio to detect clap

        # State
        self._last_clap_time = 0
        self._energy_buffer = []
        self.is_active = False
        self._clap_count = 0

    def start(self):
        """Start clap detection in background thread."""
        if self._running:
            return
        self._running = True
        self.is_active = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="clap-detector")
        self._thread.start()
        print("[Clap] Detector started")

    def stop(self):
        """Stop clap detection."""
        self._running = False
        self.is_active = False
        if self._thread:
            self._thread.join(timeout=2.0)
        print("[Clap] Detector stopped")

    def _loop(self):
        """Main audio monitoring loop."""
        try:
            import pyaudio
        except ImportError:
            print("[Clap] PyAudio not available")
            self._running = False
            return

        pa = pyaudio.PyAudio()
        try:
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.chunk_size,
            )
        except Exception as e:
            print(f"[Clap] Could not open microphone: {e}")
            pa.terminate()
            self._running = False
            return

        print("[Clap] Listening for claps...")
        try:
            while self._running:
                try:
                    data = stream.read(self.chunk_size, exception_on_overflow=False)
                except Exception:
                    continue

                # Convert to numpy array
                audio = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0

                # Calculate RMS energy
                energy = float(np.sqrt(np.mean(audio ** 2)))

                # Store energy in buffer
                self._energy_buffer.append(energy)
                if len(self._energy_buffer) > self.window_size * 3:
                    self._energy_buffer = self._energy_buffer[-self.window_size * 3:]

                # Detect clap: sudden energy spike
                now = time.time()
                if len(self._energy_buffer) >= self.window_size:
                    recent_avg = np.mean(self._energy_buffer[-self.window_size:])
                    prev_avg = np.mean(self._energy_buffer[-self.window_size * 2:-self.window_size]) if len(self._energy_buffer) >= self.window_size * 2 else recent_avg

                    # Clap criteria:
                    # 1. Energy spike: recent energy >> previous energy
                    # 2. Energy above threshold
                    # 3. Cooldown expired
                    spike = recent_avg / max(prev_avg, 0.001)
                    cooldown_ok = (now - self._last_clap_time) >= self.clap_cooldown

                    if (spike >= self.spike_ratio and
                        recent_avg >= self.energy_threshold and
                        cooldown_ok):

                        self._last_clap_time = now
                        self._clap_count += 1

                        # Confidence based on spike strength
                        confidence = min(1.0, spike / (self.spike_ratio * 2))

                        event = ClapEvent(
                            timestamp=now,
                            energy=recent_avg,
                            confidence=confidence,
                        )

                        print(f"[Clap] Detected! (#{self._clap_count}, energy={energy:.4f}, spike={spike:.1f}x)")

                        if self.on_clap:
                            try:
                                self.on_clap(event)
                            except Exception as e:
                                print(f"[Clap] Callback error: {e}")

                # Throttle
                time.sleep(0.02)

        except Exception as e:
            if self._running:
                print(f"[Clap] Error: {e}")
        finally:
            stream.stop_stream()
            stream.close()
            pa.terminate()

    def get_status(self) -> dict:
        """Get detector status."""
        return {
            "running": self._running,
            "clap_count": self._clap_count,
            "last_clap": self._last_clap_time,
            "energy_threshold": self.energy_threshold,
        }

    def set_threshold(self, threshold: float):
        """Adjust clap sensitivity."""
        self.energy_threshold = max(0.01, min(0.5, threshold))

    def set_cooldown(self, seconds: float):
        """Set cooldown between claps."""
        self.clap_cooldown = max(0.5, seconds)


# ── Singleton ──────────────────────────────────────────────

_detector: ClapDetector | None = None


def get_detector() -> ClapDetector:
    """Get or create the global clap detector."""
    global _detector
    if _detector is None:
        _detector = ClapDetector()
    return _detector
