"""Lab 5 — compile pipeline/pipeline.yaml into your provider's pipeline service.

This module is Layer 3, so provider SDKs are allowed here and nowhere else. The DAG stays
in YAML; only the translation lives here. That separation is what you argue for or against
in Lab 5 Task 4.

Implement ONE compile function, for your provider.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

SPEC = Path(__file__).resolve().parents[1] / "pipeline" / "pipeline.yaml"


def load_spec(path: Path = SPEC) -> dict[str, Any]:
    """Read the neutral DAG and expand ${VAR} references from the environment."""
    raw = path.read_text()
    for key, value in os.environ.items():
        raw = raw.replace(f"${{{key}}}", value)
    return yaml.safe_load(raw)


def compile_aws(spec: dict[str, Any]):
    """SageMaker Pipelines.

    Each step becomes a ProcessingStep or TrainingStep; `condition` becomes a
    ConditionStep. Note that SageMaker's condition steps branch rather than abort, so
    `on_failure: abort` needs a FailStep on the else branch — an asymmetry worth
    mentioning in your Lab 5 write-up.
    """
    raise NotImplementedError("Only the selected GCP provider is compiled for this submission")


def compile_azure(spec: dict[str, Any]):
    """Azure ML Pipelines.

    Each step becomes a command component; the DAG is expressed as a @pipeline function.
    Conditions use azure.ai.ml.dsl.condition, which is closer to this YAML than the other
    two providers' equivalents.
    """
    raise NotImplementedError("Only the selected GCP provider is compiled for this submission")


def _expanded(value: str, name: str) -> str:
    """Reject unresolved image placeholders before creating a costly cloud run."""
    if not value or "${" in value:
        raise ValueError(f"{name} is unresolved; set it in cloud.env before compiling")
    return value


def compile_gcp(spec: dict[str, Any]):
    """Vertex AI Pipelines.

    Kubeflow Pipelines underneath: steps become container components, conditions become
    dsl.If blocks. The compiled artifact is a JSON file you submit, so your build step
    produces a file rather than an object — different from the other two.
    """
    try:
        from kfp import compiler, dsl
    except ImportError as exc:
        raise RuntimeError("KFP is required: install the locked requirements first") from exc

    from src import config

    cfg = config.load()
    steps = {step["name"]: step for step in spec["steps"]}
    required = {"ingest", "validate", "train", "evaluate", "register", "deploy_staging"}
    missing = sorted(required - steps.keys())
    if missing:
        raise ValueError(f"pipeline spec is missing steps: {', '.join(missing)}")

    image = _expanded(steps["ingest"]["image"], "TRAINING_IMAGE_URI")
    if any(_expanded(step["image"], "TRAINING_IMAGE_URI") != image for step in steps.values()):
        raise ValueError("all Lab 5 steps must use the same immutable training image")
    if "@sha256:" not in image:
        raise ValueError("TRAINING_IMAGE_URI must be digest-pinned, not tag-pinned")

    env = {
        "CLOUD_PROVIDER": cfg.provider,
        "PROJECT_ID": cfg.project_id,
        "REGION": cfg.region,
        "BLOB_URI": cfg.blob_uri,
        "CONTAINER_REGISTRY": cfg.container_registry,
        "MLFLOW_TRACKING_URI": cfg.mlflow_tracking_uri,
        "MODEL_REGISTRY_NAME": cfg.model_registry_name,
        "IDENTITY_REF": cfg.identity_ref,
        "TRAINING_IMAGE_URI": cfg.training_image_uri,
        "SERVING_IMAGE_URI": cfg.serving_image_uri,
        "SERVING_SERVICE_ACCOUNT": cfg.serving_service_account,
    }

    def component_for(step: dict[str, Any]):
        def component():
            return dsl.ContainerSpec(image=step["image"], command=step["command"])

        component.__name__ = f"lab5_{step['name']}"
        return dsl.container_component(component)

    def gate_component_for(step: dict[str, Any]):
        def component(decision):
            return dsl.ContainerSpec(
                image=step["image"],
                command=[*step["command"], "--decision-out", decision],
            )

        component.__name__ = "lab5_evaluation_gate"
        component.__annotations__ = {"decision": dsl.OutputPath(str)}
        return dsl.container_component(component)

    components = {
        name: component_for(step)
        for name, step in steps.items()
        if name != "evaluate"
    }
    evaluate_component = gate_component_for(steps["evaluate"])

    def configured(task):
        for key, value in env.items():
            if value:
                task.set_env_variable(key, str(value))
        return task

    @dsl.pipeline(name=spec["name"], pipeline_root=f"{cfg.blob_uri.rstrip('/')}/lab5/pipeline-root")
    def training_pipeline():
        ingest = configured(components["ingest"]())
        validate = configured(components["validate"]()).after(ingest)
        train = configured(components["train"]()).after(validate)
        evaluate = configured(evaluate_component()).after(train)
        with dsl.If(evaluate.output == "pass", name="candidate-passed-evaluation"):
            register = configured(components["register"]()).after(evaluate)
            configured(components["deploy_staging"]()).after(register)

    output = Path("pipeline/lab5-pipeline.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    compiler.Compiler().compile(training_pipeline, package_path=str(output))
    print(f"compiled {output}")
    return output


COMPILERS = {"aws": compile_aws, "azure": compile_azure, "gcp": compile_gcp}


def compile_for(provider: str, spec: dict[str, Any] | None = None):
    spec = spec or load_spec()
    try:
        return COMPILERS[provider.lower()](spec)
    except KeyError:
        raise ValueError(f"No pipeline compiler for {provider!r}") from None
