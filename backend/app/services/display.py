"""Waveshare 2.13" e-Paper V4 display service (SSD1680, 122x250).

Renders a live status screen and pushes it to the display over SPI.
The driver is self-contained; GPIO/SPI imports are deferred so the module
can be imported safely on machines without hardware (they'll raise ImportError
only when EPD() is instantiated).
"""
from __future__ import annotations

import time
from typing import Optional


# ── hardware constants ──────────────────────────────────────────────────────
PIN_RST  = 17
PIN_DC   = 25
PIN_BUSY = 24
# PIN_CS = 8 (SPI0_CE0) is controlled by the SPI kernel driver — do not claim it via GPIO

WIDTH     = 122    # pixels across (short axis)
HEIGHT    = 250    # pixels down   (long axis)
ROW_BYTES = 16     # ceil(122/8) — last 6 bits of each row unused


# ── low-level driver ────────────────────────────────────────────────────────
class EPD:
    """Minimal SSD1680 driver for the Waveshare 2.13" V4 HAT."""

    def __init__(self):
        import spidev
        import RPi.GPIO as GPIO
        self._GPIO = GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(PIN_RST,  GPIO.OUT)
        GPIO.setup(PIN_DC,   GPIO.OUT)
        # PIN_CS (GPIO 8) is SPI0_CE0 — owned by the kernel SPI driver.
        # spidev asserts/deasserts CS automatically around each xfer2() call,
        # so we must not claim it via GPIO or lgpio will refuse.
        GPIO.setup(PIN_BUSY, GPIO.IN)
        self.spi = spidev.SpiDev()
        self.spi.open(0, 0)
        self.spi.max_speed_hz = 4_000_000
        self.spi.mode = 0

    # ── SPI primitives ──────────────────────────────────────────────────────
    def _cmd(self, c: int) -> None:
        self._GPIO.output(PIN_DC, 0)
        self.spi.xfer2([c])

    def _dat(self, d) -> None:
        self._GPIO.output(PIN_DC, 1)
        self.spi.xfer2(d if isinstance(d, list) else [d])

    def _busy(self, timeout: float = 10.0) -> None:
        t = time.monotonic()
        while self._GPIO.input(PIN_BUSY) == 1:
            if time.monotonic() - t > timeout:
                raise TimeoutError("EPD BUSY timeout")
            time.sleep(0.01)

    def _reset(self) -> None:
        G = self._GPIO
        G.output(PIN_RST, 1); time.sleep(0.1)
        G.output(PIN_RST, 0); time.sleep(0.02)
        G.output(PIN_RST, 1); time.sleep(0.1)

    def _set_cursor(self, x: int, y: int) -> None:
        self._cmd(0x4E); self._dat(x & 0xFF)
        self._cmd(0x4F); self._dat([y & 0xFF, (y >> 8) & 0x01])

    def _refresh(self) -> None:
        self._cmd(0x22); self._dat(0xF7)
        self._cmd(0x20)
        self._busy(15)

    # ── lifecycle ───────────────────────────────────────────────────────────
    def init(self) -> None:
        self._reset()
        self._busy()
        self._cmd(0x12)              # software reset — mandatory for V4
        self._busy()

        self._cmd(0x01)              # driver output control (249 gates)
        self._dat([0xF9, 0x00, 0x00])

        self._cmd(0x11)              # data entry: X inc, Y inc
        self._dat(0x03)

        self._cmd(0x44)              # RAM X window: bytes 0..15
        self._dat([0x00, 0x0F])
        self._cmd(0x45)              # RAM Y window: rows 0..249
        self._dat([0x00, 0x00, 0xF9, 0x00])

        self._cmd(0x3C)              # border waveform
        self._dat(0x05)

        self._cmd(0x21)              # display update control
        self._dat([0x00, 0x80])

        self._cmd(0x18)              # use internal temperature sensor
        self._dat(0x80)

        self._set_cursor(0, 0)
        self._busy()

    def sleep(self) -> None:
        self._cmd(0x10); self._dat(0x01)
        time.sleep(0.1)

    def close(self) -> None:
        self.spi.close()
        self._GPIO.cleanup()

    # ── drawing ─────────────────────────────────────────────────────────────
    def fill(self, color: int = 0xFF) -> None:
        """Flood-fill: 0xFF = white, 0x00 = black."""
        self._set_cursor(0, 0)
        self._cmd(0x24)
        self._dat([color] * (ROW_BYTES * HEIGHT))
        self._refresh()

    def show(self, image) -> None:
        """Push a Pillow image to the display.

        The image must be (WIDTH, HEIGHT) = (122, 250). If it arrives as
        (250, 122) (landscape) it is rotated automatically.
        """
        img = image.convert("1")
        if img.size == (HEIGHT, WIDTH):
            img = img.rotate(90, expand=True)
        if img.size != (WIDTH, HEIGHT):
            img = img.resize((WIDTH, HEIGHT))

        buf = [0xFF] * (ROW_BYTES * HEIGHT)
        px = img.load()
        for y in range(HEIGHT):
            for x in range(WIDTH):
                if px[x, y] == 0:
                    buf[y * ROW_BYTES + x // 8] &= ~(0x80 >> (x % 8))

        self._set_cursor(0, 0)
        self._cmd(0x24)
        self._dat(buf)
        self._refresh()


# ── status data helpers ─────────────────────────────────────────────────────
def _battery() -> tuple[Optional[int], Optional[float]]:
    """Read PiSugar3 battery % and voltage from I2C (address 0x57, bus 1)."""
    try:
        import smbus2
        bus = smbus2.SMBus(1)
        pct_raw = bus.read_byte_data(0x57, 0x2A)
        pct = min(100, max(0, pct_raw))
        msb = bus.read_byte_data(0x57, 0x22)
        lsb = bus.read_byte_data(0x57, 0x23)
        raw = ((msb & 0x3F) << 8) | lsb
        volts = round(raw * 0.001372, 2)   # ~1.372 mV per LSB
        bus.close()
        return pct, volts
    except Exception:
        return None, None


def _lte_present() -> bool:
    """True if the SIM7600 ttyUSB ports are visible."""
    from pathlib import Path
    return any(Path(f"/dev/ttyUSB{i}").exists() for i in range(5))


def _gps_line() -> str:
    """Return a short GPS status string (max ~12 chars to fit the display)."""
    from pathlib import Path
    import serial
    dev = Path("/dev/ttyUSB1")
    if not dev.exists():
        return "No device"
    try:
        with serial.Serial(str(dev), 115200, timeout=2) as s:
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                line = s.readline().decode(errors="ignore").strip()
                if line.startswith("$GNGGA") or line.startswith("$GPGGA"):
                    parts = line.split(",")
                    if len(parts) > 6 and parts[2] and parts[6] != "0":
                        # Trim DDMM.MMMM → DD.MM to keep it short
                        def _short(deg_str: str, hemi: str) -> str:
                            return deg_str[:6] + hemi if deg_str else "?"
                        lat = _short(parts[2], parts[3])
                        lon = _short(parts[4], parts[5])
                        return f"{lat} {lon}"
                    return "Searching"
    except Exception:
        pass
    return "No fix"


# ── render ──────────────────────────────────────────────────────────────────
def render_status() -> "PIL.Image.Image":
    """Build and return a 122×250 status image with live router data."""
    from PIL import Image, ImageDraw

    # Collect data (best-effort — never crash the render)
    try:
        from .network import upstream_status, ap_status
        up = upstream_status()
        ap = ap_status()
        ssid     = up.get("ssid") or "—"
        up_status = up.get("status", "—")
        devices  = ap.get("clients", 0)
        ap_ip    = ap.get("ip") or "10.0.0.1"
    except Exception:
        ssid = up_status = "—"; devices = 0; ap_ip = "10.0.0.1"

    try:
        from .system import cpu_temp_c
        temp = cpu_temp_c()
        temp_str = f"{temp}°C" if temp is not None else "—"
    except Exception:
        temp_str = "—"

    batt_pct, batt_v = _battery()
    batt_str = f"{batt_pct}%  {batt_v}V" if batt_pct is not None else "—"

    lte_str = "SIM7600G-H" if _lte_present() else "Not found"
    gps_str = _gps_line()

    def _clip(s: str, n: int = 13) -> str:
        return s if len(s) <= n else s[:n - 1] + "…"

    img = Image.new("1", (WIDTH, HEIGHT), 255)
    d   = ImageDraw.Draw(img)

    # Header bar
    d.rectangle([0, 0, WIDTH - 1, 15], fill=0)
    d.text((3, 2), "SandOS  Roku-E8C3", fill=255)

    # Body rows — values clipped to ~13 chars to stay on-screen
    rows = [
        ("Batt", batt_str),
        ("Temp", temp_str),
        ("LTE",  _clip(lte_str)),
        ("GPS",  _clip(gps_str)),
        ("", ""),
        ("WiFi", _clip(ssid)),
        ("Up",   up_status),
        ("AP",   ap_ip),
        ("Dev",  str(devices)),
    ]
    y = 22
    for label, value in rows:
        if not label and not value:
            d.line([2, y, WIDTH - 3, y], fill=0)
            y += 6
            continue
        d.text((3,  y), f"{label}:", fill=0)
        d.text((38, y), value,       fill=0)
        y += 13

    # Border
    d.rectangle([0, 0, WIDTH - 1, HEIGHT - 1], outline=0)

    return img


# ── entry point for stand-alone refresh ────────────────────────────────────
def update_display() -> None:
    """Initialise the e-paper, push a fresh status screen, then sleep it."""
    epd = EPD()
    try:
        epd.init()
        img = render_status()
        epd.show(img)
    finally:
        try:
            epd.sleep()
        except Exception:
            pass
        try:
            epd.close()
        except Exception:
            pass


if __name__ == "__main__":
    update_display()
