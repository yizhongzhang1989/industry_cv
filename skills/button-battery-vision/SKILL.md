---
name: button-battery-vision
description: 使用 industry_cv 接入 RTSP 相机，在深色平面上检测和定位纽扣电池，配置取料区、验证效果、接入平面标定并回流现场知识。适用于视觉库调试和集成，不负责机器人运动编排。
---

# 纽扣电池视觉

从当前现场总仓库定位 industry_cv 子模块；也可从本文件真实路径向上两级定位本库。核心 API 在 `src/industry_cv/`，先阅读 [使用入口](../../README.md)，只加载与任务相关的下列文档。

- 相机接入、Python/JSONL 输出和上层职责：读 [integration](../../docs/guides/integration.md)。从环境变量读取凭据，当前参考主码流路径是 `/stream0`，使用 TCP。
- 实际机器人坐标：读 [calibration](../../docs/guides/calibration.md)。没有实际对应点时，可按用户授权用 LR41 名义尺寸 7.9 × 3.6 mm 先跑通：`stream --estimate-diameter-mm 7.9` 或默认运行 `examples/button_battery/site_integration.py`。估计值输出为 `source=estimated`、`frame_id=work_surface_estimated`，无需等标定再运行。未选择估计且未提供标定时才保持 `position=null`。电池尺寸可估计工作平面尺度，不能证明其与物理机器人基座的关系。用 `validate-calibration` 对独立实测点生成误差报告；复用拟合点、缺少拟合点来源或误差超限时不得报告验收通过。
- 现场检测优化：先看 [真实案例](../../knowledge/cases/2026-11-26-button-battery/README.md)，根据新画面检查 ROI、像素半径、光照和接触情况；复制站点配置到总仓库，不把一个站点的 ROI 写入通用算法。

按任务需要运行 `industry-cv snapshot`、`detect`、`stream`。用 `--annotated` 或 `--save-dir` 对比图像及结果，检查每一个目标，尤其是相接电池、圆孔、包装盘和边界。单凭计数相等不能证明没有漏检/误检。

当前算法基于亮物体/暗背景的几何特征，不是语义分类模型；在同形金属片、复杂背景、严重反光、堆叠或遮挡场景，先记录失败条件，再按数据选择光学改善、分割或学习模型。侧光场景默认使用照度归一化和暗外缘补检；检查 diagnostics 中的处理方式与恢复数量。不要把现有 100 个静态电池的结果泛化为所有工业场景精度。

改动核心算法后运行对应测试与离线评估；实时验证报告应区分拟合/开发样例、独立标注、静态重复性、物理定位精度及端到端延迟。使用同一帧反复推理不算多帧稳定证据。实时 `pickable` 仅表示视觉条件通过，不能作为重复发送机器人动作的循环。

可复用知识按 [知识库约定](../../knowledge/README.md) 回流；新增失败案例应尽量转成脱敏回归样例。核心代码留在本库，现场状态机与抓取验证留在上层。
