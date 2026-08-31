# 设计系统展示页覆盖规则

> 路由: `/style-guide` | 覆盖 MASTER.md 全局规则

## 布局
PageHero + 7 个 section（色板 / 字体 / 圆角阴影 / 按钮 / 状态 / Token 速查 / 反模式）

## 与 Master 的偏差
- 仅开发态可见（meta.devOnly），生产构建重定向到 /overview
- 纯展示页，无数据交互

## 关键组件
无业务组件

## 注意事项
- 可视化所有设计 Token，验收设计系统一致性时参考此页
- 反模式 section 展示禁止使用的样式（emoji 图标、低对比、布局位移 hover 等）
