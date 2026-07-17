class DatastoreUnavailableError(Exception):
    """Raised when Redis or MongoDB cannot be reached within the configured timeout.

    Mapped to a 503 response by app.main's exception handler - Redis/MongoDB are this
    service's own required dependencies (not an optional downstream call it can degrade
    around), so a clear 503 lets the caller decide how *it* wants to degrade instead of
    this service hanging or raising an unhandled error.
    """
