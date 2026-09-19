"""Register the selected model, then promote to staging."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mlflow
from mlflow.tracking import MlflowClient
from cloudlayer.factory import get_adapter
from src import config


def main():
    cfg = config.load(strict=False)
    selection = json.loads(Path('reports/lab2-selection.json').read_text())
    if cfg.provider == 'local':
        mlflow.set_tracking_uri(cfg.mlflow_tracking_uri)
        lineage = json.loads((Path(selection['artifact_uri']) / 'lineage.json').read_text())
        registered = mlflow.register_model(selection['mlflow_model_uri'], cfg.model_registry_name)
        client = MlflowClient()
        for key, value in lineage.items():
            client.set_model_version_tag(cfg.model_registry_name, registered.version, key, str(value))
        client.set_registered_model_alias(cfg.model_registry_name, 'staging', registered.version)
        version = registered.version
    else:
        if selection['execution'] != 'cloud-spot':
            raise ValueError('Cannot submit a local rehearsal model as cloud evidence')
        adapter = get_adapter(cfg)
        version = adapter.register_model(selection['artifact_uri'], cfg.model_registry_name)
        adapter.promote(version)
    record = {'provider': cfg.provider, 'name': cfg.model_registry_name, 'version': version}
    Path('reports/lab2-registration.json').write_text(json.dumps(record, indent=2))
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    main()
