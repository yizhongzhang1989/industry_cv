# 维护与贡献

先阅读 [架构边界](docs/architecture.md)。本库为多个现场提供相同核心能力；现场状态机、设备互锁、机器人指令和生产数据留在上层项目。

## 新增或改进能力

1. 根据职责放入 `acquisition/`、`detectors/`、`geometry/` 或 `pipelines/`；只在实际出现复用需求时抽取公共接口，不为空想功能建立空目录或插件体系。
2. 新算法保持图像输入与结果输出接口，避免读取全局现场配置或自行连接设备。需要相机时由调用方注入 `Frame`。通用预设加入包内 `profiles/`，不要包含相机地址、ROI 或机器人位姿。
3. 在 `examples/<能力>/` 放置现场示例及明确标注的场景配置。示例可以展示上层如何消费结果，但其流程不进入库 API。
4. 单元测试验证合成几何/状态边界；集成测试验证接口；真实问题添加最小 `tests/data/<能力>/` 样例与回归测试。不要依靠计数相同证明定位正确。
5. 在 `knowledge/cases/` 添加条件、失败原因、测量方法与证据，更新知识索引；技能只链接维护中的代码和文档，不复制算法。

## 本地验证

```bash
python -m pip install -e '.[dev]'
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q
ruff check src tests examples scripts
ruff format --check src tests examples scripts
python -m build
```

系统缺少 ensurepip 时，可以用 `uv venv` 安装开发环境并以 `python -m build --installer uv` 构建。

CI 还会把构建出的 wheel 替换安装到环境，在仓库之外运行 `scripts/check_installation.py`，验证公开 API、包内预设与 CLI。源码包应包含示例、技能、知识和回归数据；wheel 只包含运行库及通用资源。

## 版本与升级

版本记录在 `pyproject.toml`，变更和迁移步骤记录在 [CHANGELOG](CHANGELOG.md)。已发布版本打 `vX.Y.Z` 标签；现场仓库固定子模块提交或 wheel 版本，避免生产项目隐式跟随开发分支。

当前为 0.x 阶段：破坏性接口、默认行为或配置变更增加次版本，兼容修复增加修订版本。稳定入口是根包导出、CLI 命令及文档化 JSON 字段；内部实现可按迁移说明调整。进入 1.x 后使用语义版本规则。

新增兼容字段保留现有 JSON 语义；改变单位、坐标系解释或必需字段时升级协议版本。数据/知识记录应说明当时版本或配置哈希，旧实验结果不直接作为新实现的性能声明。

不要提交 `.env`、真实站点标定、生产视频和密钥。用户明确授权使用估计值时，保存假设与来源，让实测值能够替换它们；不要将估计坐标宣称为已测量的机器人外参。
