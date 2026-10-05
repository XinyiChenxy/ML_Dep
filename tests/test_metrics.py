from service import metrics


def test_prometheus_metrics_cover_required_service_signals():
    metrics.observe_request(200, 42.0)
    metrics.observe_request(422, 8.0)
    metrics.observe_request(500, 120.0)
    metrics.observe_features([{"temp_c": 70.0}, {"temp_c": 80.0}])
    output = metrics.render_prometheus("test-4")
    assert 'http_requests_total{status_class="2xx"}' in output
    assert 'http_requests_total{status_class="4xx"}' in output
    assert 'http_requests_total{status_class="5xx"}' in output
    assert 'request_latency_ms_bucket{le="500"}' in output
    assert 'feature_rolling_mean{feature="temp_c"} 75.00000000' in output
    assert 'model_version_info{version="test-4"} 1' in output
