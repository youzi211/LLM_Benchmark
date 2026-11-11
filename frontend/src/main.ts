import { createApp, h } from "vue";
import { createPinia } from "pinia";
import { ElConfigProvider } from "element-plus/es/components/config-provider/index";
import zhCn from "element-plus/es/locale/lang/zh-cn";
import router from "./router";
import App from "./App.vue";
import "./styles/global.css";

// 全局中文文案（表格全选 / 分页总数等）；只引入 ConfigProvider，不整包注册 Element Plus。
const app = createApp({ render: () => h(ElConfigProvider, { locale: zhCn }, () => h(App)) });
app.use(createPinia());
app.use(router);
app.mount("#app");
