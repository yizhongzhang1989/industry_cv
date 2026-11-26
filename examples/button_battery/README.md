# LR41 纽扣电池现场示例

本目录是复现首个工业现场的示例，上层项目可以参考其接入方式。核心算法由已安装的 `industry_cv` 提供；示例 ROI、工具姿态和流程不进入运行库。

以下命令均在仓库根目录执行。脚本自身使用相对其文件位置的配置路径，也可以从其他 cwd 调用。

## 离线检查

```bash
industry-cv detect tests/data/button_battery/button_cells_side_light.jpg \
  --config examples/button_battery/configs/vision.json --part-profile parts/lr41 \
  --output artifacts/lr41.json --annotated artifacts/lr41.jpg
python examples/button_battery/evaluate.py \
  --image tests/data/button_battery/button_cells_100.jpg \
  --labels tests/data/button_battery/button_cells_100.json \
  --config examples/button_battery/configs/vision.json --repeat 50
```

## 相机与上层接入

当前工作机已有本地 `.env`（Git 忽略）。在新现场将 [.env.example](.env.example) 复制到现场总仓库并配置相机；库不再默认连接最初现场的 IP。相机地址必须提供，用户名/密码可以为空，端口默认 554、路径默认 `/`；本案例使用 `/stream0`。

```bash
source .venv/bin/activate
set -a
source .env
set +a
python examples/button_battery/site_integration.py --frames 120 \
  > artifacts/target_requests.jsonl
```

去掉 `--frames` 持续运行。示例输出 `pick_target_proposals`，包含目标、时间戳、来源、接近姿态和接触姿态，`execution_mode=preview`。它不向机器人发送运动，实际转换/预留/执行/复核由总仓库管理。

只需要完整视觉结果：

```bash
industry-cv stream --config examples/button_battery/configs/vision.json \
  --part-profile parts/lr41 --frames 120 > artifacts/vision.jsonl
```

## 默认值的归属

| 数据 | 来源 |
|---|---|
| LR41 名义直径 7.9 mm、厚度 3.6 mm | `load_profile("parts/lr41")`，随 wheel 发布 |
| ROI、1920×1080 分辨率、像素尺度 | [configs/vision.json](configs/vision.json)，此案例配置 |
| 接近偏移 20 mm、朝下四元数 xyzw=[1,0,0,0] | [configs/integration.json](configs/integration.json)，上层示例参数 |
| 相机网络与凭据 | 现场环境变量/本地 `.env` |
| 真实相机外参与机器人工作平面 | 现场标定文件 |

估计模式用首个非空帧的电池直径中位数建立并冻结尺度。原点为 ROI 面积中心，X 向图像右、Y 向图像上、Z 指向相机，坐标系名为 `work_surface_estimated`。物料高度为工作平面上的厚度。`position_source=estimated`，未知物理精度保持 null。`pickable` 只反映视觉条件。

## 换到另一个现场

将此目录的示例配置复制到总仓库，按新现场调整。脚本支持 `--config`、`--integration-config` 和 `--part-config`（使用实际物料 JSON 替代包内名义规格），也支持 `--diameter-mm`、`--height-mm` 覆盖尺寸。

```bash
# 可复用但仍明确标注为 estimated 的工作平面文件。
industry-cv estimate-calibration IMAGE --config SITE.json --part-profile parts/lr41 \
  --output /path/to/site/estimated-plane.json
# 有真实标定后切换接口，不改核心检测代码。
python examples/button_battery/site_integration.py --config /path/to/site/vision.json \
  --calibration /path/to/site/plane.json
```

标定与独立验证见[标定指南](../../docs/guides/calibration.md)；案例证据和限制见[知识记录](../../knowledge/cases/2026-11-26-button-battery/README.md)。名义尺寸估计不能恢复未知的机器人基座变换，提案也不能每帧重复当成新工单执行。
