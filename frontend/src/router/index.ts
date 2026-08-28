import { createRouter, createWebHashHistory, type RouteRecordRaw } from "vue-router";

const routes: RouteRecordRaw[] = [
  {
    path: "/",
    redirect: "/basic",
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
];

const router = createRouter({
  history: createWebHashHistory(),
  routes,
});

export default router;
