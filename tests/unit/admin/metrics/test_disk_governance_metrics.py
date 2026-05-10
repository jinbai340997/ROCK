from rock.admin.metrics.constants import MetricsConstants


class TestDiskGovernanceConstants:
    """Lock down the metric names — they're referenced by Grafana
    dashboards and Sunfire alert rules. Renaming silently breaks ops.
    """

    def test_metric_names(self):
        assert MetricsConstants.SANDBOX_LOG_ARCHIVE_TOTAL == "sandbox.log.archive.total"
        assert MetricsConstants.SANDBOX_LOG_ARCHIVE_SUCCESS == "sandbox.log.archive.success"
        assert MetricsConstants.SANDBOX_LOG_ARCHIVE_FAILURE == "sandbox.log.archive.failure"
        assert MetricsConstants.SANDBOX_LOG_ARCHIVE_SIZE == "sandbox.log.archive.size_bytes"


class TestRegisterDiskGovernanceMetrics:
    """Verify that PR-1's _register_metrics block actually registers
    the 4 new metrics on a real MetricsMonitor."""

    def test_all_four_metrics_registered(self):
        """Construct MetricsMonitor (will hit _should_skip in test env
        and return early), then manually drive _register_metrics with a
        spy on _register_counter / _register_gauge."""
        from rock.admin.metrics.monitor import MetricsMonitor

        monitor = MetricsMonitor.__new__(MetricsMonitor)
        registered_counters = []
        registered_gauges = []
        monitor._register_counter = lambda name, desc, unit="1": (registered_counters.append((name, desc, unit)))
        monitor._register_gauge = lambda name, desc, unit="1": (registered_gauges.append((name, desc, unit)))
        monitor._register_metrics()

        all_counter_names = {c[0] for c in registered_counters}
        all_gauge_names = {g[0] for g in registered_gauges}

        # PR-1 additions
        assert MetricsConstants.SANDBOX_LOG_ARCHIVE_TOTAL in all_counter_names
        assert MetricsConstants.SANDBOX_LOG_ARCHIVE_SUCCESS in all_counter_names
        assert MetricsConstants.SANDBOX_LOG_ARCHIVE_FAILURE in all_counter_names
        assert MetricsConstants.SANDBOX_LOG_ARCHIVE_SIZE in all_gauge_names

        # Regression: existing metrics must still be there
        assert MetricsConstants.SANDBOX_REQUEST_TOTAL in all_counter_names
        assert MetricsConstants.SANDBOX_DISK in all_gauge_names
        assert MetricsConstants.METASTORE_DB_RT in all_gauge_names

    def test_size_metric_unit_is_byte(self):
        """The size gauge must declare unit='byte' for OTel/Prom interpretation."""
        from rock.admin.metrics.monitor import MetricsMonitor

        monitor = MetricsMonitor.__new__(MetricsMonitor)
        recorded = []
        monitor._register_counter = lambda *a, **kw: None
        monitor._register_gauge = lambda name, desc, unit="1": (recorded.append((name, unit)))
        monitor._register_metrics()
        size_entry = next(
            (e for e in recorded if e[0] == MetricsConstants.SANDBOX_LOG_ARCHIVE_SIZE),
            None,
        )
        assert size_entry is not None
        assert size_entry[1] == "byte"
