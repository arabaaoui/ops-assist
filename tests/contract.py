"""Contract every ObservationSource must honour: replay today, real connectors later.

A test module for a source subclasses ``ObservationContract`` and provides two
fixtures: ``source`` (the source under test) and ``sample``: a ``service`` with logs
and changes, a ``metric`` of that service, a ``foreign_metric`` that exists for
another service only, and an ``unknown_metric``. Nothing here depends on one incident.
"""

import pytest

from ops_assist.observability import MAX_LOG_LINES, ObservationError


class ObservationContract:
    def test_it_has_a_name(self, source):
        assert isinstance(source.name, str) and source.name

    @pytest.fixture(autouse=True)
    def require_capability(self, request, source):
        name = request.node.name
        capability = (
            "alerts"
            if "alerts" in name
            else "metric"
            if "metric" in name
            else "logs"
            if any(x in name for x in ("logs", "limited", "level"))
            else "changes"
            if "changes" in name
            else None
        )
        if capability and capability not in source.capabilities:
            pytest.skip(f"source declares {capability} unsupported")

    def test_alerts_carry_service_severity_and_source(self, source):
        for a in source.alerts():
            assert {"id", "name", "service", "severity", "since", "source"} <= a.keys()

    def test_a_metric_series_has_a_unit_points_and_a_source(self, source, sample):
        s = source.metric(sample["metric"], sample["service"])
        assert {"name", "service", "unit", "points", "source"} <= s.keys()
        assert s["service"] == sample["service"] and all(len(p) == 2 for p in s["points"])

    def test_a_metric_of_another_service_is_not_returned(self, source, sample):
        with pytest.raises(ObservationError):
            source.metric(sample["foreign_metric"], sample["service"])

    def test_an_unknown_metric_raises_observation_error(self, source, sample):
        with pytest.raises(ObservationError):
            source.metric(sample["unknown_metric"], sample["service"])

    def test_logs_belong_to_the_service_and_are_cited(self, source, sample):
        lines = source.logs(sample["service"], limit=MAX_LOG_LINES)
        assert lines and all(x["service"] == sample["service"] and x["source"] for x in lines)

    def test_a_limited_read_returns_the_newest_lines_first(self, source, sample):
        everything = source.logs(sample["service"], limit=MAX_LOG_LINES)
        newest = source.logs(sample["service"], limit=3)
        assert [x["ts"] for x in newest] == [x["ts"] for x in everything[:3]]
        assert [x["ts"] for x in everything] == sorted((x["ts"] for x in everything), reverse=True)

    def test_logs_for_a_known_silent_service_are_empty(self, source, sample):
        assert source.logs(sample["silent_service"]) == []

    def test_a_level_filter_keeps_only_that_level(self, source, sample):
        for level in {x["level"] for x in source.logs(sample["service"], limit=MAX_LOG_LINES)}:
            assert all(x["level"] == level for x in source.logs(sample["service"], level=level))

    def test_bad_arguments_are_refused_not_answered_empty(self, source, sample):
        calls = []
        if "logs" in source.capabilities:
            calls += [
                lambda: source.logs("no-such-service"),
                lambda: source.logs(sample["service"], level="LOUD"),
                lambda: source.logs(sample["service"], limit=0),
            ]
        if "changes" in source.capabilities:
            calls.append(lambda: source.changes("no-such-service"))
        for call in calls:
            with pytest.raises(ObservationError):
                call()

    def test_changes_belong_to_the_service_newest_first_and_cited(self, source, sample):
        changes = source.changes(sample["service"])
        assert all(c["service"] == sample["service"] and c["source"] for c in changes)
        assert [c["ts"] for c in changes] == sorted((c["ts"] for c in changes), reverse=True)
