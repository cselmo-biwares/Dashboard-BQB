"""OTEL configuration."""

import logging

from opentelemetry import trace, metrics
from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs._internal.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.trace import Span

from typing import Any

from app.config import Settings


def set_otel_config(settings: Settings):
    """
    Set up OTEL spans, metrics and logs config.

    :param settings: app settings
    :return: None
    """
    setup_spans_processing()
    setup_metrics_processing()
    setup_logging_processing()


def setup_logging_processing():
    """
    Set up OTEL logging format and exporting.

    :return: None
    """
    provider = LoggerProvider()
    provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
    set_logger_provider(provider)

    handler = LoggingHandler(logger_provider=provider)
    log_format = '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "file": "%(filename)s", "line": %(lineno)d, \
"trace_id": "%(otelTraceID)s", "span_id": "%(otelSpanID)s", "message": "%(message)s"}'
    json_formatter = logging.Formatter(fmt=log_format, datefmt="%Y-%m-%d %H:%M:%S")
    handler.setFormatter(json_formatter)
    handler.addFilter(OTelContextFilter())
    logging.getLogger().addHandler(handler)


def setup_metrics_processing():
    """
    Set up OTEL metrics exporting.

    :return: None
    """
    exporter = OTLPMetricExporter()
    reader = PeriodicExportingMetricReader(exporter)
    meter_provider = MeterProvider(metric_readers=[reader])
    metrics.set_meter_provider(meter_provider)


def setup_spans_processing():
    """
    Set up OTEL spans exporting.

    :return: None
    """
    tracer_provider = TracerProvider()
    trace_exporter = OTLPSpanExporter()
    span_processor = BatchSpanProcessor(trace_exporter)
    tracer_provider.add_span_processor(span_processor)
    trace.set_tracer_provider(tracer_provider)


def server_request_hook(span: Span, scope: dict[str, Any]):
    """
    Augment server requests spans.

    :param span: current span
    :param scope: ASGI scope
    :return: None
    """
    if span and span.is_recording():
        # TODO: implement if necessary
        pass
        # span.set_attribute("custom_user_attribute_from_request_hook", "some-value")


def client_request_hook(span: Span, scope: dict[str, Any], message: dict[str, Any]):
    """
    Augment client request spans.

    :param span: current span
    :param scope: ASGI scope
    :param message: event
    :return: None
    """
    if span and span.is_recording():
        # TODO: implement if necessary
        pass
        # span.set_attribute("custom_user_attribute_from_client_request_hook", "some-value")


def client_response_hook(span: Span, scope: dict[str, Any], message: dict[str, Any]):
    """
    Augment client response spans.

    :param span: current span
    :param scope: ASGI scope
    :param message: event
    :return: None
    """
    if span and span.is_recording():
        # TODO: implement if necessary
        pass
        # span.set_attribute("custom_user_attribute_from_response_hook", "some-value")


class OTelContextFilter(logging.Filter):
    """
    A logging filter that adds OpenTelemetry trace_id and span_id to log records.

    If no active span exists, defaults to 'N/A'.
    """

    def __init__(self, name: str = ""):
        """Initialize the filter."""
        super().__init__(name)

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Add OTEL trace_id and span_id to the log record.

        Args:
            record: The log record to filter/enrich

        Returns:
            True to allow the record to be logged
        """
        span = trace.get_current_span()

        if span and span.get_span_context().is_valid:
            span_context = span.get_span_context()
            # Format as hex strings
            record.otelTraceID = format(span_context.trace_id, "032x")
            record.otelSpanID = format(span_context.span_id, "016x")
        else:
            record.otelTraceID = "N/A"
            record.otelSpanID = "N/A"

        return True
