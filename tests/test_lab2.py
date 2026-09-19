"""Contract tests for remote requests, lineage and checkpoint integrity (no cloud calls)."""
import importlib
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from cloudlayer.gcp import GcpAdapter
from src.config import Config
from src.tune import grid, SEARCH_SPACE, save_checkpoint


@pytest.fixture
def adapter():
    return GcpAdapter(Config('gcp', 'test-project', 'test-region', 'object://bucket/prefix',
                            'registry', 'https://tracking.example', 'model', 'trainer@example'))


def test_grid_varies_three_parameters():
    configurations = grid(SEARCH_SPACE)
    assert len(configurations) == 12
    assert len({tuple(p.items()) for p in configurations}) == 12
    assert all(len({p[k] for p in configurations}) > 1 for k in SEARCH_SPACE)


def test_checkpoint_atomic_replace(tmp_path):
    path = tmp_path / 'state.json'
    save_checkpoint(path, {'completed': [1]})
    save_checkpoint(path, {'completed': [1, 2]})
    assert json.loads(path.read_text())['completed'] == [1, 2]
    assert not path.with_suffix('.tmp').exists()


def test_submit_valid_spot_protobuf(adapter):
    types = importlib.import_module('google.cloud.aiplatform_v1.types')
    client = Mock()
    client.create_custom_job.return_value = SimpleNamespace(name='projects/p/locations/r/customJobs/1')
    adapter._client = Mock(return_value=client)
    adapter._blob = Mock()
    result = adapter.submit_training('registry/image@sha256:' + 'a' * 64, {
        'env': {'GIT_COMMIT': 'b' * 40}, 'instance': 'n1-standard-4', 'command_args': ['--trials', '36'],
        'study': 'study', 'timeout_s': 3600})
    request = types.CustomJob(client.create_custom_job.call_args.kwargs['custom_job'])
    assert request.job_spec.scheduling.strategy == types.Scheduling.Strategy.SPOT
    assert request.job_spec.service_account == 'trainer@example'
    assert request.job_spec.worker_pool_specs[0].container_spec.command == ['python', '-m', 'src.tune']
    assert result.endswith('/customJobs/1')
    adapter._blob.return_value.upload_from_string.assert_called_once()


def test_reject_mutable_training_image(adapter):
    with pytest.raises(ValueError, match='digest-pinned'):
        adapter.submit_training('image:latest', {})


def test_wait_propagates_failure(adapter):
    types = importlib.import_module('google.cloud.aiplatform_v1.types')
    client = Mock()
    client.get_custom_job.return_value = types.CustomJob(name='job', state=types.JobState.JOB_STATE_FAILED,
                                                       error={'message': 'permission denied'})
    adapter._client = Mock(return_value=client)
    with pytest.raises(RuntimeError, match='permission denied'):
        adapter.wait_training('job')


def test_version_must_be_immutable(adapter):
    with pytest.raises(ValueError, match='immutable'):
        adapter.model_metadata('projects/p/locations/r/models/1@staging')


def test_missing_lineage_blocks_registration(adapter):
    adapter._blob = Mock()
    adapter._blob.return_value.download_as_text.return_value = '{}'
    with pytest.raises(ValueError, match='Missing required lineage'):
        adapter.register_model('object://model', 'test')
