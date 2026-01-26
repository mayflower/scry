"""OpenTelemetry instrumentation for Scry MCP server.

This module initializes OpenTelemetry tracing and exports traces to Grafana Tempo
via gRPC OTLP. FastMCP uses Starlette internally, so we instrument that.
"""

import logging
import os

logger = logging.getLogger(__name__)

# Configuration from environment
OTEL_ENABLED = os.getenv("OTEL_ENABLED", "false").lower() == "true"
OTEL_SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "maistack-scry")
OTEL_EXPORTER_OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")


def init_telemetry() -> None:
    """Initialize OpenTelemetry tracing if enabled.

    Sets up:
    - TracerProvider with gRPC OTLP exporter to Tempo
    - Auto-instrumentation for Starlette (used by FastMCP internally)
    """
    if not OTEL_ENABLED:
        logger.info("OpenTelemetry tracing disabled (OTEL_ENABLED=false)")
        return

    if not OTEL_EXPORTER_OTLP_ENDPOINT:
        logger.warning(
            "OTEL_ENABLED=true but OTEL_EXPORTER_OTLP_ENDPOINT not set. "
            "Skipping OpenTelemetry initialization."
        )
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.instrumentation.starlette import StarletteInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.semconv.resource import ResourceAttributes

        # Create resource with service identification
        resource = Resource.create(
            {
                ResourceAttributes.SERVICE_NAME: OTEL_SERVICE_NAME,
                ResourceAttributes.DEPLOYMENT_ENVIRONMENT: os.getenv("ENVIRONMENT", "development"),
                ResourceAttributes.SERVICE_VERSION: os.getenv("APP_VERSION", "unknown"),
            }
        )

        # Create tracer provider with OTLP gRPC exporter
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(
            endpoint=OTEL_EXPORTER_OTLP_ENDPOINT,
            insecure=True,  # Within cluster, TLS not needed
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        # Auto-instrument Starlette (FastMCP uses Starlette internally)
        StarletteInstrumentor().instrument()
        logger.info("Starlette instrumented with OpenTelemetry")

        logger.info(
            f"OpenTelemetry initialized: service={OTEL_SERVICE_NAME}, "
            f"endpoint={OTEL_EXPORTER_OTLP_ENDPOINT}"
        )

    except ImportError as e:
        logger.error(
            f"OpenTelemetry packages not installed: {e}. "
            "Install with: pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc"
        )
    except Exception as e:
        logger.error(f"Failed to initialize OpenTelemetry: {e}")


def shutdown_telemetry() -> None:
    """Shutdown OpenTelemetry tracer provider gracefully."""
    if not OTEL_ENABLED:
        return

    try:
        from opentelemetry import trace

        provider = trace.get_tracer_provider()
        if hasattr(provider, "shutdown"):
            provider.shutdown()
            logger.info("OpenTelemetry tracer provider shut down")
    except Exception as e:
        logger.warning(f"Error shutting down OpenTelemetry: {e}")
