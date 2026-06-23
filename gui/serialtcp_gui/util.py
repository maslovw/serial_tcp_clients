"""Small formatting helpers and a throughput meter for the GUI."""


def format_duration(seconds):
    s = int(max(0, seconds))
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return '{:02d}:{:02d}:{:02d}'.format(h, m, s)


def format_bytes(n):
    """Return ``(value, unit)`` for a stat tile, e.g. ``('142', 'KB')``."""
    n = float(n)
    if n < 1024:
        return ('{:.0f}'.format(n), 'B')
    for unit in ('KB', 'MB', 'GB'):
        n /= 1024.0
        if n < 1024 or unit == 'GB':
            value = '{:.1f}'.format(n) if n < 10 else '{:.0f}'.format(n)
            return (value, unit)
    return ('{:.0f}'.format(n), 'GB')


def format_rate(bytes_per_sec):
    """Return a compact rate string, e.g. ``4.2 KB/s`` (or an em dash)."""
    if bytes_per_sec is None or bytes_per_sec <= 0:
        return '—'
    bps = float(bytes_per_sec)
    if bps < 1024:
        return '{:.0f} B/s'.format(bps)
    kb = bps / 1024.0
    if kb < 1024:
        fmt = '{:.1f} KB/s' if kb < 10 else '{:.0f} KB/s'
        return fmt.format(kb)
    mb = kb / 1024.0
    fmt = '{:.1f} MB/s' if mb < 10 else '{:.0f} MB/s'
    return fmt.format(mb)


class RateMeter:
    """Derives a bytes/second rate from successive cumulative samples."""

    def __init__(self):
        self._prev_total = None
        self._prev_time = None

    def sample(self, total, now):
        rate = 0.0
        if self._prev_total is not None and now > self._prev_time:
            dt = now - self._prev_time
            rate = max(0.0, (total - self._prev_total) / dt)
        self._prev_total = total
        self._prev_time = now
        return rate
