# industry_cv

面向多个工业现场长期复用的机器视觉工具库。提供 Python API、JSON/JSONL 命令行接口、AI 技能和现场知识；通过 Python 包或 Git 子模块引入现场总仓库。机器人运动、设备互锁和整体流程由上层项目组织。

当前可用能力：RTSP 采集、纽扣电池检测与稳定跟踪、平面标定及尺寸估计。LR41 是第一个已验证案例，核心检测支持均匀光和侧光；[案例记录](knowledge/cases/2026-11-26-button-battery/README.md)保存适用条件、失败样例及实测结果。

## 安装与调用

Python 3.10+，CPU 即可；当前运行依赖为 NumPy 和 OpenCV，不依赖 ROS 或机器人 SDK。

```bash
python -m pip install -e .
# 开发环境增加测试、检查、构建工具：python -m pip install -e '.[dev]'

# 预设随 wheel 发布，无需源码目录也可列出/导出。
industry-cv profiles
industry-cv profiles button_battery/default --output /path/to/site/vision.json
```

```python
from industry_cv import BatteryDetector, DetectorConfig, load_profile

settings = load_profile('button_battery/default')
# settings['roi'] / settings['image_size'] 由当前现场提供。
detector = BatteryDetector(DetectorConfig(**settings))
detections = detector.detect(bgr_image)  # uint8 BGR / 灰度图
```

顶层 API 还提供 `Frame`、`CameraConfig`、`RTSPCamera`、`PlanarCalibration`、`ButtonBatteryPipeline`。旧名 `VisionPipeline` 保留为兼容别名。跨语言项目可以消费 `industry-cv stream` 输出的 JSONL，见[接入与协议](docs/guides/integration.md)。

## 仓库导航

| 路径 | 用途 |
|---|---|
| [src/industry_cv](src/industry_cv) | 按采集、检测、几何、管线分层的运行代码 |
| [profiles](src/industry_cv/profiles) | 随包发布的通用参数和物料规格，不含现场地址/ROI |
| [examples/button_battery](examples/button_battery/README.md) | 可直接运行的 LR41 示例、示例 ROI 和上层消费代码 |
| [skills](skills/README.md) | AI 使用入口及能力索引 |
| [knowledge](knowledge/README.md) | 现场案例、实验依据和知识回流 |
| [docs/architecture.md](docs/architecture.md) | 职责、依赖方向和配置边界 |
| [tests](tests) | 单元、集成、真实场景回归及最小数据集 |

完整目录和扩展方法见[架构说明](docs/architecture.md)，版本变更见 [CHANGELOG](CHANGELOG.md)。库运行不依赖仓库 cwd；站点配置由参数提供，通用预设由安装包资源读取。

## 运行首个现场示例

在仓库根目录执行以下离线命令即可检查真实画面，不需要相机：

```bash
industry-cv detect tests/data/button_battery/button_cells_side_light.jpg \
  --config examples/button_battery/configs/vision.json \
  --part-profile parts/lr41 \
  --output artifacts/result.json --annotated artifacts/result.jpg
```

实时运行、环境变量及默认值替换见 [LR41 示例](examples/button_battery/README.md)。该示例可先用名义尺寸输出明确标注的估计坐标；没有提供标定/物料尺寸时保留像素定位。实际机器人坐标的测量和验收见[标定指南](docs/guides/calibration.md)。

## 作为子模块维护

```bash
# 在现场总仓库执行，并提交生成的子模块指针。
git submodule add https://github.com/yizhongzhang1989/industry_cv.git third_party/industry_cv
python -m pip install -e ./third_party/industry_cv
```

现场地址、凭据、ROI、实际标定、工具参数和生产记录由总仓库维护。通用改进经最小回归样例和知识记录回流本库，现场项目验证后再升级固定的子模块提交或包版本。示例配置仅用于复现实验，不是所有现场的默认配置。

## 验证与贡献

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q
ruff check src tests examples scripts
ruff format --check src tests examples scripts
python -m build
# 系统缺少 ensurepip 时可以使用 python -m build --installer uv。
```

CI 还会安装构建出的 wheel，并在仓库之外验证 API、包内预设和 CLI。扩展能力、数据管理、兼容性与发布规则见 [CONTRIBUTING](CONTRIBUTING.md)。
