# Cloud 发版与轻量盯盘

## 1. 作用
Cloud 当前只负责：
- 轻量盯盘
- 手机 / 异地应急查看
- 生产只读 / 轻写接口消费

## 2. 当前发布入口
```bash
cd /Users/dong/Desktop/AIGC/market-live-terminal
./deploy_to_cloud.sh
```

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
