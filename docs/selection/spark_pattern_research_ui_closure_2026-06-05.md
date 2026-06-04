# 星火形态研究页 UI 收口

更新时间：2026-06-05

## 结论

这条 `spark-ui` worktree 做的不是模型训练，而是选股研究工作台里的“星火形态研究页”前端。

本轮已确认这条线可以正式收口：

1. 选股研究工作台顶部已接入 `研究入口` 下拉菜单
2. 已接通 3 个独立研究页：
   - `星火 1.0 形态研究页`
   - `星火 v2 稳健型形态研究页`
   - `星火 v2 进攻型形态研究页`
3. 每个研究页都能按股票展示完整图卡，并标出：
   - 信号日
   - 次日买入日
   - 22 日硬退出日
4. 星火 v2 对应的静态 research payload 和导出脚本已经补齐

因此，这条 worktree 不需要继续独立保留，适合并回主分支后关闭。

## 正式保留产物

### 一、前端入口

- `src/App.tsx`
- `src/components/selection/SelectionResearchPage.tsx`

当前正式入口不是单独记 URL，而是：

- 先进入 `/selection-research`
- 再从顶部 `研究入口` 下拉菜单进入对应页面

### 二、研究页组件

- `src/components/selection/SparkPatternPrototypePage.tsx`
- `src/components/selection/SparkPatternResearchPage.tsx`
- `src/components/selection/SparkPatternResearchShared.tsx`
- `src/components/selection/sparkPatternResearchRegistry.ts`

### 三、静态研究数据

- `public/research/spark_top1_pattern_prototype.json`
- `public/research/spark_v2_guarded_pattern_research.json`
- `public/research/spark_v2_aggressive_pattern_research.json`

### 四、导出脚本

- `backend/scripts/export_spark_pattern_research_payloads.py`

## 验收结果

### 构建

- `npm run build` 已通过

### 页面验收

已实际打开并确认：

1. `/selection-research`
   - 顶部能看到 `研究入口`
   - 点击后能展开 3 个研究页菜单项
2. `/selection-spark-pattern-research/1-0`
   - 页面能正常打开
   - `Top1 / Top3` 档位切换可见
   - 图卡和标记线可正常渲染

## 业务边界

这次收口只代表“研究页 UI 已完成”。

不代表：

1. 新训练链路已经新增
2. 星火模型结论发生变化
3. 这套页面本身参与正式选股打分

它的定位仍然是：

- 给研究工作台提供一个正式的形态观察入口
- 帮助回看模型到底选了什么票、形态长什么样

## 一句话收口

`spark-ui` 这条线已经不是待探索原型，而是可用、已验收、适合并回主分支的研究页前端功能。
