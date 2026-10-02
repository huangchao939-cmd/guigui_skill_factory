# 批量制作与断点续作

## 目录与清单

一个课程一个根目录。建议使用以下稳定结构，已有项目可映射到等价位置：

```text
课程根目录/
  README.md
  course-manifest.json
  sources/
    source-map.md
    official-transcripts/
    slides/
    official-code/
  lectures/
    L01-课节名/
      L01-官方英文逐字稿.md
      L01-视频时间轴.md
      L01-中文精译逐字稿.md
      L01-详细讲义.md
      L01-一页复习.md
      L01-闪卡与练习.md
      L01-实验.md
  output/pdf/
  tmp/
```

只有实际取得材料才创建对应文件；不存在 PPT 或未下载代码时不填伪文件。外部代码可以只保留已核验的链接与版本，依据用户离线需求决定是否下载。

`course-manifest.json` 使用 UTF-8 JSON，结构示例（示例状态不代表已完成）：

```json
{
  "title": "课程标题",
  "course_url": "https://official.example/course",
  "language": "en",
  "lessons": [
    {
      "id": "L01",
      "title": "课节标题",
      "directory": "lectures/L01-课节标题",
      "status": "pending",
      "source_status": "missing",
      "artifacts": {},
      "gaps": [],
      "verification": {
        "coverage": "pending",
        "code_execution": "not_run",
        "rendering": "not_requested"
      }
    }
  ]
}
```

课节状态：`pending` → `sources_ready` → `drafted` → `reviewed` → `complete`；有实际资料/权限缺口时用 `blocked` 并列出缺口。`source_status` 使用 `complete/partial/missing`。`artifacts` 将七件套的资料名映射为课程根目录下的相对路径，中文课用“官方原文逐字稿”替换英文稿。验证状态允许 `pending/passed/failed/not_run/not_applicable/not_requested`；未执行实验只能记录 `not_run`。

## 执行顺序

1. 读取现有清单、来源和成果，核实状态后续作；不能仅凭文件存在跳过内容审查。
2. 先确定全部课程/章节顺序与输出边界，再收集来源。优先按一课或少量课节完成完整交付，避免全部目录都只有空壳。
3. 每课节先来源与覆盖表，再译文、讲义、速查、练习、实验。完成一节及时更新清单，记录失败和来源缺口。
4. 同一课程共享术语表和版本说明；全部课节复核后统一导航与课程级项目，避免重复/矛盾。
5. 用户允许批量时持续完成授权范围；资料缺失不阻止处理其余已具备来源的课节。需要用户介入时精确说明哪一课、哪个资源、已完成什么。
6. 最后检查结构、内容覆盖、链接和导出文件；提交课程入口、完成统计、实际验证范围、剩余缺口。

## 多 Agent 协作

仅当用户或上层任务已经授权多 Agent 工作且环境支持时分派；不自行创建新的用户任务或外部消息。

分工单位优先为整个课程；同一课程可按不重叠课节分派。协调 Agent 独占课程级导航、术语表、清单与完整手册；课节 Agent 仅写自己课节目录及独立的来源/完成报告。避免同时改清单或覆盖同名输出。

任务必须携带：skill 的绝对路径、输入来源、负责课节、输出目录、需要交付的格式、已授权操作与禁止操作。若跨机器执行，先把整个 skill 文件夹放到对方环境可读取位置，不依赖原机器路径。

派发示例：

```text
使用 $course-lecture-notes（位于 <skill目录>），为 <课程标题> 制作 L03-L05。
输入来源：<字幕/PPT/官方仓库路径或链接>。
仅写入 <课程根目录>/lectures/L03-* 至 L05-*；附来源映射与完成报告。
按七件套标准细致讲解，包含官方代码导读、示例、参考答案和可验证实验。
缺少来源时记录缺口，不编造逐字稿；未执行代码标明未运行。
由协调 Agent 整合课程级文件和进度，完成结构、内容、格式验收。
```
