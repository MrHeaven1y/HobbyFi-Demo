"""
This module Configures and return [when called get_logger()] a structured logging for the application
and exposes a helper to get a logger.
setup_logging() sets a standard library logger (format, level, stream) and then configures structlog
with a pipeline of processors and factories so logs are emitted either as pretty console 
output in development or as JSON in non-development environments.

"""

import logging
import sys
import structlog
from app.core.config import settings

def setup_logging():
    """
    Configures structlog for JSON output in non development and
    pretty-printed console output in development.
    """
    log_level = logging.DEBUG if settings.DEBUG else logging.INFO # This control which log records are emitted

    # minimal format (message only), sends output to stdout and applies the chosen level. It ensures code using logging have a baseline config
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    # list of callables that transform the event dict and final output. This builds a base list and then appends either a pretty console renderer or a JSON renderer.
    processors = [
        structlog.contextvars.merge_contextvars, # merges context variables (like request_id, user_id) stored in contextvars into event dict so contextual data travels with log events
        structlog.processors.add_log_level, # adds log levels (e.g info, error) into the event dict
        structlog.processors.StackInfoRenderer(), # this renders the stack information into the event when stack info was requested
        structlog.dev.set_exc_info, # ensures the exception info is attached to event when exception is logged
    ]

    if settings.APP_ENV == "development":
        processors.append(structlog.dev.ConsoleRenderer(colors=True)) # pretty o/p for local development
    else:
        processors.append(structlog.processors.JSONRenderer()) # emits machine‑friendly JSON suitable for log aggregation

    structlog.configure(
        processors=processors, # each processors receives (logger, method_name, event_dict) and returns a modified event / final string
        wrapper_class=structlog.make_filtering_bound_logger(log_level), # provide methods to api for attaching context to loggers. returns a wrapper that filters out event below log_level
        context_class=dict, # dict type to hold bound context
        logger_factory=structlog.PrintLoggerFactory(), # creates logger objects that ultimately call print() with the final rendered string. 
        cache_logger_on_first_use=True, # When True, structlog caches created logger instances for performance so subsequent get_logger() calls are faster.
    )

def get_logger(name: str = __name__):
    """Returns a structured logger instance."""

    return structlog.get_logger(name)
