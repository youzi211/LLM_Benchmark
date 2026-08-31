import { createRouter, createWebHashHistory, type RouteRecordRaw } from "vue-router";

const routes: RouteRecordRaw[] = [
  {
    path: "/",
    redirect: "/overview",
  },
  {
    path: "/overview",
    name: "overview",
    component: () => import("@/views/OverviewView.vue"),
    meta: { title: "概览", tab: "overview" },
  },
  {
    path: "/basic",
    name: "basic",
    component: () => import("@/views/BasicView.vue"),
    meta: { title: "基础评测", tab: "basic" },
  },
  {
    path: "/stress",
    name: "stress",
    component: () => import("@/views/StressView.vue"),
    meta: { title: "压测评测", tab: "stress" },
  },
  {
    path: "/intelligence",
    name: "intelligence",
    component: () => import("@/views/IntelligenceView.vue"),
    meta: { title: "能力评测", tab: "intelligence" },
  },
  {
    path: "/suites",
    name: "suites",
    component: () => import("@/views/SuitesView.vue"),
    meta: { title: "一键完整评测", auxiliary: true },
  },
  {
    path: "/schedules",
    name: "schedules",
    component: () => import("@/views/SchedulesView.vue"),
    meta: { title: "定时任务", auxiliary: true },
  },
  {
    path: "/compare",
    name: "compare",
    component: () => import("@/views/CompareView.vue"),
    meta: { title: "任务对比", auxiliary: true },
  },
  {
    path: "/style-guide",
    name: "style-guide",
    component: () => import("@/views/StyleGuideView.vue"),
    meta: { title: "设计系统", auxiliary: true, devOnly: true },
  },
];

const router = createRouter({
  history: createWebHashHistory(),
  routes,
});

// 开发态独占页面（如 /style-guide）在生产构建中直接重定向到概览。
router.beforeEach((to, _from, next) => {
  if (to.meta?.devOnly && !import.meta.env.DEV) {
    return next({ path: "/overview", replace: true });
  }
  next();
});

export default router;
