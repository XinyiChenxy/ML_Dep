# Lab 2：GCP 实作与从零开始指南

目前尚未开通 GCP。代码提供本地演练和 GCP 路径；本地结果不能代替课程要求的云端证据。原实验题目保留在 `course/labs/lab-02-tracking-and-registry.md`。

## 现在即可运行

在项目根目录执行（Python 3.12）：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-gcp.txt
bash scripts/lab2_local.sh
```

脚本会生成数据，运行三次后以退出码 75 模拟受控中断，再从 checkpoint 完成 36 次训练，生成比较报告、注册到本地 MLflow、设置 staging alias，并按注册版本重新加载模型预测五行。真实 Spot 抢占尚待 GCP 验证。再次运行会跳过已完成训练，但会创建新的本地注册版本。

结果位置：

- `reports/lab2-comparison.md`：全部实验、种子方差、≤200 词选择理由。
- `reports/lab2-interruption.log` 和 `reports/lab2-resume.log`：真实本地中断/续跑日志。
- `reports/lab2-registration.json`、`reports/lab2-reload.json`：注册版本与预测。
- `reports/tune_checkpoint.json`：断点、估算费用与完整运行 ID。

模型的三个参数为树数量、最大深度、叶节点最少样本数。12 个配置分别运行三个 seed。数据按机器分组，始终使用固定 split seed，避免把数据切分差异误称为模型种子方差。先按验证均值筛选距最好配置不超过 0.005 AUC 的配置，再选实测平均耗时最短的配置；测试集不参与选择。云端会重新生成比较，不能直接照搬本地耗时排名。

## 1. 开通账号

打开 [Google Cloud 注册入口](https://cloud.google.com/free)，用自己的 Google 账号完成身份与账单验证，创建一个专门用于课程的项目。Project ID 与项目显示名称不同，后续用 Project ID。试用资格和资源限制以 [官方免费计划说明](https://docs.cloud.google.com/free/docs/free-cloud-features) 为准。

在 Billing → Budgets & alerts 为课程项目设置相当于 150 THB 的提醒。提醒不是硬性消费上限。不要把赠送额度误记为实验实际资源成本。

本实验使用 CPU，不需要 GPU。地区示例为 `asia-southeast1`，实际需确认该区 Vertex 的配额和 Spot 容量。

## 2. 初始化 GCP 资源

可以先使用 Google Cloud Console 的 Cloud Shell（自带 gcloud），或按 [官方安装说明](https://cloud.google.com/sdk/docs/install) 安装本地 CLI。本地执行 SDK 时需要 Application Default Credentials：

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
```

下面命令会创建收费资源的存储容器；替换变量后执行。仓库、bucket 和服务账号在一次实验后保留供 Lab 3 使用。

```bash
export LAB2_PROJECT=YOUR_PROJECT_ID
export LAB2_REGION=asia-southeast1
export LAB2_BUCKET=YOUR_GLOBALLY_UNIQUE_BUCKET
export LAB2_SA=lab2-trainer@${LAB2_PROJECT}.iam.gserviceaccount.com

gcloud services enable aiplatform.googleapis.com artifactregistry.googleapis.com storage.googleapis.com --project "$LAB2_PROJECT"
gcloud storage buckets create "gs://$LAB2_BUCKET" --project "$LAB2_PROJECT" --location "$LAB2_REGION" --uniform-bucket-level-access
gcloud artifacts repositories create itcs355 --project "$LAB2_PROJECT" --location "$LAB2_REGION" --repository-format docker
gcloud iam service-accounts create lab2-trainer --project "$LAB2_PROJECT"
gcloud storage buckets add-iam-policy-binding "gs://$LAB2_BUCKET" --member "serviceAccount:$LAB2_SA" --role roles/storage.objectUser
```

提交者需要 Vertex 作业/模型权限、存储对象读写和 Artifact Registry 写权限，并且需要训练服务账号上的 `iam.serviceAccounts.actAs`（通常通过 `roles/iam.serviceAccountUser`）。不要把运行身份与提交身份混淆。跨项目镜像还需额外授权 Vertex 服务代理读取 Artifact Registry。若遇到权限错误，保存原错误、调用者、缺失 permission 与修复方式到 `reports/lab2-permissions.md`，不能预先编造错误。

## 3. MLflow 与配置

云端训练需要能从 Vertex 容器访问的 MLflow 服务。本地 `sqlite:///mlflow.db` 不可直接共享给云端。优先使用学校提供的 HTTPS MLflow；否则需自行部署一个有持久化数据库、artifact storage 和访问控制的 MLflow 服务，费用也计入 150 THB。此仓库不会假装已经部署了这个服务。若学校服务需要登录，需把其认证配置通过云端秘密注入方式传给训练，当前脚本不自动复制本机认证变量。

```bash
cp cloud.gcp.env.example cloud.env
```

填入真实项目、bucket、镜像仓库、训练服务账号、MLflow 地址。`SERVING_IMAGE_URI` 可使用下面构建的同一 GCP 镜像摘要；该镜像包含 `cloudlayer.serve`，因此训练与重载使用相同 sklearn/joblib 依赖。不要填 Azure 参数。

## 4. 数据与不可变镜像

```bash
source .venv/bin/activate
make data
pip install 'dvc[gs]'
dvc add data/raw/sensors.csv
# 检查并提交自己的代码和 data/raw/sensors.csv.dvc；不要提交 cloud.env。
# git add ... && git commit ...
make image-gcp
python -c 'from src import config; from cloudlayer.factory import get_adapter; print(get_adapter(config.load()).push_image("itcs355-lab1:YOUR_GIT_SHORT_SHA"))'
```

记录返回的完整 `...@sha256:...`。数据按 DVC MD5 写入版本化 GCS 路径，提交前检查文件与 `.dvc` 中 hash 一致。远程提交拒绝脏工作区，防止提交 SHA 与运行代码不一致。需要自己确认推送的镜像确由该次 commit 构建。

## 5. 价格、训练、断点恢复

参考 [Vertex 训练 Spot 配置](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/training/use-spot-vms?hl=en) 与 [Spot 价格](https://cloud.google.com/spot-vms/pricing)。运行当天核对所选区域 Vertex 自定义训练的 CPU、内存及管理费用，按当时 USD/THB 汇率换算；记录价格页面、地区、日期、汇率来源。仓库原 `src/costs.py` 数值仅是旧示例，不能当作核实过的价格。

```bash
make cloud-check
make train-remote REMOTE_ARGS='--image YOUR_IMAGE@sha256:YOUR_DIGEST --study lab2-gcp-001 --hourly-thb YOUR_VERIFIED_RATE --pricing-source YOUR_PRICING_URL --timeout-s 3600'
```

一个 Vertex CustomJob 使用一台 `n1-standard-4` Spot 节点，执行完整 study。timeout × 小时费率上限为 120 THB，另外预留 30 THB；实际账单仍受启动、失败重试、存储和 MLflow 服务费用影响，代码不能保证账单绝不超预算。每个 trial 先预留五分钟费用，超过五分钟会中断；恢复时未结算 trial 按完整预留计费，以免把中断工作算成零。每个已完成 trial 的模型和断点写入 GCS。重跑同一个 study 可以跳过已完成项，最多重新训练当前 trial。请勿同时提交同名 study。

云端 checkpoint 会覆盖本地 `reports/tune_checkpoint.json`，先备份本地演练结果。若作业被平台终止而未自动恢复，重新提交相同 study；应使用相同镜像、数据、费率和参数。保留 Cloud Logging 中的中断和恢复记录，受控退出不能声称证明了真实 Spot 抢占。

## 6. 注册、晋级、重载、清理

```bash
make compare
make register
make reload-check
make cost-report
make teardown LAB=2
```

GCP 注册保存八个完整 lineage 字段到版本的 `version_description` JSON 中，避免 SHA 被 GCP label 长度限制截断。返回 `projects/.../models/ID@VERSION`；先设 candidate，再晋级 staging。重载先按不可变版本查询 Vertex，取得模型 GCS URI，然后下载模型及该版本数据，对固定测试集的五行预测。无须部署收费 Endpoint。

真实组织中，staging 晋级应由模型负责人和独立 ML 平台/发布审核人授权，不能任由训练身份自我批准；应审查验证与测试指标、种子稳定性、泄漏检查、预算、完整 lineage、相同环境的重载证据和回滚版本。本实验脚本自动执行 staging 以展示流程，生产环境应把该权限拆开。

`teardown` 仅取消并删除带本项目课程标签和 `lab=2` 的 CustomJobs，不删除注册模型、训练数据或模型 artifact。若自行部署了 MLflow/VM，还需停掉其计算资源，并从 Billing 导出实际费用，区分每 trial 估计、作业总费用和项目总费用。实验最终清单的云端项目只能在获得真实证据后勾选。
