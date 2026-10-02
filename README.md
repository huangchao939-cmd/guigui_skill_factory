# guigui_skill_factory

GUiGUI 的个人 skill 沉淀仓库。把实际任务中验证过的流程、判断标准、模板和脚本整理为可复用的 Agent 技能，并持续维护。

## 已收录

| Skill | 用途 | 状态 |
|---|---|---|
| [course-lecture-notes](skills/course-lecture-notes/SKILL.md) | 将字幕、视频、PPT 与官方代码转为详细中文课程讲义，支持七件套、批量制作和验收 | active · v1.0.0 |
| [course-teaching-notebooks](skills/course-teaching-notebooks/SKILL.md) | 将已有讲义转为可运行教学 Notebook，提供结果观察、参数实验、练习答案及 HTML 阅读版 | active · v1.0.0 |

完整元数据见 [catalog.json](catalog.json)。新增和修改 skill 先阅读 [沉淀规范](docs/SKILL_STANDARD.md)；Agent 还必须遵循 [AGENTS.md](AGENTS.md)。

## 使用

将需要的 `skills/<skill-name>/` 整个文件夹复制到目标 Agent 的技能目录，例如 Codex 的 `~/.codex/skills/`。保留 `references/`、`scripts/` 等相对路径，不只复制 `SKILL.md`。

不支持 skill 自动发现的 Agent，可以直接读取对应 `SKILL.md`，随后读取其中要求的参考资料。

讲义制作示例：

```text
使用 $course-lecture-notes，为指定课程制作详细中文讲义。
课程列表：……
官方资料或本地输入：……
输出目录：……
按七件套标准制作，融合官方代码和资源，补充解释、示例、练习答案和实验。
记录来源、覆盖情况和资料缺口，交付 Markdown；需要 PDF 时完成渲染验收。
```

## 维护

```text
python -m pip install -r requirements-dev.txt
python scripts/validate_skills.py
```

提交前运行检查，并记录实际测试。当前使用本地结构检查；GitHub Actions 配置已在本地准备，待 GitHub 授权具备 `workflow` 权限后上传启用。结构检查不替代真实任务验收。

仓库保存技能定义和少量必要资源。课程视频、批量讲义、临时截图、缓存、账号资料和密钥不进入本仓库。

## 开源许可

本仓库原创技能、脚本和维护文档采用 [MIT License](LICENSE)，允许使用、修改和分发，需保留版权及许可声明。引用或链接的第三方课程、代码与资料遵循其各自许可证。
