# 旧 Cloud 发版与退役边界

## 1. 作用
这份 runbook 只记录旧 Cloud 阶段的遗留发布入口与退役边界。

当前正式线上节点已经切到 NAS；Cloud 不再是当前默认发布目标。

旧 Cloud 历史上只负责：
- 轻量盯盘
- 手机 / 异地应急查看
- 生产只读 / 轻写接口消费

## 2. 当前发布入口
```bash
cd /Users/dong/Desktop/AIGC/market-live-terminal
./deploy_to_cloud.sh
```

使用规则：

- 只有在明确需要维护旧 Cloud 遗留环境时才使用这条入口
- 当前默认线上发布、在线查询和 `research/current` 收口都应走 NAS 相关 runbook

## 3. 发布前必须确认
1. 当前改动确实属于 Cloud 范围
2. `main` 已包含要发布的提交
3. `npm run check:baseline` 已通过
4. 版本号一致：`package.json / src/version.ts / README.md / backend/app/main.py`

## 4. 发布后最小冒烟
- 页面可打开
- `/api/health`
- `/api/realtime/dashboard`
- 若本轮涉及 review/selection/events，再抽样对应接口

## 5. 当前边界
- Cloud 不承载 full atomic 全量主库
- 不把 Mac 本地研究站能力直接等同为 Cloud 生产能力
- Cloud Lite 历史上必保能力只有盯盘与正式复盘；当前线上研究查询已经由 NAS 承接
- 后续应通过运行 profile / 环境开关隐藏或禁用 Cloud 非目标模块，不维护两套代码
- 云端数据清理必须先列白名单，再删旧库/旧目录
