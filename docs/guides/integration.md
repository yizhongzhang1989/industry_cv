# 上层仓库接入

建议现场总仓库组织为：

```text
site_project/
  third_party/industry_cv/     # 本库子模块，固定提交
  third_party/robot/           # 机器人库子模块
  configs/vision.json          # 当前现场 ROI / 尺寸参数
  calibration/plane.json      # 当前相机、抓取平面与机器人坐标系
  orchestration/              # 工单、状态机、抓取、验证和重试
  data/                       # 现场数据，按总仓库数据策略管理
```

开发时 editable install，发布时安装固定版本 wheel 或固定子模块提交。不要把核心算法复制到现场总仓库；通用改进及最小回归样例回流本库后，再升级子模块。Python API 和 JSON 协议的破坏性变更应更新版本并写迁移说明。

## 接口选择

Python：`BatteryDetector.detect(bgr)` 返回 `Detection` 列表；`RTSPCamera.read()` 返回带序号、连接代号、接收时间的 `Frame`；`VisionPipeline.process(frame)` 返回可 JSON 序列化的结果。已经通过 ROS 图像话题取图时，将图像转换为 uint8 BGR，并为每个**真实新帧**构造 `Frame`，不需要重复打开 RTSP。

C++、C#、Go 等可以启动 `industry-cv stream --config ... --calibration ...`，逐行读取 stdout JSON，监测进程退出和超时，stderr 留作诊断。不要只取最后一次成功结果后无限复用。CLI 退出码 2 为配置/处理错误，130 为中断；`validate-calibration` 的退出码 3 表示点位验收未通过。无标定可获取像素定位，也可用 `--estimate-diameter-mm 7.9` 获取明确标注的工作平面毫米估计。

输出结构示例（数值仅用于说明字段）：

```json
{
  "schema_version": "1.1",
  "frame_sequence": 12,
  "connection_id": 1,
  "received_at_unix": 1795680000.0,
  "timestamp_source": "host_decode_receipt",
  "frame_age_s": 0.03,
  "image_size": [1920, 1080],
  "targets": [{
    "track_id": 1,
    "center_px": [742.8, 179.0],
    "radius_px": 24.0,
    "axes_px": [47.8, 48.2],
    "ellipse_angle_deg": 82.0,
    "score": 0.97,
    "arc_coverage": 1.0,
    "contrast": 120.0,
    "stable": true,
    "jitter_px": 0.1,
    "position": null,
    "position_source": null,
    "pickable": false,
    "blocked_reasons": ["uncalibrated"]
  }],
  "diagnostics": {
    "lighting_normalized": true,
    "shadow_recovered": 0,
    "threshold": 96.0,
    "rejected_candidates": 0,
    "processing_ms": 27.0
  },
  "calibration": null
}
```

有标定或启用尺寸估计时 `position` 为 `{x_mm, y_mm, z_mm, frame_id}`。单位是 **mm**，ROS 或以米为单位的机器人库须显式换算。`z_mm` 是标定的目标表面平面高度，不是接近高度或工具 TCP 位姿。标定残差只反映拟合点，外推被禁止。上层可运行 `validate-calibration` 检查独立点位报告，核对通过状态、工艺容差和标定哈希后决定是否启用抓取。

`blocked_reasons`：

| 原因 | 含义 |
|---|---|
| `roi_border` | 目标边缘距有效区域不足 |
| `neighbor_clearance` | 邻近电池间距不足当前配置阈值 |
| `unstable` | 未连续观测足够帧，或中心抖动过大 |
| `uncalibrated` | 没有可用标定或尺寸估计 |
| `outside_calibration` | 目标超出标定区域或图像分辨率不匹配 |
| `stale` | 处理完成时帧已超过时效 |
| `single_frame` | 离线单帧没有连续稳定性依据 |

协议 1.1 增加 `calibration` 摘要和目标 `position_source`，取值为 `estimated` 或 `correspondences`；没有位置时为 null。估计模式通过视觉条件也可返回 `pickable=true`，供上层联调，来源不会被隐藏。

`pickable=true` 仅表示通过本库的视觉条件。它不是机器人动作指令，也不证明夹爪空间可达。`clearance_px` 默认 4 像素，需按实际夹爪/吸盘外形设置或在上层做更完整的碰撞检查。部分堆叠、严重遮挡和非圆物可能被拒绝而不输出；因此“检测列表为空”不能证明料区已经清空。

## 时间与追踪

解码线程持续排空视频，每个实例仅保留最新帧，慢调用方跳过中间帧；断流后重连并清空旧帧。读取支持超时与最大帧龄。同一帧不能重复计入稳定性；目标消失、连接变更、采样中断会清空稳定记录。默认连续 3 次观测、最大中心偏差 1 像素。

序号只在一个相机实例内单调递增，`track_id` 只在一个 pipeline 生命周期内有效；相邻目标交叉移动或遮挡后身份不能保证。此跟踪器用于静态取料，不用于运动输送带追踪。

时间戳来自**主机解码接收时刻**，不是传感器曝光时刻，帧龄不包含相机编码缓存和网络传输延迟。当前单帧检测速度与真实端到端延迟分开报告。移动相机/运动抓取需要相机时间同步、实际时延测量及机器人位姿同步，由现场工程补充。

上层流程应：选定并保留一个目标 → 复核最新位置 → 执行接近/抓取/撤离 → 重新取图验证结果。每次检测输出不是新的抓取工单，不能每帧重复执行整张目标列表。

## 模块边界

| 本库 | 现场总仓库 / 机器人库 |
|---|---|
| 相机接入、检测、图像标定和定位 | 设备互锁、机器人通信、轨迹执行 |
| 图像坐标、平面毫米坐标、视觉拒绝原因 | 工具姿态、抓取高度补偿、目标预留 |
| 通用算法测试、脱敏样例、AI 技能 | 当前现场密钥、标定、生产记录与验收 |

AI 工具可从 `skills/button-battery-vision/SKILL.md` 读取技能。它依赖本子模块的相对路径；将整个技能目录或入口关联到上层所用工具的技能发现目录时，保留本库路径的可解析性。

开启光照归一化（默认）时，`contrast` 与阈值基于归一化后的灰度，不是相机原始灰度。`diagnostics.lighting_normalized` 和 `shadow_recovered` 记录处理方式及补检数量；显式设置 `threshold` 时只使用该阈值，自动阴影补检仅作用于自适应阈值。
