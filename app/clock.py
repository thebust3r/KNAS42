"""Local time for KNAS.

The container's system clock is in UTC and the small Linux image has no time zone database,
so local time comes from TZ (if the system knows it) or else from the weather service, which
reports your UTC offset (and follows daylight saving time) with every forecast."""
import datetime, os, time


def local_now():
    try:
        from zoneinfo import ZoneInfo
        tz = os.environ.get("TZ", "").strip()
        if tz and tz != "auto":
            return datetime.datetime.now(ZoneInfo(tz)).replace(tzinfo=None)
    except Exception:
        pass
    off = os.environ.get("KNAS_UTC_OFFSET")
    if off:
        try:
            return (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=int(float(off)))).replace(tzinfo=None)
        except ValueError:
            pass
    return datetime.datetime.now()


def local_today():
    return local_now().date()


def local_ts(ts):
    """A file's timestamp as local date/time."""
    return local_now() - datetime.timedelta(seconds=time.time() - ts)


def offset():
    """Seconds your local time is ahead of UTC right now."""
    d = local_now() - datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    return int(round(d.total_seconds() / 60.0)) * 60


def local_dt(ts):
    """A Unix timestamp as your local date/time (the container's own clock is UTC)."""
    return datetime.datetime.fromtimestamp(ts + offset(), datetime.timezone.utc).replace(tzinfo=None)


def local_midnight_ts(year, month=1, day=1):
    """The Unix timestamp of local midnight on that date."""
    return datetime.datetime(year, month, day, tzinfo=datetime.timezone.utc).timestamp() - offset()
