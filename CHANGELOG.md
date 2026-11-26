# Changelog

## 0.2.0 — 首个功能版本，未发布

首次功能提交包含下列完整实现。0.1.0 仅指此前的本地开发阶段，尚未作为独立版本发布。

仓库从单一纽扣电池项目整理为可复用工具库，检测算法与 JSON 1.1 输出语义保持不变。

- 模块按 `core`、`acquisition`、`detectors`、`geometry`、`pipelines`、`cli` 分层；`Frame` 不再属于相机实现。
- 保留 `from industry_cv import ...` 顶层导入和 `industry-cv` 命令入口；`ButtonBatteryPipeline` 是领域明确的新名称，`VisionPipeline` 是兼容别名。
- 通用预设随 wheel 发布，通过 `load_profile()` 或 `industry-cv profiles` 使用。LR41 尺寸与上层抓取姿态拆分。
- 现场示例集中到 `examples/button_battery/`；知识记录归档到 `knowledge/cases/`；测试区分 unit、integration、regression。
- CI 增加在仓库外检查已安装 wheel，覆盖预设资源和真实图片 CLI。

### 0.1 → 0.2 迁移

| 旧位置/行为 | 新位置/行为 |
|---|---|
| `industry_cv.battery` | `industry_cv.detectors.button_battery`；优先使用顶层导出 |
| `industry_cv.camera` | `industry_cv.acquisition.rtsp`；`Frame` 从顶层或 `core.frame` 导入 |
| `industry_cv.calibration` | `industry_cv.geometry.planar` |
| `industry_cv.pipeline` | `industry_cv.pipelines.button_battery` |
| `industry_cv.cli.annotate` | `industry_cv.visualization.annotate` |
| `configs/button_battery.site.example.json` | `examples/button_battery/configs/vision.json` |
| `configs/lr41.defaults.json` | 名义物料数据在 `load_profile("parts/lr41")`，姿态在示例 `configs/integration.json` |
| `examples/site_integration.py`、`examples/evaluate.py` | `examples/button_battery/` 下同名文件 |
| `tests/fixtures/` | `tests/data/button_battery/` |
| `docs/knowledge/` | `knowledge/`，案例证据与图片在对应案例目录内 |

相机地址现在必须通过 `CameraConfig(host=...)` 或 `INDUSTRY_CV_CAMERA_HOST` 指定；用户名/密码默认空，路径默认 `/`，不再静默连接历史现场。已有本机 `.env` 已包含该相机全部参数，可继续使用。端口也支持环境变量 `INDUSTRY_CV_CAMERA_PORT`。

通用几何 API 的 `from_nominal_diameter` 要求调用方提供 `diameter_mm`；管线和几何的默认工作平面高度为 0 mm，不再默认某种电池厚度。LR41 可显式用包内预设传入 7.9 / 3.6 mm，或在 CLI 使用 `--part-profile parts/lr41`。`estimate-calibration` 需要 `--diameter-mm` 或 `--part-profile`。

现场集成示例仍默认 LR41：它读取物料预设与示例配置后显式传入尺寸，不需要手动标定即可运行估计模式。

## 0.1.0 — 未发布的开发阶段

初始实现：RTSP、纽扣电池检测与追踪、平面标定/尺寸估计、独立点验收、JSONL 接口、LR41 现场样例和技能。
